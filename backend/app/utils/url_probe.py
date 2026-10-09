"""判断来源链接在浏览器里能不能打开，供详情页决定跳原文还是跳必应搜索兜底。

判定规则
--------
* 非 http(s)（如 ``tianapi://`` 伪 URL、空值）→ 不可浏览
* http(s) → 真实发起一次请求探测：
  - 状态码 < 400 且 content-type 是 html/text → 可浏览
  - 4xx/5xx、超时、非 html（JSON API 链接）→ 不可浏览

关键点：**探测不走出站代理**（``trust_env=False``），模拟国内浏览器直连 —— 否则
Google News、FT 这类"走代理能通、访客打不开"的链接会被误判为可用。

缓存：成功 24h，失败 2h（网络抖动不应长期判死一个链接）。进程内字典缓存，
重启即失效，靠下次访问重建。
"""

import asyncio
import ipaddress
import time
from typing import Dict, Optional, Tuple, Union
from urllib.parse import quote

import httpx
from loguru import logger

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

# url -> (browsable, expires_at)
_cache: Dict[str, Tuple[bool, float]] = {}
_sem = asyncio.Semaphore(CONCURRENCY)


def is_browser_url(url: Optional[str]) -> bool:
    return bool(url) and (url.startswith("http://") or url.startswith("https://"))


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

    hit = _cached(target)
    if hit is not None:
        return hit

    async with _sem:
        try:
            ok = await _probe(target)
        except Exception as exc:  # 兜底：绝不让探测把接口拖挂
            logger.warning(f"URL 探测异常 {type(exc).__name__}: {target[:100]}")
            return False

    _cache[target] = (ok, time.time() + (OK_TTL if ok else FAIL_TTL))
    if not ok:
        logger.info(f"来源链接不可浏览（将走搜索兜底）: {target[:120]}")
    return ok


async def probe_many(urls: list) -> Dict[str, bool]:
    """批量探测，未缓存的并行查，返回 url -> browsable。"""
    unique = list({u for u in urls if is_browser_url(u)})
    if not unique:
        return {}
    await asyncio.gather(*(is_browsable(u) for u in unique))
    return {u: bool(_cached(u)) for u in unique}
