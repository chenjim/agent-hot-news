"""url_probe 的 SSRF 过滤与兜底逻辑测试。"""

import asyncio

import pytest

from app.utils import url_probe


class TestHostAllowed:
    @pytest.mark.asyncio
    async def test_loopback_rejected(self):
        assert not await url_probe._host_allowed("127.0.0.1")
        assert not await url_probe._host_allowed("::1")

    @pytest.mark.asyncio
    async def test_private_and_link_local_rejected(self):
        assert not await url_probe._host_allowed("192.168.31.165")
        assert not await url_probe._host_allowed("10.0.0.1")
        assert not await url_probe._host_allowed("169.254.169.254")

    @pytest.mark.asyncio
    async def test_public_ip_allowed(self):
        assert await url_probe._host_allowed("1.1.1.1")
        assert await url_probe._host_allowed("8.8.8.8")

    @pytest.mark.asyncio
    async def test_empty_host_rejected(self):
        assert not await url_probe._host_allowed("")


class TestProbeGuard:
    @pytest.mark.asyncio
    async def test_probe_blocks_private_targets(self):
        # 命中内网过滤时不发请求，直接判不可浏览
        assert await url_probe._probe("http://127.0.0.1:8000/") is False
        assert await url_probe._probe("http://169.254.169.254/latest/meta-data/") is False


class TestProbeRedisCache:
    class FakeRedis:
        def __init__(self):
            self.data = {}

        async def get(self, key):
            return self.data.get(key)

        async def mget(self, keys):
            return [self.data.get(k) for k in keys]

        async def setex(self, key, ttl, value):
            self.data[key] = value[0] if isinstance(value, tuple) else value
            self.data[key + ":ttl"] = ttl

    @pytest.fixture(autouse=True)
    def _clean_memory_cache(self):
        url_probe._cache.clear()
        url_probe._warming.clear()
        yield
        url_probe._cache.clear()
        url_probe._warming.clear()

    @pytest.mark.asyncio
    async def test_result_written_to_redis(self, monkeypatch):
        fake = self.FakeRedis()
        monkeypatch.setattr(url_probe, "get_redis_client", lambda: fake)

        async def ok_probe(url):
            return True

        monkeypatch.setattr(url_probe, "_probe", ok_probe)

        url = "https://example.com/ok"
        assert await url_probe.is_browsable(url) is True

        key = url_probe._redis_key(url)
        assert fake.data[key] == "1"
        assert fake.data[key + ":ttl"] == url_probe.OK_TTL

    @pytest.mark.asyncio
    async def test_redis_hit_skips_probe_after_restart(self, monkeypatch):
        """内存缓存清空（模拟重启）后应命中 Redis，不再发起网络探测。"""
        fake = self.FakeRedis()
        monkeypatch.setattr(url_probe, "get_redis_client", lambda: fake)

        calls = []

        async def false_probe(url):
            calls.append(url)
            return False

        monkeypatch.setattr(url_probe, "_probe", false_probe)

        url = "https://example.com/dead"
        assert await url_probe.is_browsable(url) is False
        assert fake.data[url_probe._redis_key(url)] == "0"
        assert fake.data[url_probe._redis_key(url) + ":ttl"] == url_probe.FAIL_TTL

        url_probe._cache.clear()
        assert await url_probe.is_browsable(url) is False
        assert calls == [url]  # 第二轮走 Redis，未再探测

    @pytest.mark.asyncio
    async def test_get_probe_cache_reads_redis_without_probing(self, monkeypatch):
        fake = self.FakeRedis()
        fake.data[url_probe._redis_key("https://example.com/dead")] = "0"
        monkeypatch.setattr(url_probe, "get_redis_client", lambda: fake)

        async def must_not_probe(url):
            raise AssertionError("缓存命中时不应发起探测")

        monkeypatch.setattr(url_probe, "_probe", must_not_probe)

        result = await url_probe.get_probe_cache(
            ["https://example.com/dead", "tianapi://douyinhot"]
        )
        assert result == {"https://example.com/dead": False}

    @pytest.mark.asyncio
    async def test_warm_probes_in_background_and_dedupes(self, monkeypatch):
        calls = []

        async def fake_browsable(url):
            calls.append(url)
            return True

        monkeypatch.setattr(url_probe, "is_browsable", fake_browsable)

        url_probe.warm(["https://example.com/a"])
        url_probe.warm(["https://example.com/a"])  # 同一 URL 不重复排队
        await asyncio.sleep(0.01)

        assert calls == ["https://example.com/a"]
        assert url_probe._warming == set()


class TestHelpers:
    def test_is_browser_url(self):
        assert url_probe.is_browser_url("https://example.com/a")
        assert url_probe.is_browser_url("http://example.com/a")
        assert not url_probe.is_browser_url("tianapi://douyinhot")
        assert not url_probe.is_browser_url("")
        assert not url_probe.is_browser_url(None)

    def test_bing_fallback_encodes_title(self):
        url = url_probe.bing_fallback("a b&c")
        assert url.startswith("https://www.bing.com/search?q=")
        assert " " not in url and "&c" not in url
