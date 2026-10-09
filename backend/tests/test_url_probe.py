"""url_probe 的 SSRF 过滤与兜底逻辑测试。"""

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
