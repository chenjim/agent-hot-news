"""x-opencode-session 请求头回归测试。

背景：OpenCode Go 网关（tok.h89.cn new-api 渠道的上游）强制要求该头，
缺失返回 400 MissingSessionID。曾因只在 base_url 含 opencode.ai 时才带头，
经 new-api 中转（tok.h89.cn）时判断不命中、头丢失而报错。
修复为统一带头；本文件防止条件判断被改回来，也防止会话 ID 变成一次性。
"""

from app.core.config import OPENCODE_SESSION_ID, llm_extra_headers


class TestLlmExtraHeaders:
    # 各类真实 base_url 都必须带头：OpenAI 官方、new-api 中转、Ollama、OpenRouter
    BASE_URLS = [
        "https://api.openai.com/v1",
        "https://tok.h89.cn/v1",
        "http://host.docker.internal:11434/v1",
        "https://openrouter.ai/api/v1",
    ]

    def test_always_include_session_header(self):
        for base in self.BASE_URLS:
            headers = llm_extra_headers(base)
            assert headers == {
                "x-opencode-session": OPENCODE_SESSION_ID
            }, f"base_url={base} 必须携带 x-opencode-session"

    def test_session_id_stable_within_process(self):
        # OpenCode 文档要求 stable session ID；进程内多次调用必须拿到同一个值，
        # 一次性随机值会破坏路由与 prompt 缓存。
        first = llm_extra_headers("https://tok.h89.cn/v1")["x-opencode-session"]
        second = llm_extra_headers("https://tok.h89.cn/v1")["x-opencode-session"]
        assert first == second
        assert first  # 非空

    def test_session_id_unique_across_generation(self):
        # OPENCODE_SESSION_ID 是进程级常量，重复调用不重新生成
        assert isinstance(OPENCODE_SESSION_ID, str)
        assert len(OPENCODE_SESSION_ID) > 0
