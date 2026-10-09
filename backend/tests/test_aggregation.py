"""聚合改动 A/B/C 的测试。

A 标题硬合并 / B 向量召回 + LLM 归属 / C outlier 待定池
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai_pipeline.normalize import normalize_title
from app.ai_pipeline.router import EventRouter, RouteItem, RouteDecision
from app.ai_pipeline.pipeline import AIPipeline, _PendingItem
from app.models.models import Article, HotEvent, EventArticle
from app.core.config import get_settings

settings = get_settings()


def _now():
    return datetime.now(timezone.utc)


# ======================================================================
# A：标题归一化与硬合并
# ======================================================================
class TestNormalizeTitle:
    def test_strips_punctuation_and_width(self):
        assert normalize_title("郑钦文中网开门红！") == normalize_title("郑钦文中网开门红")
        assert normalize_title("ＡＩ 新闻，速览。") == normalize_title("AI新闻速览")

    def test_keeps_cjk_and_alnum(self):
        assert normalize_title("12306辟谣抢票传言") == "12306辟谣抢票传言"
        assert normalize_title("  空格 与\t换行 ") == "空格与换行"

    def test_empty_and_symbol_only(self):
        assert normalize_title(None) == ""
        assert normalize_title("") == ""
        assert normalize_title("。。。") == ""

    def test_different_titles_stay_different(self):
        assert normalize_title("张本智和1金1银收官") != normalize_title("张本智和私下搭讪传闻")


class TestMergeDuplicateEvents:
    def test_merges_same_normalized_title(self, db):
        """两个标题只差标点的事件应合并为一个，文章全并到保留方。"""
        now = _now()
        a1 = Article(title="T1", url="http://a", source_name="s1", fetched_at=now)
        a2 = Article(title="T2", url="http://b", source_name="s2", fetched_at=now)
        db.add_all([a1, a2])
        db.flush()

        keep = HotEvent(
            title="郑钦文中网开门红", articles_count=3, sources_count=2,
            last_updated_at=now, embedding_centroid=[1.0, 0.0],
        )
        dup = HotEvent(
            title="郑钦文中网开门红！", articles_count=2, sources_count=2,
            last_updated_at=now, embedding_centroid=[0.0, 1.0],
        )
        db.add_all([keep, dup])
        db.flush()
        db.add_all([
            EventArticle(event_id=keep.id, article_id=a1.id),
            EventArticle(event_id=dup.id, article_id=a2.id),
        ])
        db.commit()

        AIPipeline(db)._merge_duplicate_events()

        events = db.query(HotEvent).all()
        assert len(events) == 1
        assert events[0].id == keep.id
        assert events[0].articles_count == 2
        assert events[0].sources_count == 2
        links = db.query(EventArticle).all()
        assert len(links) == 2
        assert all(link.event_id == keep.id for link in links)

    def test_keeps_event_with_more_articles(self, db):
        """同名两事件保留文章更多的一条，即使它的 id 更大。"""
        now = _now()
        poor = HotEvent(title="同名", articles_count=1, sources_count=1,
                        last_updated_at=now, embedding_centroid=[1.0, 0.0])
        rich = HotEvent(title="同名。", articles_count=5, sources_count=3,
                        last_updated_at=now, embedding_centroid=[0.5, 0.5])
        db.add_all([poor, rich])
        db.commit()

        AIPipeline(db)._merge_duplicate_events()

        events = db.query(HotEvent).all()
        assert len(events) == 1
        assert events[0].id == rich.id

    def test_drops_shared_article_link(self, db):
        """两事件都挂着同一篇文章时，合并后只留一条连线。"""
        now = _now()
        art = Article(title="共享", url="http://shared", source_name="s",
                      fetched_at=now)
        other = Article(title="独有", url="http://other", source_name="s",
                        fetched_at=now)
        db.add_all([art, other])
        db.flush()

        e1 = HotEvent(title="同名", articles_count=2, sources_count=1,
                      last_updated_at=now, embedding_centroid=[1.0, 0.0])
        e2 = HotEvent(title="同名！", articles_count=2, sources_count=1,
                      last_updated_at=now, embedding_centroid=[1.0, 0.0])
        db.add_all([e1, e2])
        db.flush()
        db.add_all([
            EventArticle(event_id=e1.id, article_id=art.id),
            EventArticle(event_id=e2.id, article_id=art.id),
            EventArticle(event_id=e2.id, article_id=other.id),
        ])
        db.commit()

        AIPipeline(db)._merge_duplicate_events()

        events = db.query(HotEvent).all()
        assert len(events) == 1
        assert events[0].articles_count == 2
        links = db.query(EventArticle).all()
        assert len(links) == 2
        assert len({(l.event_id, l.article_id) for l in links}) == 2

    def test_different_titles_not_merged(self, db):
        now = _now()
        db.add_all([
            HotEvent(title="张本智和1金1银收官", articles_count=1, sources_count=1,
                     last_updated_at=now, embedding_centroid=[1.0, 0.0]),
            HotEvent(title="张本智和私下搭讪传闻", articles_count=1, sources_count=1,
                     last_updated_at=now, embedding_centroid=[0.9, 0.1]),
        ])
        db.commit()

        AIPipeline(db)._merge_duplicate_events()

        assert db.query(HotEvent).count() == 2


class TestTitleMatchPriority:
    """_resolve_event 的优先级：A 标题硬合并 > B LLM 归属 > 旧向量阈值。"""

    def _pending(self, key="cluster:0"):
        return _PendingItem(
            kind="cluster", key=key, embedding=[1.0, 0.0],
            article_indexes=[0], title="簇标题",
        )

    def test_title_match_beats_llm_decision(self, db):
        now = _now()
        by_title = HotEvent(title="同名事件", articles_count=2, sources_count=1,
                            last_updated_at=now, embedding_centroid=[0.1, 0.9])
        by_llm = HotEvent(title="另一个事件", articles_count=1, sources_count=1,
                          last_updated_at=now, embedding_centroid=[1.0, 0.0])
        db.add_all([by_title, by_llm])
        db.commit()

        pipeline = AIPipeline(db)
        title_index = pipeline._index_by_title([by_title, by_llm])
        got = pipeline._resolve_event(
            self._pending(), "同名事件", [1.0, 0.0],
            {"cluster:0": by_llm.id}, route_failed=False, title_index=title_index,
        )
        assert got is by_title

    def test_llm_decision_used_when_title_differs(self, db):
        now = _now()
        ev = HotEvent(title="目标事件", articles_count=1, sources_count=1,
                      last_updated_at=now, embedding_centroid=[0.1, 0.9])
        db.add(ev)
        db.commit()

        pipeline = AIPipeline(db)
        got = pipeline._resolve_event(
            self._pending(), "全新标题", [1.0, 0.0],
            {"cluster:0": ev.id}, route_failed=False, title_index={},
        )
        assert got is ev

    def test_llm_new_wins_over_high_vector_similarity(self, db):
        """判定层正常时以 LLM 为准 —— 相似度高也不回退到旧阈值。"""
        now = _now()
        ev = HotEvent(title="相关但不同", articles_count=1, sources_count=1,
                      last_updated_at=now, embedding_centroid=[1.0, 0.0])
        db.add(ev)
        db.commit()

        pending = self._pending()
        pending.best_sim = 0.90  # 模拟张本智和那类高分误并信号

        pipeline = AIPipeline(db)
        got = pipeline._resolve_event(
            pending, "全新标题", [1.0, 0.0],
            {"cluster:0": None}, route_failed=False, title_index={},
        )
        assert got is None

    def test_fallback_to_vector_when_router_down(self, db):
        """判定层故障才回退旧的 0.75 向量阈值路径。"""
        now = _now()
        ev = HotEvent(title="既有事件", articles_count=1, sources_count=1,
                      last_updated_at=now, embedding_centroid=[1.0, 0.0])
        db.add(ev)
        db.commit()

        pipeline = AIPipeline(db)
        got = pipeline._resolve_event(
            self._pending(), "全新标题", [1.0, 0.0],
            {}, route_failed=True, title_index={},
        )
        assert got is ev

    def test_no_fallback_when_title_misses_and_vector_below_threshold(self, db):
        now = _now()
        ev = HotEvent(title="远", articles_count=1, sources_count=1,
                      last_updated_at=now, embedding_centroid=[0.0, 1.0])
        db.add(ev)
        db.commit()

        pipeline = AIPipeline(db)
        got = pipeline._resolve_event(
            self._pending(), "全新标题", [1.0, 0.0],
            {}, route_failed=True, title_index={},
        )
        assert got is None


# ======================================================================
# B：召回 + LLM 归属
# ======================================================================
class TestRecall:
    def test_only_events_above_floor_become_candidates(self, db):
        now = _now()
        near = HotEvent(title="近", articles_count=1, sources_count=1,
                        last_updated_at=now, embedding_centroid=[1.0, 0.0])
        far = HotEvent(title="反向", articles_count=1, sources_count=1,
                       last_updated_at=now, embedding_centroid=[-1.0, 0.0])
        db.add_all([near, far])
        db.commit()

        close = _PendingItem(kind="noise", key="a1", embedding=[1.0, 0.0],
                             article_indexes=[0], title="t")
        away = _PendingItem(kind="noise", key="a2", embedding=[0.0, 1.0],
                            article_indexes=[1], title="t")

        candidates, title_index = AIPipeline(db)._recall([close, away], [near, far])

        assert "a1" in candidates
        assert "a2" not in candidates
        assert candidates["a1"][0][0] == near.id
        assert close.best_sim == pytest.approx(1.0)
        assert away.best_sim == pytest.approx(0.0)
        assert title_index[normalize_title("近")].id == near.id

    def test_top_k_limits_candidates(self, db):
        now = _now()
        events = [
            HotEvent(title=f"事件{i}", articles_count=1, sources_count=1,
                     last_updated_at=now, embedding_centroid=[1.0, float(i)])
            for i in range(10)
        ]
        db.add_all(events)
        db.commit()

        pending = _PendingItem(kind="noise", key="k", embedding=[1.0, 0.0],
                               article_indexes=[0], title="t")
        candidates, _ = AIPipeline(db)._recall([pending], events)

        assert len(candidates["k"]) <= settings.ROUTE_TOP_K

    def test_empty_window_returns_no_candidates(self):
        pending = _PendingItem(kind="noise", key="k", embedding=[1.0, 0.0],
                               article_indexes=[0], title="t")
        candidates, title_index = AIPipeline(MagicMock())._recall([pending], [])
        assert candidates == {}
        assert title_index == {}


class TestEventRouter:
    @pytest.mark.asyncio
    async def test_no_candidates_skips_llm_entirely(self):
        router = EventRouter()
        with patch.object(router, "_route_chunk", new=AsyncMock()) as chunk:
            result = await router.route(
                [RouteItem(key="k1", title="只有标题")], {}
            )
        chunk.assert_not_called()
        assert result == [RouteDecision(key="k1", event_id=None)]

    @pytest.mark.asyncio
    async def test_accepts_valid_event_id(self):
        router = EventRouter()
        with patch.object(
            router, "_route_chunk",
            new=AsyncMock(return_value={"k1": 42}),
        ):
            result = await router.route(
                [RouteItem(key="k1", title="条目")], {"k1": [(42, "候选事件")]}
            )
        assert result == [RouteDecision(key="k1", event_id=42)]

    @pytest.mark.asyncio
    async def test_rejects_event_id_not_in_candidates(self):
        """LLM 幻觉出的 id（不在该条目的召回集合里）必须被丢弃成"新事件"。"""
        router = EventRouter()
        items = [RouteItem(key="k1", title="条目")]
        candidates = {"k1": [(7, "候选七")]}
        raw = '{"decisions":[{"i":0,"event_id":999}]}'
        got = await self._chunk_with_llm(router, items, candidates, raw)
        assert got == {"k1": None}

    @pytest.mark.asyncio
    async def test_accepts_id_that_is_in_candidates(self):
        router = EventRouter()
        items = [RouteItem(key="k1", title="条目")]
        candidates = {"k1": [(7, "候选七")]}
        raw = '{"decisions":[{"i":0,"event_id":7}]}'
        got = await self._chunk_with_llm(router, items, candidates, raw)
        assert got == {"k1": 7}

    @staticmethod
    async def _chunk_with_llm(router, items, candidates, content):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"choices": [{"message": {"content": content}}]}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = resp

        with patch.object(router, "_wait_if_needed", new=AsyncMock()):
            with patch(
                "app.ai_pipeline.router.httpx.AsyncClient",
                return_value=mock_client,
            ):
                return await router._route_chunk(items, candidates)

    @pytest.mark.asyncio
    async def test_malformed_output_returns_none(self):
        router = EventRouter()
        items = [RouteItem(key="k1", title="条目")]
        candidates = {"k1": [(7, "候选七")]}
        got = await self._chunk_with_llm(router, items, candidates, "这不是 JSON")
        assert got is None

    @pytest.mark.asyncio
    async def test_llm_failure_propagates_as_none(self):
        router = EventRouter()
        items = [RouteItem(key="k1", title="条目")]
        candidates = {"k1": [(7, "候选七")]}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.side_effect = Exception("boom")

        with patch.object(router, "_wait_if_needed", new=AsyncMock()):
            # 重试退避的 sleep 在测试里没有意义，直接吃掉
            with patch("app.ai_pipeline.router.asyncio.sleep", new=AsyncMock()):
                with patch(
                    "app.ai_pipeline.router.httpx.AsyncClient",
                    return_value=mock_client,
                ):
                    got = await router._route_chunk(items, candidates)
        assert got is None

    def test_prompt_lists_candidates_per_item(self):
        items = [
            RouteItem(key="cluster:0", title="郑钦文中网开门红 / 郑钦文2比1施晗"),
            RouteItem(key="article:9", title="河北廊坊市地震", summary="震级4.1"),
        ]
        candidates = {
            "cluster:0": [(3686, "郑钦文中网开门红")],
            "article:9": [(3690, "地震速报"), (3691, "廊坊震感")],
        }
        text = EventRouter._format_items(items, candidates)
        assert "[0] 郑钦文中网开门红" in text
        assert "3686=郑钦文中网开门红" in text
        assert "[1] 河北廊坊市地震" in text
        assert "3690=地震速报 | 3691=廊坊震感" in text


# ======================================================================
# C：outlier 待定池
# ======================================================================
class TestNoisePendingPool:
    def _pending(self, article):
        return _PendingItem(
            kind="noise", key=f"article:{article.id}", embedding=[1.0, 0.0],
            article_indexes=[0], title=article.title,
        )

    def test_unrouted_article_stays_pending_until_aged_out(self, db):
        now = _now()
        art = Article(title="孤例标题", url="http://x", source_name="s1",
                      fetched_at=now)
        db.add(art)
        db.commit()

        pipeline = AIPipeline(db)
        pending = self._pending(art)

        for attempt in range(1, settings.ROUTE_MAX_ATTEMPTS + 1):
            pipeline._apply_noise(pending, [art], {})
            db.commit()
            db.refresh(art)
            assert art.route_attempts == attempt
            # 没被收编前必须留在未处理集合里，下轮才能继续判定
            assert art.is_processed is (attempt >= settings.ROUTE_MAX_ATTEMPTS)

        assert art.is_processed is True

    def test_routed_article_is_attached_and_processed(self, db):
        now = _now()
        art = Article(title="迟到的文章", url="http://late", source_name="s2",
                      fetched_at=now)
        # 事件里已有一篇 s1 的文章：跨来源才允许挂上去
        anchor = Article(title="锚点文章", url="http://anchor", source_name="s1",
                         fetched_at=now)
        db.add_all([art, anchor])
        db.flush()

        event = HotEvent(title="目标事件", articles_count=1, sources_count=1,
                         last_updated_at=now, embedding_centroid=[1.0, 0.0])
        db.add(event)
        db.flush()
        db.add(EventArticle(event_id=event.id, article_id=anchor.id))
        db.commit()
        art.route_attempts = 2
        db.commit()

        pipeline = AIPipeline(db)
        pipeline._apply_noise(self._pending(art), [art], {f"article:{art.id}": event.id})
        db.commit()
        db.refresh(art)
        db.refresh(event)

        assert art.is_processed is True
        assert art.route_attempts == 0
        assert event.articles_count == 2   # anchor + art
        assert event.sources_count == 2    # s1 + s2 跨来源
        # anchor + art 两条连线
        assert db.query(EventArticle).count() == 2


# ======================================================================
# D：同一来源不聚合（MIN_EVENT_SOURCES）
# ======================================================================
class TestCrossSourceOnly:
    """跨来源印证过的才算事件；同一来源的多条条目退待定池。"""

    @staticmethod
    def _mocked(pipeline, embed=None):
        async def _all_same(texts):
            # 向量个数必须与文本数一致，否则 run() 会按错位保护中断本轮
            return [[1.0, 0.0]] * len(texts)

        pipeline.embedding.embed_texts = AsyncMock(side_effect=embed or _all_same)
        pipeline.summarizer.summarize_cluster = AsyncMock(
            return_value={
                "title": "聚合事件", "summary": "摘要", "detail": "详情",
                "category": "other", "sentiment": "neutral", "entities": [],
            }
        )
        pipeline.router.route = AsyncMock(
            return_value=[RouteDecision(key="cluster:0", event_id=None)]
        )
        return pipeline

    def _two_articles(self, db, source_a, source_b, now=None):
        now = now or _now()
        a1 = Article(title="条目一", url="http://1", source_name=source_a,
                     fetched_at=now)
        a2 = Article(title="条目二", url="http://2", source_name=source_b,
                     fetched_at=now)
        db.add_all([a1, a2])
        db.commit()
        return [a1, a2]

    @pytest.mark.asyncio
    async def test_same_source_cluster_creates_no_event(self, db):
        """同一来源的两篇聚成一簇 → 不建事件，双双退回待定池。"""
        arts = self._two_articles(db, "tianapi_weibohot", "tianapi_weibohot")
        pipeline = self._mocked(AIPipeline(db))

        await pipeline.run(max_articles=100)

        db.expire_all()
        assert db.query(HotEvent).count() == 0
        for art in arts:
            db.refresh(art)
            assert art.is_processed is False   # 留在池里等跨源同主题
            assert art.route_attempts == 1

    @pytest.mark.asyncio
    async def test_cross_source_cluster_creates_event(self, db):
        """两篇来自不同来源 → 正常成事件并标记已处理，但只有 2 篇未达发布门槛。"""
        arts = self._two_articles(db, "baidu_hot", "toutiao")
        pipeline = self._mocked(AIPipeline(db))

        await pipeline.run(max_articles=100)

        db.expire_all()
        events = db.query(HotEvent).all()
        assert len(events) == 1
        assert events[0].sources_count == 2
        # 2 篇 < MIN_PUBLISH_ARTICLES，不打 aggregated_at → 不上首页
        assert events[0].aggregated_at is None
        for art in arts:
            db.refresh(art)
            assert art.is_processed is True
            assert art.route_attempts == 0

    @pytest.mark.asyncio
    async def test_three_article_cluster_published_with_timestamp(self, db):
        """3 篇跨源一簇成事件 → 创建即达标，aggregated_at 当场打上、可上首页。"""
        now = _now()
        arts = [
            Article(title=f"条目{i}", url=f"http://three/{i}", source_name=src,
                    fetched_at=now)
            for i, src in enumerate(("baidu_hot", "toutiao", "weibo"))
        ]
        db.add_all(arts)
        db.commit()

        pipeline = self._mocked(AIPipeline(db))
        await pipeline.run(max_articles=100)

        db.expire_all()
        events = db.query(HotEvent).all()
        assert len(events) == 1
        assert events[0].articles_count == 3
        assert events[0].sources_count == 3
        assert events[0].aggregated_at is not None

    @pytest.mark.asyncio
    async def test_same_source_cluster_ages_out(self, db):
        """同源簇连续 ROUTE_MAX_ATTEMPTS 轮不成事件后老化出池。"""
        arts = self._two_articles(db, "zhihu", "zhihu")

        for _ in range(settings.ROUTE_MAX_ATTEMPTS):
            pipeline = self._mocked(AIPipeline(db))
            await pipeline.run(max_articles=100)
            db.expire_all()

        assert db.query(HotEvent).count() == 0
        for art in arts:
            db.refresh(art)
            assert art.is_processed is True
            assert art.route_attempts == settings.ROUTE_MAX_ATTEMPTS

    @pytest.mark.asyncio
    async def test_same_source_cluster_attached_to_cross_source_event(self, db):
        """LLM 把同源簇判给一个已有多来源的事件 → 仍允许并入（合并后跨源）。"""
        now = _now()
        arts = self._two_articles(db, "google_news", "google_news", now)
        anchor_s1 = Article(title="别家报道", url="http://a1",
                            source_name="baidu_hot", fetched_at=now,
                            is_processed=True)
        anchor_s2 = Article(title="另一家报道", url="http://a2",
                            source_name="toutiao", fetched_at=now,
                            is_processed=True)
        db.add_all([anchor_s1, anchor_s2])
        db.flush()
        event = HotEvent(title="既有跨源事件", articles_count=2, sources_count=2,
                         last_updated_at=now, embedding_centroid=[1.0, 0.0])
        db.add(event)
        db.flush()
        db.add_all([
            EventArticle(event_id=event.id, article_id=anchor_s1.id),
            EventArticle(event_id=event.id, article_id=anchor_s2.id),
        ])
        db.commit()

        pipeline = self._mocked(AIPipeline(db))
        pipeline.router.route = AsyncMock(
            return_value=[RouteDecision(key="cluster:0", event_id=event.id)]
        )

        await pipeline.run(max_articles=100)

        db.expire_all()
        assert db.query(HotEvent).count() == 1
        db.refresh(event)
        assert event.articles_count == 4
        assert event.sources_count == 3   # baidu_hot + toutiao + google_news
        for art in arts:
            db.refresh(art)
            assert art.is_processed is True

    def test_outlier_refused_by_single_source_event(self, db):
        """事件本身只有同源文章时，再挂一篇同源的也不行 —— 事件仍是同源。"""
        now = _now()
        anchor = Article(title="锚点", url="http://anchor",
                         source_name="s1", fetched_at=now)
        art = Article(title="后来者", url="http://late", source_name="s1",
                      fetched_at=now)
        db.add_all([anchor, art])
        db.flush()
        event = HotEvent(title="单源事件", articles_count=1, sources_count=1,
                         last_updated_at=now, embedding_centroid=[1.0, 0.0])
        db.add(event)
        db.flush()
        db.add(EventArticle(event_id=event.id, article_id=anchor.id))
        db.commit()

        pending = _PendingItem(kind="noise", key=f"article:{art.id}",
                               embedding=[1.0, 0.0], article_indexes=[0],
                               title=art.title)
        AIPipeline(db)._apply_noise(
            pending, [art], {f"article:{art.id}": event.id}
        )
        db.commit()
        db.refresh(art)

        assert art.is_processed is False
        assert art.route_attempts == 1
        assert db.query(EventArticle).count() == 1   # 只有锚点那条连线

    @pytest.mark.asyncio
    async def test_switch_off_restores_unconditional_aggregation(self, db, monkeypatch):
        """MIN_EVENT_SOURCES=1 时回到旧的无条件聚合行为（可逆开关）。"""
        monkeypatch.setattr(settings, "MIN_EVENT_SOURCES", 1)
        now = _now()
        arts = [
            Article(title="同源一", url="http://1", source_name="s1",
                    fetched_at=now),
            Article(title="同源二", url="http://2", source_name="s1",
                    fetched_at=now),
        ]
        db.add_all(arts)
        db.commit()

        pending = _PendingItem(kind="cluster", key="cluster:0",
                               embedding=[1.0, 0.0], article_indexes=[0, 1],
                               title="簇标题")
        pipeline = AIPipeline(db)
        pipeline.summarizer.summarize_cluster = AsyncMock(
            return_value={"title": "同源事件", "summary": "摘要", "detail": "d",
                          "category": "other", "sentiment": "neutral",
                          "entities": []}
        )
        await pipeline._apply_cluster(
            pending, arts, [[1.0, 0.0], [1.0, 0.0]], {}, False, {}
        )

        db.expire_all()
        events = db.query(HotEvent).all()
        assert len(events) == 1
        assert events[0].sources_count == 1


# ======================================================================
# 端到端：A + B + C 串起来
# ======================================================================
class TestRunEndToEnd:
    @pytest.mark.asyncio
    async def test_same_title_cluster_and_noise_attach_to_one_event(self, db):
        """同批两簇 + 一篇 outlier：标题硬合并把两簇并成一个事件，
        outlier 由 LLM 归属挂上去，全程只留一个事件。"""
        now = _now()
        art_a = Article(title="郑钦文中网开门红", url="http://a",
                        source_name="baidu_hot", fetched_at=now)
        art_b = Article(title="郑钦文2比1施晗", url="http://b",
                        source_name="weibo", fetched_at=now)
        art_noise = Article(title="河北廊坊市地震", url="http://c",
                            source_name="baidu_hot", fetched_at=now)
        db.add_all([art_a, art_b, art_noise])
        db.commit()

        existing = HotEvent(
            title="郑钦文中网开门红", summary="已有事件", articles_count=1,
            sources_count=1, last_updated_at=now, embedding_centroid=[1.0, 0.0],
        )
        db.add(existing)
        db.commit()

        pipeline = AIPipeline(db)
        # 批内：art_a 与 art_b 聚成一簇；art_noise 是 outlier
        pipeline.embedding.embed_texts = AsyncMock(
            return_value=[[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]]
        )
        pipeline.summarizer.summarize_cluster = AsyncMock(
            return_value={
                "title": "郑钦文中网开门红", "summary": "郑钦文2比1取胜",
                "detail": "详情", "category": "other",
                "sentiment": "positive", "entities": ["郑钦文"],
            }
        )
        # 簇按 LLM 判"新"，outlier 判"归入既有事件" —— 用来证明 A 会压过 B
        pipeline.router.route = AsyncMock(
            return_value=[
                RouteDecision(key="cluster:0", event_id=None),
                RouteDecision(key=f"article:{art_noise.id}", event_id=existing.id),
            ]
        )

        await pipeline.run(max_articles=100)

        db.expire_all()
        events = db.query(HotEvent).all()
        # 只有一个事件：簇没被 LLM 判归属，是被标题硬合并（A）拉回去的
        assert len(events) == 1
        assert events[0].id == existing.id
        assert events[0].title == "郑钦文中网开门红"
        assert events[0].summary == "郑钦文2比1取胜"  # 簇摘要已写入

        linked = {
            l.article_id for l in db.query(EventArticle)
            .filter(EventArticle.event_id == existing.id).all()
        }
        assert art_a.id in linked
        assert art_noise.id in linked

        for art in (art_a, art_b, art_noise):
            db.refresh(art)
            assert art.is_processed is True
            assert art.route_attempts == 0

    @pytest.mark.asyncio
    async def test_noise_not_routed_goes_to_pending_pool(self, db):
        now = _now()
        art = Article(title="没人认领的标题", url="http://lonely",
                      source_name="s1", fetched_at=now)
        db.add(art)
        db.commit()

        pipeline = AIPipeline(db)
        pipeline.embedding.embed_texts = AsyncMock(return_value=[[0.0, 1.0]])
        pipeline.router.route = AsyncMock(
            return_value=[RouteDecision(key=f"article:{art.id}", event_id=None)]
        )

        await pipeline.run(max_articles=100)

        db.refresh(art)
        assert art.is_processed is False  # 留在待定池
        assert art.route_attempts == 1
        assert db.query(HotEvent).count() == 0


# ======================================================================
# E：发布门槛（MIN_PUBLISH_ARTICLES + aggregated_at 冻结）
# ======================================================================
class TestPublishThreshold:
    """满 MIN_PUBLISH_ARTICLES 篇且来源 ≥ MIN_EVENT_SOURCES 才打 aggregated_at；
    一旦打上永不刷新，首页排序/展示靠的就是这个稳定时间。"""

    @staticmethod
    def _summary(title="聚合事件"):
        return {
            "title": title, "summary": "摘要", "detail": "详情",
            "category": "other", "sentiment": "neutral", "entities": [],
        }

    @staticmethod
    def _articles(db, specs):
        now = _now()
        arts = [
            Article(title=title, url=url, source_name=src, fetched_at=now)
            for title, url, src in specs
        ]
        db.add_all(arts)
        db.commit()
        return arts

    @pytest.mark.asyncio
    async def test_create_below_threshold_has_no_timestamp(self, db):
        """只有 2 篇（未达标）→ 事件可建，但不打 aggregated_at，不上首页。"""
        arts = self._articles(db, [
            ("条目一", "http://1", "s1"),
            ("条目二", "http://2", "s2"),
        ])
        pipeline = AIPipeline(db)

        event = pipeline._create_event(arts, self._summary(), [1.0, 0.0], 10.0)
        db.commit()

        assert event.articles_count == 2
        assert event.aggregated_at is None

    @pytest.mark.asyncio
    async def test_third_article_stamps_then_freezes(self, db):
        """第 3 篇并入的瞬间打点；第 4 篇起时间不再变。"""
        arts = self._articles(db, [
            ("条目一", "http://1", "s1"),
            ("条目二", "http://2", "s2"),
        ])
        pipeline = AIPipeline(db)
        event = pipeline._create_event(arts, self._summary(), [1.0, 0.0], 10.0)
        db.commit()
        assert event.aggregated_at is None

        third = self._articles(db, [("条目三", "http://3", "s3")])
        pipeline._add_articles_to_event(event, third, centroid=[1.0, 0.0])
        db.commit()
        db.refresh(event)

        assert event.articles_count == 3
        stamped = event.aggregated_at
        assert stamped is not None

        fourth = self._articles(db, [("条目四", "http://4", "s4")])
        pipeline._add_articles_to_event(event, fourth, centroid=[1.0, 0.0])
        db.commit()
        db.refresh(event)

        assert event.articles_count == 4
        # 关键断言：追加报道不得刷新聚合时间，否则老事件又会跳回头条
        assert event.aggregated_at == stamped

    @pytest.mark.asyncio
    async def test_three_articles_single_source_not_published(self, db):
        """3 篇但全来自同一来源 → 不达标，aggregated_at 仍为空。"""
        arts = self._articles(db, [
            ("同源一", "http://1", "s1"),
            ("同源二", "http://2", "s1"),
            ("同源三", "http://3", "s1"),
        ])
        pipeline = AIPipeline(db)

        event = pipeline._create_event(arts, self._summary(), [1.0, 0.0], 10.0)
        db.commit()

        assert event.articles_count == 3
        assert event.sources_count == 1
        assert event.aggregated_at is None

    def test_merge_keeps_earlier_aggregated_at(self, db):
        """标题硬合并后取两边较早的聚合时间，合并不能让发布时刻变晚。"""
        now = _now()
        keep_arts = self._articles(db, [("同题报道", "http://k", "s1")])
        dup_arts = self._articles(db, [
            ("同题报道侧", "http://d1", "s2"),
            ("同题报道侧二", "http://d2", "s3"),
        ])

        keep = HotEvent(
            title="同题", articles_count=1, sources_count=1,
            last_updated_at=now, aggregated_at=now, embedding_centroid=[1.0, 0.0],
        )
        dup = HotEvent(
            title="同题！", articles_count=2, sources_count=2,
            last_updated_at=now, aggregated_at=now - timedelta(hours=2),
            embedding_centroid=[0.0, 1.0],
        )
        db.add_all([keep, dup])
        db.flush()
        db.add_all(
            [EventArticle(event_id=keep.id, article_id=a.id) for a in keep_arts]
            + [EventArticle(event_id=dup.id, article_id=a.id) for a in dup_arts]
        )
        db.commit()

        AIPipeline(db)._merge_event_into(keep, dup)
        db.commit()
        db.refresh(keep)

        assert db.query(HotEvent).filter(HotEvent.id == dup.id).count() == 0
        assert keep.articles_count == 3
        # SQLite 取回来的时间戳不带时区，比较前先归一到 UTC
        assert AIPipeline._ensure_utc(keep.aggregated_at) == now - timedelta(hours=2)
