import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

from app.ai_pipeline.embedding import EmbeddingService
from app.ai_pipeline.clustering import ClusteringService
from app.ai_pipeline.summarizer import SummarizerService
from app.ai_pipeline.pipeline import AIPipeline
from app.models.models import Article, HotEvent, EventArticle


class TestEmbeddingService:
    @pytest.mark.asyncio
    async def test_embed_texts_empty(self):
        service = EmbeddingService()
        result = await service.embed_texts([])
        assert result == []

        result2 = await service.embed_texts(["", "   "])
        assert result2 == []

    @pytest.mark.asyncio
    async def test_embed_texts_mock(self):
        service = EmbeddingService()
        texts = ["hello", "world"]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"index": 0, "embedding": [0.1] * 1536},
                {"index": 1, "embedding": [0.2] * 1536},
            ]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_response

        with patch("app.ai_pipeline.embedding.httpx.AsyncClient", return_value=mock_client):
            result = await service.embed_texts(texts)

        assert len(result) == 2
        assert len(result[0]) == 1536
        assert result[0][0] == pytest.approx(0.1)
        assert result[1][0] == pytest.approx(0.2)

    def test_cosine_similarity(self):
        service = EmbeddingService()

        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert service.cosine_similarity(a, b) == pytest.approx(1.0)

        c = [0.0, 1.0, 0.0]
        assert service.cosine_similarity(a, c) == pytest.approx(0.0)

        d = [1.0, 1.0, 0.0]
        expected = 1.0 / np.sqrt(2)
        assert service.cosine_similarity(a, d) == pytest.approx(expected)


class TestClusteringService:
    def test_cluster_basic(self):
        embeddings = [
            [1.0, 0.0, 0.0],
            [0.99, 0.01, 0.0],
            [0.98, 0.02, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.99, 0.01],
            [0.0, 0.98, 0.02],
        ]
        service = ClusteringService(eps=0.25, min_samples=2)
        labels, clusters = service.cluster(embeddings)

        assert len(clusters) == 2
        assert all(lbl != -1 for lbl in labels)

    def test_cluster_noise(self):
        embeddings = [
            [1.0, 0.0, 0.0],
            [0.99, 0.01, 0.0],
            [0.0, 0.0, 1.0],  # isolated outlier
        ]
        service = ClusteringService(eps=0.25, min_samples=2)
        labels, clusters = service.cluster(embeddings)

        assert labels[2] == -1
        assert len(clusters) == 1

    def test_cluster_not_enough_samples(self):
        embeddings = [[1.0, 0.0, 0.0]]
        service = ClusteringService(eps=0.25, min_samples=2)
        labels, clusters = service.cluster(embeddings)

        assert labels == [-1]
        assert clusters == {}

    def test_compute_centroid(self):
        service = ClusteringService()
        embeddings = [
            [1.0, 2.0, 3.0],
            [3.0, 2.0, 1.0],
        ]
        centroid = service.compute_centroid(embeddings)
        assert centroid == pytest.approx([2.0, 2.0, 2.0])


class TestSummarizerService:
    @pytest.mark.asyncio
    async def test_summarize_cluster_mock(self):
        service = SummarizerService()
        mock_content = (
            '{"title": "AI News", "summary": "AI is great", "category": "tech", '
            '"sentiment": "positive", "entities": ["OpenAI"]}'
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": mock_content}}]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_response

        with patch("app.ai_pipeline.summarizer.httpx.AsyncClient", return_value=mock_client):
            result = await service.summarize_cluster(["Title 1"], ["Summary 1"])

        assert result["title"] == "AI News"
        assert result["summary"] == "AI is great"
        assert result["category"] == "tech"
        assert result["sentiment"] == "positive"
        assert result["entities"] == ["OpenAI"]

    @pytest.mark.asyncio
    async def test_summarize_cluster_fallback(self):
        service = SummarizerService()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.side_effect = Exception("API Error")

        with patch("app.ai_pipeline.summarizer.httpx.AsyncClient", return_value=mock_client):
            result = await service.summarize_cluster(["Fallback Title"], ["Fallback Summary"])

        assert result["title"] == "Fallback Title"
        assert result["summary"] == "Fallback Summary"
        assert result["category"] == "other"
        assert result["sentiment"] == "neutral"
        assert result["entities"] == []


class TestAIPipeline:
    def test_compute_hot_score(self, db):
        now = datetime.now(timezone.utc)
        articles = [
            Article(title="A", url="http://a.com", source_name="S1", raw_hot_score=10.0, fetched_at=now),
            Article(title="B", url="http://b.com", source_name="S2", raw_hot_score=20.0, fetched_at=now),
        ]
        pipeline = AIPipeline(db)
        score = pipeline._compute_hot_score(articles)

        # alpha*avg_raw + beta*count + gamma*sources - delta*time_decay
        # avg_raw = 15, count = 2, sources = 2, time_decay ≈ 0
        # 0.3*15 + 5.0*2 + 10.0*2 = 4.5 + 10 + 20 = 34.5
        assert score == pytest.approx(34.5, abs=0.1)

    def test_find_similar_event(self, db):
        now = datetime.now(timezone.utc)
        event = HotEvent(
            title="Existing",
            summary="Existing event",
            embedding_centroid=[0.1] * 1536,
            last_updated_at=now,
        )
        db.add(event)
        db.commit()

        pipeline = AIPipeline(db)

        with patch.object(EmbeddingService, "cosine_similarity", return_value=0.9):
            result = pipeline._find_similar_event([0.1] * 1536)

        assert result is not None
        assert result.id == event.id

    def test_create_event(self, db):
        now = datetime.now(timezone.utc)
        article = Article(title="New", url="http://new.com", source_name="S1", fetched_at=now)
        db.add(article)
        db.commit()

        pipeline = AIPipeline(db)
        summary = {
            "title": "Event",
            "summary": "Desc",
            "category": "tech",
            "sentiment": "positive",
            "entities": ["E1"],
        }
        centroid = [0.1] * 1536
        hot_score = 50.0

        pipeline._create_event([article], summary, centroid, hot_score)
        db.commit()

        event = db.query(HotEvent).first()
        assert event is not None
        assert event.title == "Event"
        assert event.hot_score == 50.0
        assert event.articles_count == 1
        assert event.sources_count == 1

        ea = db.query(EventArticle).first()
        assert ea.event_id == event.id
        assert ea.article_id == article.id

    def test_update_event(self, db):
        now = datetime.now(timezone.utc)
        article1 = Article(title="Old", url="http://old.com", source_name="S1", fetched_at=now)
        db.add(article1)
        db.flush()

        event = HotEvent(title="Original", summary="Orig", hot_score=10.0, embedding_centroid=[0.0] * 1536)
        db.add(event)
        db.flush()

        ea1 = EventArticle(event_id=event.id, article_id=article1.id)
        db.add(ea1)
        db.commit()

        article2 = Article(title="New", url="http://new.com", source_name="S2", fetched_at=now)
        db.add(article2)
        db.commit()

        pipeline = AIPipeline(db)
        summary = {
            "title": "Updated",
            "summary": "New Desc",
            "category": "finance",
            "sentiment": "negative",
            "entities": ["E2"],
        }
        centroid = [0.2] * 1536
        hot_score = 80.0

        pipeline._update_event(event, [article2], summary, centroid, hot_score)
        db.commit()

        db.refresh(event)
        assert event.title == "Updated"
        assert event.hot_score == 80.0
        assert event.category == "finance"
        assert event.sentiment == "negative"
        assert event.articles_count == 2
        assert event.sources_count == 2
