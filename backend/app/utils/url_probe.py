"""判断来源链接在浏览器里能不能打开，供详情页决定跳原文还是跳必应搜索兜底。

判定规则
--------
* 非 http(s)（如 ``tianapi://`` 伪 URL、空值）→ 不可浏览
* 反爬白名单域名（``TRUSTED_HOSTS``，如知乎）→ 直接判可浏览，不探测
* http(s) → 真实发起一次请求探测：
  - 状态码 < 400 且 content-type 是 html/text → 可浏览
  - 4xx/5xx、超时、非 html（JSON API 链接）→ 不可浏览

关键点：**探测不走出站代理**（``trust_env=False``），模拟国内浏览器直连 —— 否则
Google News、FT 这类"走代理能通、访客打不开"的链接会被误判为可用。

缓存：成功 24h，失败 2h（网络抖动不应长期判死一个链接）。结论同时写 Redis
（``probe:url:<sha1>``，与内存同样的 TTL），进程重启或多 worker 时仍能命中；
内存字典只是 Redis 之上的快路径。

接口侧用 ``get_probe_cache`` 只读结论、``warm`` 后台补冷：详情页不再为探测
阻塞请求（此前单链接最长 5s、整页预算 7s，首次打开能卡到 7s）。
"""

import asyncio
import hashlib
import ipaddress
import time
from typing import Dict, Optional, Tuple, Union
from urllib.parse import quote

import httpx
from loguru import logger

from app.cache.redis_client import get_redis_client

PROBE_TIMEOUT = 5.0          # 单个链接探测上限
CONCURRENCY = 4              # 并发探测上限
OK_TTL = 24 * 3600           # 成功结论缓存
FAIL_TTL = 2 * 3600          # 失败结论缓存（短一些，留给网络抖动恢复）
MAX_BYTES = 16384            # 单次探测最多读取的响应体，防止大文件拖垮探测
MAX_REDIRECTS = 5            # 手动跟随重定向的跳数上限（每跳都要过内网过滤）

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 对机房 IP 一律返回 403/412 反爬、但访客浏览器能正常打开的站点。
# 这些域名不做网络探测，直接视为可浏览，避免被错误降级到搜索兜底。
TRUSTED_HOSTS = ("zhihu.com",)

# url -> (browsable, expires_at)
_cache: Dict[str, Tuple[bool, float]] = {}
_sem = asyncio.Semaphore(CONCURRENCY)
# 正在后台预热的 URL / 持引用防止任务被 GC
_warming: set = set()
_warm_tasks: set = set()


def is_browser_url(url: Optional[str]) -> bool:
    return bool(url) and (url.startswith("http://") or url.startswith("https://"))


def is_trusted_url(url: Optional[str]) -> bool:
    """命中反爬白名单（不做探测，直接判可浏览）。"""
    if not is_browser_url(url):
        return False
    host = (httpx.URL(url or "").host or "").lower()
    return any(host == d or host.endswith("." + d) for d in TRUSTED_HOSTS)


def bing_fallback(title: str) -> str:
    """不可浏览时的兜底：必应搜索该标题。"""
    return f"https://www.bing.com/search?q={quote(title or '')}"


def _cached(url: str) -> Optional[bool]:
    item = _cache.get(url)
    if not item:
        return None
    ok, expires = item
    if time.time() > expires:
        _cache.pop(url, None)
        return None
    return ok


def _redis_key(url: str) -> str:
    return "probe:url:" + hashlib.sha1(url.encode()).hexdigest()


async def _load_from_redis(url: str) -> Optional[bool]:
    """读 Redis 结论并回填内存缓存；Redis 不可用时静默降级为纯内存模式。"""
    try:
        raw = await get_redis_client().get(_redis_key(url))
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"URL 探测缓存读取失败 {type(exc).__name__}: {url[:100]}")
        return None
    if raw is None:
        return None
    ok = raw == "1"
    _cache[url] = (ok, time.time() + (OK_TTL if ok else FAIL_TTL))
    return ok


async def _save_to_redis(url: str, ok: bool) -> None:
    ttl = OK_TTL if ok else FAIL_TTL
    try:
        await get_redis_client().setex(_redis_key(url), ttl, "1" if ok else "0")
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"URL 探测缓存写入失败 {type(exc).__name__}: {url[:100]}")


def _is_global_ip(ip: Union[ipaddress.IPv4Address, ipaddress.IPv6Address]) -> bool:
    """只允许公网单播地址；环回/私网/链路本地/保留/组播/未指定一律拒绝。"""
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def _host_allowed(host: str) -> bool:
    """解析主机名并校验其全部地址都是公网地址，挡 SSRF（内网/元数据地址）。"""
    if not host:
        return False
    try:
        return _is_global_ip(ipaddress.ip_address(host))
    except ValueError:
        pass
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    except (OSError, UnicodeError):
        return False
    if not infos:
        return False
    for info in infos:
        addr = info[4][0].split("%", 1)[0]  # 去掉 IPv6 scope id
        try:
            if not _is_global_ip(ipaddress.ip_address(addr)):
                return False
        except ValueError:
            return False
    return True


async def _probe(url: str) -> bool:
    # trust_env=False：不读 HTTP(S)_PROXY，走国内直连，和访客一致
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(PROBE_TIMEOUT, connect=3.0),
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml,*/*"},
    ) as client:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            if not await _host_allowed(httpx.URL(current).host):
                logger.debug(f"URL 探测拦截非公网目标: {current[:100]}")
                return False
            try:
                async with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            return False
                        current = str(resp.url.join(location))
                        continue
                    if resp.status_code >= 400:
                        return False
                    ctype = (resp.headers.get("content-type") or "").lower()
                    # 只认浏览器能直接读的页面；JSON/XML 这类 API 链接点了也是白屏
                    if ctype and not any(t in ctype for t in ("html", "text/plain", "xhtml")):
                        return False
                    # 只读到安全上限即停，避免大文件把探测拖垮
                    read = 0
                    async for chunk in resp.aiter_bytes():
                        read += len(chunk)
                        if read >= MAX_BYTES:
                            break
                    return True
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"URL 探测失败 {type(exc).__name__}: {current[:100]}")
                return False
        return False  # 重定向超过上限


async def is_browsable(url: Optional[str]) -> bool:
    """返回该链接能否在浏览器里正常打开（带缓存）。"""
    if not is_browser_url(url):
        return False
    target = url or ""

    # 反爬白名单直接判可用，并覆盖旧的探测结论
    if is_trusted_url(target):
        _cache[target] = (True, time.time() + OK_TTL)
        await _save_to_redis(target, True)
        return True

    hit = _cached(target)
    if hit is not None:
        return hit

    remote = await _load_from_redis(target)
    if remote is not None:
        return remote

    async with _sem:
        try:
            ok = await _probe(target)
        except Exception as exc:  # 兜底：绝不让探测把接口拖挂
            logger.warning(f"URL 探测异常 {type(exc).__name__}: {target[:100]}")
            return False

    _cache[target] = (ok, time.time() + (OK_TTL if ok else FAIL_TTL))
    await _save_to_redis(target, ok)
    if not ok:
        logger.info(f"来源链接不可浏览（将走搜索兜底）: {target[:120]}")
    return ok


async def get_probe_cache(urls: list) -> Dict[str, bool]:
    """只读已有结论（内存优先，其次 Redis），绝不发起网络探测。

    未命中的 URL 不出现在返回值里，由调用方按 ``is_browser_url`` 兜底，
    再用 ``warm`` 丢到后台补探测。
    """
    result: Dict[str, bool] = {}
    missing = []
    for url in {u for u in urls if is_browser_url(u)}:
        if is_trusted_url(url):
            result[url] = True
            continue
        hit = _cached(url)
        if hit is None:
            missing.append(url)
        else:
            result[url] = hit
    if not missing:
        return result

    try:
        values = await get_redis_client().mget([_redis_key(u) for u in missing])
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"URL 探测缓存批量读取失败 {type(exc).__name__}")
        return result

    for url, raw in zip(missing, values):
        if raw is None:
            continue
        ok = raw == "1"
        _cache[url] = (ok, time.time() + (OK_TTL if ok else FAIL_TTL))
        result[url] = ok
    return result


async def _warm_one(url: str) -> None:
    try:
        await is_browsable(url)
    finally:
        _warming.discard(url)


def warm(urls: list) -> None:
    """后台预热：给没有结论的链接排探测任务，立即返回，不阻塞请求。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # 非事件循环环境（如脚本）无需预热

    for url in {u for u in urls if is_browser_url(u)}:
        if _cached(url) is not None or url in _warming:
            continue
        _warming.add(url)
        task = loop.create_task(_warm_one(url))
        _warm_tasks.add(task)
        task.add_done_callback(_warm_tasks.discard)
