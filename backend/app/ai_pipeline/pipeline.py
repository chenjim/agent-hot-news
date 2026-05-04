from typing import List, Dict
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from loguru import logger

from app.models.models import Article, HotEvent, EventArticle, SourceStatus
from app.ai_pipeline.embedding import EmbeddingService
from app.ai_pipeline.clustering import ClusteringService
from app.ai_pipeline.summarizer import SummarizerService


class AIPipeline:
    def __init__(self, db: Session):
        self.db = db
        self.embedding = EmbeddingService()
        self.clustering = ClusteringService(eps=0.25, min_samples=2)
        self.summarizer = SummarizerService()

    async def run(self, max_articles: int = 500):
        """
        Main pipeline:
        1. Fetch unprocessed articles
        2. Compute embeddings
        3. Cluster articles
        4. For each cluster, summarize with LLM
        5. Save/update HotEvent records
        """
        articles = self._get_unprocessed_articles(max_articles)
        if not articles:
            logger.info("No unprocessed articles, skipping pipeline")
            return

        logger.info(f"AI Pipeline starting with {len(articles)} articles")

        # Step 1: Embed
        texts = [f"{a.title}\n{a.summary or ''}" for a in articles]
        logger.info(f"Embedding {len(texts)} texts...")
        embeddings = await self.embedding.embed_texts(texts)
        logger.info(f"Embedding complete, got {len(embeddings)} vectors")

        # Store embeddings
        for article, emb in zip(articles, embeddings):
            article.embedding = emb
        self.db.commit()

        # Step 2: Cluster
        logger.info("Clustering embeddings...")
        labels, clusters = self.clustering.cluster(embeddings)
        noise_count = labels.count(-1)
        logger.info(f"Clustering complete: {len(clusters)} clusters, {noise_count} outliers")

        # Mark outliers as processed but not in any event
        for idx, label in enumerate(labels):
            if label == -1:
                articles[idx].is_processed = True
        self.db.commit()

        # Step 3: For each cluster, summarize and create/update HotEvent
        for cluster_id, indices in clusters.items():
            cluster_articles = [articles[i] for i in indices]
            cluster_embeddings = [embeddings[i] for i in indices]
            logger.info(f"Processing cluster {cluster_id} with {len(cluster_articles)} articles")
            await self._process_cluster(cluster_articles, cluster_embeddings)

        logger.info("AI Pipeline complete")

    def _get_unprocessed_articles(self, limit: int) -> List[Article]:
        return (
            self.db.query(Article)
            .filter(Article.is_processed == False)
            .order_by(Article.fetched_at.desc())
            .limit(limit)
            .all()
        )

    async def _process_cluster(
        self,
        articles: List[Article],
        embeddings: List[List[float]],
    ):
        """Process a single cluster: summarize, compute score, save event."""
        titles = [a.title for a in articles]
        summaries = [a.summary or a.title for a in articles]

        # Summarize with LLM
        summary_result = await self.summarizer.summarize_cluster(titles, summaries)

        # Compute centroid
        centroid = self.clustering.compute_centroid(embeddings)

        # Compute hot score
        hot_score = self._compute_hot_score(articles)

        # Try to find existing similar event
        existing_event = self._find_similar_event(centroid)

        if existing_event:
            # Update existing event
            self._update_event(existing_event, articles, summary_result, centroid, hot_score)
        else:
            # Create new event
            self._create_event(articles, summary_result, centroid, hot_score)

        # Mark articles as processed
        for article in articles:
            article.is_processed = True
        self.db.commit()

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

    def _find_similar_event(self, centroid: List[float]) -> HotEvent:
        """Find an existing event with similar centroid."""
        recent_events = (
            self.db.query(HotEvent)
            .filter(HotEvent.last_updated_at >= datetime.now(timezone.utc) - timedelta(hours=48))
            .all()
        )

        best_match = None
        best_score = 0.75  # threshold

        for event in recent_events:
            if event.embedding_centroid:
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
    ):
        event = HotEvent(
            title=summary.get("title", "未知事件"),
            summary=summary.get("summary", ""),
            category=summary.get("category", "other"),
            hot_score=hot_score,
            sentiment=summary.get("sentiment", "neutral"),
            entities=summary.get("entities", []),
            articles_count=len(articles),
            sources_count=len(set(a.source_name for a in articles)),
            embedding_centroid=centroid,
        )
        self.db.add(event)
        self.db.flush()

        for article in articles:
            ea = EventArticle(event_id=event.id, article_id=article.id)
            self.db.add(ea)

        logger.info(f"Created new event: {event.title} (score={hot_score})")

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
        event.category = summary.get("category", event.category)
        event.hot_score = hot_score
        event.sentiment = summary.get("sentiment", event.sentiment)
        event.entities = summary.get("entities", event.entities)

        # Avoid N+1: bulk query existing articles instead of lazy-loading
        existing_eas = event.event_articles
        existing_article_ids = [ea.article_id for ea in existing_eas]
        existing_articles = (
            self.db.query(Article)
            .filter(Article.id.in_(existing_article_ids))
            .all()
        ) if existing_article_ids else []
        existing_sources = {a.source_name for a in existing_articles}

        # Add new article links (avoid duplicates)
        existing_ids = set(existing_article_ids)
        new_articles = [a for a in articles if a.id not in existing_ids]
        for article in new_articles:
            ea = EventArticle(event_id=event.id, article_id=article.id)
            self.db.add(ea)

        if new_articles:
            event.articles_count = len(existing_eas) + len(new_articles)
            event.sources_count = len(
                existing_sources | set(a.source_name for a in new_articles)
            )
            event.embedding_centroid = centroid
            event.last_updated_at = datetime.now(timezone.utc)
            logger.info(f"Updated event: {event.title} (score={hot_score}, +{len(new_articles)} articles)")
        else:
            logger.info(f"Event unchanged: {event.title} (no new articles)")
