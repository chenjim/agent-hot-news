"""AI 聚合流水线。

三处聚合改动（A/B/C）：

A  标题硬合并 —— 归一化标题相等即判定同一事件，不走向量。
   向量分数在"同事件 / 相关事件"上重叠（同事件实测低到 0.46，相关事件
   高到 0.89），阈值双向都会错；标题字面相等则是可确定性判定的强信号。
   两处生效：每轮开跑时合并历史同名事件（自愈），以及建事件前查同名。

B  向量只召回、LLM 判归属 —— 每个待归类条目召回 top-K 候选事件
   （宁宽勿严），由 LLM 判断它是否真的属于其中之一。LLM 不可用时
   回退到旧的 0.75 向量阈值路径，不让判定层故障拖垮整条流水线。

C  outlier 进待定池 —— 不再标记 is_processed 后永久丢弃，改为每轮
   重新参与归属判定，直到被某个事件收编，或重试满 ROUTE_MAX_ATTEMPTS
   轮后老化出池。这样"事件晚几轮才出现"的同主题文章还能被拉回来。
"""

from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session
from loguru import logger

from app.models.models import Article, HotEvent, EventArticle, SourceStatus
from app.ai_pipeline.embedding import EmbeddingService
from app.ai_pipeline.clustering import ClusteringService
from app.ai_pipeline.summarizer import SummarizerService
from app.ai_pipeline.router import EventRouter, RouteItem, RouteDecision, CandidateMap
from app.ai_pipeline.normalize import normalize_title
from app.core.config import get_settings

settings = get_settings()

# 摘要短于这个长度的不算有效上下文（热榜常见 "..."、"新事件上榜" 占位）
_MIN_MEANINGFUL_SUMMARY = 10


@dataclass
class _PendingItem:
    """本轮要判定归属的条目：一个 DBSCAN 簇，或一篇 outlier 文章。"""

    kind: str  # "cluster" | "noise"
    key: str
    embedding: List[float]
    article_indexes: List[int]  # 指向本轮 articles 列表的下标
    title: str
    summary: str = ""
    best_sim: float = 0.0


class AIPipeline:
    def __init__(self, db: Session):
        self.db = db
        self.embedding = EmbeddingService()
        self.clustering = ClusteringService(eps=0.20, min_samples=2)
        self.summarizer = SummarizerService()
        self.router = EventRouter()

    async def run(self, max_articles: int = 500):
        """
        Main pipeline:
        1. 合并窗口内历史同名事件（A）
        2. Fetch unprocessed articles
        3. Compute embeddings
        4. Cluster（批内压缩：一个簇 = 一次摘要调用）
        5. 向量召回 + LLM 归属判定（B）
        6. 逐簇 / 逐篇落库；outlier 进待定池（C）
        """
        # A：先自愈历史重复，否则重复事件会同时进召回候选干扰判定
        self._merge_duplicate_events()

        articles = self._get_unprocessed_articles(max_articles)
        if not articles:
            logger.info("No unprocessed articles, skipping pipeline")
            return

        logger.info(f"AI Pipeline starting with {len(articles)} articles")

        # Step 1: Embed
        texts = [f"{a.title}\n{a.summary or ''}" for a in articles]
        logger.info(f"Embedding {len(texts)} texts...")
        embeddings = await self.embedding.embed_texts(texts)
        if len(embeddings) != len(articles):
            # 长度不齐说明有文本被 embedding 服务静默丢弃，
            # 继续下去会让文章与向量错位，宁可中断本轮
            logger.error(
                f"Embedding count mismatch: {len(embeddings)} vectors for "
                f"{len(articles)} articles, aborting this pass"
            )
            return
        logger.info(f"Embedding complete, got {len(embeddings)} vectors")

        # Store embeddings
        for article, emb in zip(articles, embeddings):
            article.embedding = emb
        self.db.commit()

        # Step 2: Cluster —— 只负责批内压缩，不再承担跨轮归属判定
        logger.info("Clustering embeddings...")
        labels, clusters = self.clustering.cluster(embeddings)
        noise_count = list(labels).count(-1)
        logger.info(
            f"Clustering complete: {len(clusters)} clusters, {noise_count} outliers"
        )

        # Step 3: 归属判定 —— 窗口内事件读一次，向量召回，批量 LLM（B）
        window_events = self._window_events()
        pendings = self._build_pending_items(articles, labels, clusters, embeddings)
        candidates, title_index = self._recall(pendings, window_events)

        decisions: List[RouteDecision] = []
        route_failed = False
        if pendings:
            routed = await self.router.route(
                [
                    RouteItem(key=p.key, title=p.title, summary=p.summary)
                    for p in pendings
                ],
                candidates,
            )
            if routed is None:
                route_failed = True
                logger.warning("归属判定不可用，本轮回退到旧的向量阈值路径（0.75）")
            else:
                decisions = routed
        decision_by_key: Dict[str, Optional[int]] = {
            d.key: d.event_id for d in decisions
        }

        # Step 4: 落库
        for pending in pendings:
            if pending.kind == "cluster":
                await self._apply_cluster(
                    pending, articles, embeddings, decision_by_key,
                    route_failed, title_index,
                )
            else:
                self._apply_noise(pending, articles, decision_by_key)

        self.db.commit()
        logger.info("AI Pipeline complete")

    # ------------------------------------------------------------------
    # 取数
    # ------------------------------------------------------------------
    def _get_unprocessed_articles(self, limit: int) -> List[Article]:
        return (
            self.db.query(Article)
            .filter(Article.is_processed == False)
            .order_by(Article.fetched_at.desc())
            .limit(limit)
            .all()
        )

    def _window_events(self) -> List[HotEvent]:
        """回看窗口内的事件 —— A 的硬合并 / 标题匹配与 B 的召回共用一份。"""
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=settings.EVENT_MATCH_WINDOW_DAYS
        )
        return (
            self.db.query(HotEvent)
            .filter(HotEvent.last_updated_at >= cutoff)
            .order_by(HotEvent.last_updated_at.desc())
            .limit(500)
            .all()
        )

    # ------------------------------------------------------------------
    # A：标题硬合并
    # ------------------------------------------------------------------
    @staticmethod
    def _index_by_title(events: Sequence[HotEvent]) -> Dict[str, HotEvent]:
        """归一化标题 -> 事件。同名冲突保留文章更多的一条（信息更全）。"""
        index: Dict[str, HotEvent] = {}
        for ev in events:
            key = normalize_title(ev.title)
            if not key:
                continue
            cur = index.get(key)
            if cur is None or (ev.articles_count or 0) > (cur.articles_count or 0):
                index[key] = ev
        return index

    def _merge_duplicate_events(self) -> None:
        """把窗口内归一化标题相同的事件合成一个（每轮开跑自愈）。"""
        events = self._window_events()
        groups: Dict[str, List[HotEvent]] = {}
        for ev in events:
            key = normalize_title(ev.title)
            if key:
                groups.setdefault(key, []).append(ev)

        merged = 0
        for group in groups.values():
            if len(group) < 2:
                continue
            # 保留文章最多、其次 id 最小的（老 URL 更可能已被分享）
            group.sort(key=lambda e: (-(e.articles_count or 0), e.id))
            keep = group[0]
            for dup in group[1:]:
                logger.info(
                    f"标题硬合并: #{dup.id} {dup.title!r} -> #{keep.id} {keep.title!r}"
                )
                self._merge_event_into(keep, dup)
                merged += 1

        if merged:
            self.db.commit()
            logger.info(f"标题硬合并共处理 {merged} 个重复事件")

    def _merge_event_into(self, keep: HotEvent, dup: HotEvent) -> None:
        """把 dup 的文章并进 keep，然后删掉 dup。"""
        keep_ids = {
            row[0]
            for row in self.db.query(EventArticle.article_id)
            .filter(EventArticle.event_id == keep.id)
            .all()
        }
        dup_links = (
            self.db.query(EventArticle).filter(EventArticle.event_id == dup.id).all()
        )

        moved = 0
        for link in dup_links:
            if link.article_id in keep_ids:
                self.db.delete(link)  # 同一篇文章两边都有连线，去掉重复
            else:
                link.event = keep
                keep_ids.add(link.article_id)
                moved += 1

        # 先把连线变更落库，再删 dup：否则 SQLAlchemy 删除父行时会把
        # 尚未 flush、仍指向 dup 的子行外键置 NULL，覆盖掉上面的迁移
        self.db.flush()

        # 质心按文章数加权平均
        if keep.embedding_centroid is not None and dup.embedding_centroid is not None:
            kc = np.asarray(keep.embedding_centroid, dtype=np.float64)
            dc = np.asarray(dup.embedding_centroid, dtype=np.float64)
            if kc.shape == dc.shape:
                kw = max(1, keep.articles_count or 0)
                dw = max(1, dup.articles_count or 0)
                keep.embedding_centroid = ((kc * kw + dc * dw) / (kw + dw)).tolist()

        if keep_ids:
            rows = (
                self.db.query(Article.source_name)
                .filter(Article.id.in_(keep_ids))
                .all()
            )
            keep.sources_count = len({r[0] for r in rows})
        keep.articles_count = len(keep_ids)
        keep.last_updated_at = datetime.now(timezone.utc)
        # 合并后计数变化，可能首次达标；时间取两边较早的，合并不能让发布时刻变晚
        if keep.aggregated_at is None:
            keep.aggregated_at = dup.aggregated_at
        elif dup.aggregated_at is not None:
            keep.aggregated_at = min(
                self._ensure_utc(keep.aggregated_at),
                self._ensure_utc(dup.aggregated_at),
            )
        if keep.aggregated_at is None:
            self._stamp_aggregated(keep)
        self.db.delete(dup)
        logger.info(
            f"  并入 {moved} 篇文章，#{keep.id} 现有 {keep.articles_count} 篇 / "
            f"{keep.sources_count} 源"
        )

    # ------------------------------------------------------------------
    # B：召回
    # ------------------------------------------------------------------
    def _build_pending_items(
        self,
        articles: Sequence[Article],
        labels: Sequence[int],
        clusters: Dict[int, List[int]],
        embeddings: Sequence[List[float]],
    ) -> List[_PendingItem]:
        pendings: List[_PendingItem] = []

        for cluster_id, indexes in clusters.items():
            titles = [articles[i].title for i in indexes]
            summaries = [
                (articles[i].summary or "").strip()
                for i in indexes
                if len((articles[i].summary or "").strip()) >= _MIN_MEANINGFUL_SUMMARY
            ]
            pendings.append(
                _PendingItem(
                    kind="cluster",
                    key=f"cluster:{cluster_id}",
                    embedding=self.clustering.compute_centroid(
                        [embeddings[i] for i in indexes]
                    ),
                    article_indexes=list(indexes),
                    title=" / ".join(t[:80] for t in titles[:3]),
                    summary=" / ".join(s[:120] for s in summaries[:3]),
                )
            )

        for i, label in enumerate(labels):
            if label != -1:
                continue
            art = articles[i]
            summary = (art.summary or "").strip()
            pendings.append(
                _PendingItem(
                    kind="noise",
                    key=f"article:{art.id}",
                    embedding=embeddings[i],
                    article_indexes=[i],
                    title=art.title,
                    # 占位摘要（"..."、"新事件上榜"）不进 prompt，只会稀释判断
                    summary=summary if len(summary) >= _MIN_MEANINGFUL_SUMMARY else "",
                )
            )
        return pendings

    def _recall(
        self, pendings: Sequence[_PendingItem], window_events: Sequence[HotEvent]
    ) -> Tuple[CandidateMap, Dict[str, HotEvent]]:
        """向量召回：每个条目取相似度最高的前 K 个、且不低于召回下限的事件。

        这里只做召回、不做判定 —— 阈值卡的是"肯定不是"，不是"是"。
        同时返回归一化标题索引给 A 用。
        """
        title_index = self._index_by_title(window_events)
        # pgvector 的 VectorType 取出来是 np.ndarray，直接 if 会抛
        # "truth value of an array ... is ambiguous"，必须显式判 None
        events = [e for e in window_events if e.embedding_centroid is not None]
        if not pendings or not events:
            return {}, title_index

        # 逐条校验维度再堆叠：单条坏质心（如换模型前的残留）不该废掉整轮召回
        dim: Optional[int] = None
        vectors: List[np.ndarray] = []
        usable: List[HotEvent] = []
        for ev in events:
            try:
                arr = np.asarray(ev.embedding_centroid, dtype=np.float64).ravel()
            except (TypeError, ValueError):
                logger.warning(f"事件 #{ev.id} 质心无法解析为向量，跳过")
                continue
            if arr.size == 0:
                continue
            if dim is None:
                dim = arr.size
            if arr.size != dim:
                logger.warning(
                    f"事件 #{ev.id} 质心维度 {arr.size} != {dim}，跳过召回"
                )
                continue
            vectors.append(arr)
            usable.append(ev)

        if not usable:
            return {}, title_index

        matrix = np.vstack(vectors)
        norms = np.linalg.norm(matrix, axis=1)
        norms[norms == 0] = 1.0
        matrix = matrix / norms[:, None]
        ids = [e.id for e in usable]
        titles = [e.title for e in usable]

        candidates: Dict[str, Sequence[Tuple[int, str]]] = {}
        for pending in pendings:
            try:
                vec = np.asarray(pending.embedding, dtype=np.float64).ravel()
            except (TypeError, ValueError):
                continue
            if vec.shape[0] != matrix.shape[1]:
                logger.warning(
                    f"条目 {pending.key} 向量维度 {vec.shape[0]} 与事件质心 "
                    f"{matrix.shape[1]} 不一致，跳过召回"
                )
                continue
            n = np.linalg.norm(vec)
            if n == 0:
                continue
            sims = matrix @ (vec / n)
            pending.best_sim = float(sims.max())
            top = np.argsort(-sims)[: settings.ROUTE_TOP_K]
            picked = [
                (ids[i], titles[i])
                for i in top
                if sims[i] >= settings.ROUTE_RECALL_FLOOR
            ]
            if picked:
                candidates[pending.key] = picked
        return candidates, title_index

    # ------------------------------------------------------------------
    # 落库
    # ------------------------------------------------------------------
    async def _apply_cluster(
        self,
        pending: _PendingItem,
        articles: Sequence[Article],
        embeddings: Sequence[List[float]],
        decision_by_key: Dict[str, Optional[int]],
        route_failed: bool,
        title_index: Dict[str, HotEvent],
    ) -> None:
        indexes = pending.article_indexes
        cluster_articles = [articles[i] for i in indexes]
        cluster_embeddings = [embeddings[i] for i in indexes]
        titles = [a.title for a in cluster_articles]
        summaries = [a.summary or a.title for a in cluster_articles]
        logger.info(
            f"Processing {pending.key} with {len(cluster_articles)} articles"
        )

        summary_result = await self.summarizer.summarize_cluster(titles, summaries)
        centroid = self.clustering.compute_centroid(cluster_embeddings)
        hot_score = self._compute_hot_score(cluster_articles)

        cluster_sources = {a.source_name for a in cluster_articles}
        event = self._resolve_event(
            pending, summary_result.get("title"), centroid,
            decision_by_key, route_failed, title_index,
        )

        # 同一来源不聚合：新建事件前，以及并入已有事件后，都必须跨来源
        if event is None:
            blocked = len(cluster_sources) < settings.MIN_EVENT_SOURCES
            got_sources = cluster_sources
        else:
            got_sources = self._merged_sources(event, cluster_sources)
            blocked = len(got_sources) < settings.MIN_EVENT_SOURCES
        if blocked:
            logger.info(
                f"  同源不聚合: {pending.key} 来源 {sorted(cluster_sources)}，"
                f"并入后共 {len(got_sources)} 个来源（需 {settings.MIN_EVENT_SOURCES}），退待定池"
            )
            self._defer_to_pool(cluster_articles)
            self.db.commit()
            return

        if event is not None:
            self._reindex_title(event, title_index, summary_result.get("title"))
            self._update_event(
                event, cluster_articles, summary_result, centroid, hot_score
            )
        else:
            event = self._create_event(
                cluster_articles, summary_result, centroid, hot_score
            )
            self._index_created(event, title_index)

        for article in cluster_articles:
            article.is_processed = True
            article.route_attempts = 0
        self.db.commit()

    def _resolve_event(
        self,
        pending: _PendingItem,
        new_title: Optional[str],
        centroid: List[float],
        decision_by_key: Dict[str, Optional[int]],
        route_failed: bool,
        title_index: Dict[str, HotEvent],
    ) -> Optional[HotEvent]:
        """A（标题硬合并） > B（LLM 归属） > 旧向量阈值（仅判定层故障时）。"""
        # A
        event = self._find_by_title(new_title, title_index)
        if event is not None:
            logger.info(f"  命中标题硬合并 -> #{event.id} {event.title!r}")
            return event

        # B
        routed_id = decision_by_key.get(pending.key)
        if routed_id is not None:
            event = (
                self.db.query(HotEvent).filter(HotEvent.id == routed_id).first()
            )
            if event is not None:
                logger.info(f"  LLM 判归属 -> #{event.id} {event.title!r}")
                return event

        # 判定层故障才回退；判定层正常时以 LLM 的判断为准，
        # 但相似度异常高的分歧记一笔，方便事后审计
        if route_failed:
            event = self._find_similar_event(centroid)
            if event is not None:
                logger.info(f"  回退向量阈值 -> #{event.id} {event.title!r}")
            return event

        if pending.best_sim >= 0.75:
            logger.warning(
                f"  分歧审计: {pending.key} 最高召回相似度 "
                f"{pending.best_sim:.3f}，但 LLM 判为新事件"
            )
        return None

    def _find_by_title(
        self, title: Optional[str], title_index: Dict[str, HotEvent]
    ) -> Optional[HotEvent]:
        key = normalize_title(title)
        if not key:
            return None
        return title_index.get(key)

    @staticmethod
    def _index_created(event: HotEvent, title_index: Dict[str, HotEvent]) -> None:
        key = normalize_title(event.title)
        if key:
            title_index.setdefault(key, event)

    @staticmethod
    def _reindex_title(
        event: HotEvent, title_index: Dict[str, HotEvent], new_title: Optional[str]
    ) -> None:
        """事件标题被 LLM 改写后同步索引，避免旧标题还挂着这个事件。"""
        old_key = normalize_title(event.title)
        new_key = normalize_title(new_title)
        if old_key and old_key != new_key and title_index.get(old_key) is event:
            del title_index[old_key]
        if new_key:
            title_index.setdefault(new_key, event)

    def _apply_noise(
        self,
        pending: _PendingItem,
        articles: Sequence[Article],
        decision_by_key: Dict[str, Optional[int]],
    ) -> None:
        """C：outlier 不再立刻丢弃 —— 被收编则挂到事件上，否则进待定池。"""
        article = articles[pending.article_indexes[0]]
        routed_id = decision_by_key.get(pending.key)
        event = None
        if routed_id is not None:
            event = (
                self.db.query(HotEvent).filter(HotEvent.id == routed_id).first()
            )

        # 收编同样要跨来源：并进一个只有同源文章的事件，事件还是同源的
        if event is not None and len(
            self._merged_sources(event, {article.source_name})
        ) < settings.MIN_EVENT_SOURCES:
            logger.info(
                f"  同源不聚合: outlier #{article.id} 并入 #{event.id} 后仍只有 "
                f"{article.source_name} 一个来源，改判新事件"
            )
            event = None

        if event is not None:
            added = self._add_articles_to_event(event, [article])
            article.is_processed = True
            article.route_attempts = 0
            logger.info(
                f"  outlier #{article.id} {article.title!r} 归入事件 "
                f"#{event.id} {event.title!r} (+{added})"
            )
            return

        self._defer_to_pool([article])

    def _merged_sources(
        self, event: HotEvent, incoming: Iterable[str]
    ) -> set:
        """事件现有来源 ∪ 待并入来源（只读，不落库）—— 用于跨来源判定。"""
        rows = (
            self.db.query(Article.source_name)
            .join(EventArticle, EventArticle.article_id == Article.id)
            .filter(EventArticle.event_id == event.id)
            .distinct()
            .all()
        )
        return {r[0] for r in rows} | set(incoming)

    def _defer_to_pool(self, cluster_articles: Sequence[Article]) -> None:
        """不成事件的文章退回待定池：每轮 +1，满 ROUTE_MAX_ATTEMPTS 轮老化出池。"""
        for article in cluster_articles:
            attempts = (article.route_attempts or 0) + 1
            article.route_attempts = attempts
            if attempts >= settings.ROUTE_MAX_ATTEMPTS:
                article.is_processed = True
                logger.info(
                    f"  待定池老化出池: #{article.id} {article.title!r}"
                    f"（{attempts} 轮未被任何事件收编）"
                )
            else:
                logger.info(
                    f"  待定池保留: #{article.id} {article.title!r}"
                    f"（第 {attempts} 轮，下轮继续判定）"
                )

    # ------------------------------------------------------------------
    # 事件读写
    # ------------------------------------------------------------------
    @staticmethod
    def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
        """SQLite 存取回来的时间戳不带时区，比较前先归一到 UTC。"""
        if dt is not None and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _stamp_aggregated(self, event: HotEvent) -> Optional[datetime]:
        """首次达标时打上聚合发布时间；已打过则原样返回，绝不刷新。

        达标 = 文章数 ≥ MIN_PUBLISH_ARTICLES 且来源数 ≥ MIN_EVENT_SOURCES。
        这是 aggregated_at 唯一的正常写入口（硬合并路径另有取较早值的逻辑）。
        """
        if event.aggregated_at is not None:
            return event.aggregated_at
        if (event.articles_count or 0) < settings.MIN_PUBLISH_ARTICLES:
            return None
        if (event.sources_count or 0) < settings.MIN_EVENT_SOURCES:
            return None
        event.aggregated_at = datetime.now(timezone.utc)
        logger.info(
            f"  事件 #{event.id} 达到 {event.articles_count} 篇/"
            f"{event.sources_count} 源，发布并固定时间 {event.aggregated_at}"
        )
        return event.aggregated_at

    def _compute_hot_score(self, articles: List[Article]) -> float:
        """
        H = α·avg_raw_score + β·article_count + γ·source_diversity - δ·time_decay
        """
        now = datetime.now(timezone.utc)
        alpha, beta, gamma, delta = 0.3, 5.0, 10.0, 0.5

        avg_raw = sum(a.raw_hot_score for a in articles) / len(articles) if articles else 0
        count = len(articles)
        sources = len(set(a.source_name for a in articles))

        # Time decay based on newest article
        def _ensure_utc(dt):
            if dt is not None and dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        newest = max(
            (_ensure_utc(a.published_at) or _ensure_utc(a.fetched_at) for a in articles),
            default=now,
        )
        hours_old = max(0, (now - newest).total_seconds() / 3600)
        time_decay = hours_old * delta

        score = alpha * avg_raw + beta * count + gamma * sources - time_decay
        return round(max(0, score), 2)

    def _find_similar_event(self, centroid: List[float]) -> Optional[HotEvent]:
        """Find an existing event with similar centroid using pgvector cosine distance.

        仅在归属判定层不可用时使用（B 的回退路径）。
        """
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=settings.EVENT_MATCH_WINDOW_DAYS
        )

        if settings.DATABASE_URL.startswith("postgresql"):
            similar = (
                self.db.query(HotEvent)
                .filter(HotEvent.last_updated_at >= cutoff)
                .filter(HotEvent.embedding_centroid.isnot(None))
                .order_by(HotEvent.embedding_centroid.cosine_distance(centroid))
                .first()
            )
            if similar is None:
                return None
            sim = self.embedding.cosine_similarity(centroid, similar.embedding_centroid)
            return similar if sim > 0.75 else None
        else:
            # SQLite fallback: brute-force search
            recent_events = (
                self.db.query(HotEvent)
                .filter(HotEvent.last_updated_at >= cutoff)
                .all()
            )
            best_match = None
            best_score = 0.75
            for event in recent_events:
                # 同上：质心是 np.ndarray，不能直接 if
                if event.embedding_centroid is not None:
                    sim = self.embedding.cosine_similarity(centroid, event.embedding_centroid)
                    if sim > best_score:
                        best_score = sim
                        best_match = event
            return best_match

    def _create_event(
        self,
        articles: List[Article],
        summary: Dict,
        centroid: List[float],
        hot_score: float,
    ) -> HotEvent:
        # Deduplicate by (source_name, title) within the cluster before linking
        seen_source_titles = set()
        deduped_articles = []
        for a in articles:
            key = (a.source_name, a.title)
            if key not in seen_source_titles:
                seen_source_titles.add(key)
                deduped_articles.append(a)

        event = HotEvent(
            title=summary.get("title", "未知事件"),
            summary=summary.get("summary", ""),
            detail=summary.get("detail", ""),
            category=summary.get("category", "other"),
            hot_score=hot_score,
            sentiment=summary.get("sentiment", "neutral"),
            entities=summary.get("entities", []),
            articles_count=len(deduped_articles),
            sources_count=len(set(a.source_name for a in deduped_articles)),
            embedding_centroid=centroid,
        )
        self.db.add(event)
        self.db.flush()

        for article in deduped_articles:
            ea = EventArticle(event_id=event.id, article_id=article.id)
            self.db.add(ea)

        # 一个簇一次带来足量文章 → 创建即达标，直接打上聚合发布时间
        self._stamp_aggregated(event)

        logger.info(f"Created new event: {event.title} (score={hot_score})")
        return event

    def _add_articles_to_event(
        self,
        event: HotEvent,
        articles: List[Article],
        centroid: Optional[List[float]] = None,
    ) -> int:
        """把文章挂到已有事件上：只连线、重算计数，不覆盖事件摘要字段。

        返回新增连线数。
        """
        existing_links = (
            self.db.query(EventArticle)
            .filter(EventArticle.event_id == event.id)
            .all()
        )
        existing_article_ids = [link.article_id for link in existing_links]
        existing_articles = (
            self.db.query(Article)
            .filter(Article.id.in_(existing_article_ids))
            .all()
        ) if existing_article_ids else []
        existing_sources = {a.source_name for a in existing_articles}
        existing_source_titles = {(a.source_name, a.title) for a in existing_articles}

        # Deduplicate the incoming batch by (source_name, title) first
        seen_source_titles_batch = set()
        deduped_articles = []
        for a in articles:
            key = (a.source_name, a.title)
            if key not in seen_source_titles_batch:
                seen_source_titles_batch.add(key)
                deduped_articles.append(a)

        # Add new article links (avoid duplicates by id AND by source+title)
        existing_ids = set(existing_article_ids)
        new_articles = [
            a for a in deduped_articles
            if a.id not in existing_ids and (a.source_name, a.title) not in existing_source_titles
        ]
        for article in new_articles:
            self.db.add(EventArticle(event_id=event.id, article_id=article.id))

        if new_articles:
            event.articles_count = len(existing_links) + len(new_articles)
            event.sources_count = len(
                existing_sources | set(a.source_name for a in new_articles)
            )
            if centroid is not None:
                event.embedding_centroid = centroid
            event.last_updated_at = datetime.now(timezone.utc)
            # 首次跨过发布门槛才打点，之后这个值不再动
            self._stamp_aggregated(event)
        return len(new_articles)

    def _update_event(
        self,
        event: HotEvent,
        articles: List[Article],
        summary: Dict,
        centroid: List[float],
        hot_score: float,
    ):
        event.title = summary.get("title", event.title)
        event.summary = summary.get("summary", event.summary)
        event.detail = summary.get("detail", event.detail)
        event.category = summary.get("category", event.category)
        event.hot_score = hot_score
        event.sentiment = summary.get("sentiment", event.sentiment)
        event.entities = summary.get("entities", event.entities)

        added = self._add_articles_to_event(event, articles, centroid)
        if added:
            logger.info(
                f"Updated event: {event.title} (score={hot_score}, +{added} articles)"
            )
        else:
            logger.info(f"Event unchanged: {event.title} (no new articles)")
