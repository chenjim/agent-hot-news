"""读写令牌鉴权 + 原文不入库的摘要层测试。"""

import pytest

from app.ai_pipeline.article_summarizer import (
    ORIGINAL_THRESHOLD,
    ArticleSummarizer,
    fold_content,
    is_original,
    original_text,
)
from app.collectors.base import RawArticle


def _raw(
    summary: str | None = None,
    content: str | None = None,
    url: str = "https://example.com/a1",
    title: str = "标题",
) -> RawArticle:
    return RawArticle(
        url=url,
        title=title,
        summary=summary,
        content=content,
        source_name="TestSource",
        source_url="https://example.com/feed",
    )


class TestReadToken:
    def test_missing_token_is_rejected(self, client):
        # client fixture 自带令牌头，这里显式清掉
        resp = client.get("/api/v1/hot-events", headers={"X-Read-Token": ""})
        assert resp.status_code == 401

    def test_wrong_token_is_rejected(self, client):
        resp = client.get("/api/v1/hot-events", headers={"X-Read-Token": "wrong"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Missing or invalid access token"

    def test_query_token_accepted(self, client):
        resp = client.get(
            "/api/v1/hot-events", headers={"X-Read-Token": ""}, params={"token": "test-read-token"}
        )
        assert resp.status_code == 200

    def test_bearer_token_accepted(self, client):
        resp = client.get(
            "/api/v1/articles",
            headers={"X-Read-Token": "", "Authorization": "Bearer test-read-token"},
        )
        assert resp.status_code == 200

    def test_read_token_does_not_grant_write(self, client):
        resp = client.post(
            "/api/v1/admin/trigger-fetch",
            headers={"X-Read-Token": "test-read-token", "X-Write-Token": ""},
        )
        assert resp.status_code == 401

    def test_admin_stats_requires_read_token(self, client):
        resp = client.get("/api/v1/admin/stats", headers={"X-Read-Token": ""})
        assert resp.status_code == 401

    def test_sources_get_requires_read_token(self, client):
        resp = client.get("/api/v1/sources", headers={"X-Read-Token": ""})
        assert resp.status_code == 401


class TestWriteToken:
    def test_missing_write_token_is_rejected(self, client):
        resp = client.post(
            "/api/v1/sources",
            json={"name": "X", "type": "rss", "endpoint": "http://x"},
            headers={"X-Write-Token": ""},
        )
        assert resp.status_code == 401

    def test_write_token_accepted(self, client):
        resp = client.post(
            "/api/v1/sources",
            json={"name": "Auth Source", "type": "rss", "endpoint": "http://auth.test/rss"},
            headers={"X-Write-Token": "test-write-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Auth Source"

    def test_delete_requires_write_token(self, client):
        resp = client.delete("/api/v1/sources/99999", headers={"X-Write-Token": ""})
        assert resp.status_code == 401

    def test_write_token_query_is_rejected(self, client):
        # 写接口不接受 query 令牌，避免令牌进访问日志
        resp = client.post(
            "/api/v1/sources",
            json={"name": "Q", "type": "rss", "endpoint": "http://q.test/rss"},
            headers={"X-Write-Token": ""},
            params={"token": "test-write-token"},
        )
        assert resp.status_code == 401

    def test_health_is_open(self, client):
        resp = client.get("/health", headers={"X-Read-Token": "", "X-Write-Token": ""})
        assert resp.status_code == 200


class TestArticleSummarizerRules:
    def test_long_content_triggers_summarize(self):
        assert is_original(_raw(content="文" * (ORIGINAL_THRESHOLD + 1)))

    def test_short_content_passes_through(self):
        assert not is_original(_raw(content="短描述"))

    def test_fold_content_moves_short_text_into_summary(self):
        raw = _raw(summary="导语", content="短正文")
        out = fold_content(raw)
        assert out.content is None
        assert out.summary == "导语\n\n短正文"

    @pytest.mark.asyncio
    async def test_process_folds_short_content_without_llm(self, monkeypatch):
        async def boom(_self, title, text):
            raise AssertionError("短文本不应调用 LLM")

        monkeypatch.setattr(ArticleSummarizer, "summarize_text", boom)
        out = await ArticleSummarizer().process([_raw(content="短描述")])
        assert len(out) == 1
        assert out[0].content is None
        assert out[0].summary == "短描述"

    def test_long_summary_triggers_summarize(self):
        assert is_original(_raw(summary="字" * (ORIGINAL_THRESHOLD + 1)))

    def test_short_summary_passes_through(self):
        assert not is_original(_raw(summary="短标题式摘要"))

    def test_hotlist_item_passes_through(self):
        assert not is_original(_raw(summary=None, content=None))

    def test_original_text_joins_summary_and_content(self):
        raw = _raw(summary="导语", content="正文")
        assert original_text(raw) == "导语\n\n正文"

    def test_original_text_truncates_at_safety_valve(self, monkeypatch):
        import app.ai_pipeline.article_summarizer as mod

        monkeypatch.setattr(mod, "MAX_INPUT_CHARS", 10)
        assert len(original_text(_raw(summary="一" * 100))) == 10

    @pytest.mark.asyncio
    async def test_process_replaces_content_with_llm_summary(self, monkeypatch):
        raw = _raw(content="原文正文" * 100)

        async def fake_summarize(_self, title, text):
            assert "原文正文" in text  # 原文完整进入 prompt
            return "AI 摘要"

        monkeypatch.setattr(ArticleSummarizer, "summarize_text", fake_summarize)
        out = await ArticleSummarizer().process([raw, _raw(summary=None, content=None)])
        assert len(out) == 2
        summarized = next(a for a in out if a.content is None and a.summary == "AI 摘要")
        assert summarized.content is None

    @pytest.mark.asyncio
    async def test_process_drops_item_when_summarize_fails(self, monkeypatch):
        raw = _raw(content="原文正文" * 100)

        async def fake_fail(_self, title, text):
            return None

        monkeypatch.setattr(ArticleSummarizer, "summarize_text", fake_fail)
        out = await ArticleSummarizer().process([raw])
        assert out == []

    @pytest.mark.asyncio
    async def test_process_skips_known_items_without_llm(self, monkeypatch):
        """已在库的原文条目跳过 LLM，但仍保留在输出里供落库更新。"""

        async def boom(_self, title, text):
            raise AssertionError("已在库的条目不应调用 LLM")

        monkeypatch.setattr(ArticleSummarizer, "summarize_text", boom)
        out = await ArticleSummarizer().process(
            [_raw(content="原文正文" * 100)], is_known=lambda _raw: True
        )
        assert len(out) == 1
        assert out[0].content is None  # 原文仍不落库

    @pytest.mark.asyncio
    async def test_process_dedupes_originals_within_batch(self, monkeypatch):
        """同一批里重复的原文条目只调一次 LLM。"""
        calls = []

        async def fake_summarize(_self, title, text):
            calls.append(title)
            return "AI 摘要"

        monkeypatch.setattr(ArticleSummarizer, "summarize_text", fake_summarize)
        a1 = _raw(content="原文正文" * 100, url="http://x/1", title="同题")
        a2 = _raw(content="原文正文" * 100, url="http://x/1", title="同题")
        out = await ArticleSummarizer().process([a1, a2])
        assert len(calls) == 1
        assert len(out) == 2
