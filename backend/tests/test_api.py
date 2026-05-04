from datetime import datetime, timedelta, timezone

from app.models.models import Article, HotEvent, EventArticle, Source, SourceType, SourceStatus


class TestHotEventsAPI:
    def test_list_hot_events_empty(self, client):
        response = client.get("/api/v1/hot-events")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_hot_events_with_data(self, client, db):
        now = datetime.now(timezone.utc)
        e1 = HotEvent(title="Event 1", summary="S1", category="tech", hot_score=100.0, last_updated_at=now)
        e2 = HotEvent(title="Event 2", summary="S2", category="finance", hot_score=50.0, last_updated_at=now)
        db.add_all([e1, e2])
        db.commit()

        response = client.get("/api/v1/hot-events")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["title"] == "Event 1"
        assert data[1]["title"] == "Event 2"

    def test_list_hot_events_filter_category(self, client, db):
        now = datetime.now(timezone.utc)
        e1 = HotEvent(title="Tech News", summary="S1", category="tech", hot_score=10.0, last_updated_at=now)
        e2 = HotEvent(title="Finance News", summary="S2", category="finance", hot_score=20.0, last_updated_at=now)
        db.add_all([e1, e2])
        db.commit()

        response = client.get("/api/v1/hot-events?category=tech")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Tech News"

    def test_get_hot_event_detail(self, client, db):
        now = datetime.now(timezone.utc)
        event = HotEvent(title="Detail Event", summary="Detailed", category="social", hot_score=75.0, last_updated_at=now)
        db.add(event)
        db.flush()

        article = Article(
            title="Article 1",
            url="http://example.com/1",
            source_name="Source A",
            source_url="http://source-a.com",
            published_at=now,
            raw_hot_score=5.0,
        )
        db.add(article)
        db.flush()

        ea = EventArticle(event_id=event.id, article_id=article.id)
        db.add(ea)
        db.commit()

        response = client.get(f"/api/v1/hot-events/{event.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Detail Event"
        assert len(data["timeline"]) == 1
        assert data["timeline"][0]["source"] == "Source A"
        assert len(data["sources"]) == 1
        assert data["sources"][0]["name"] == "Source A"
        assert data["sources"][0]["url"] == "http://example.com/1"

    def test_get_hot_event_not_found(self, client):
        response = client.get("/api/v1/hot-events/9999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Event not found"


class TestSourcesAPI:
    def test_create_source(self, client):
        payload = {
            "name": "Test Source",
            "type": "rss",
            "endpoint": "http://test.com/rss",
            "config": {"language": "zh"},
        }
        response = client.post("/api/v1/sources", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Source"
        assert data["type"] == "rss"
        assert data["status"] == "active"
        assert data["endpoint"] == "http://test.com/rss"

    def test_list_sources(self, client, db):
        s1 = Source(name="S1", type=SourceType.RSS, endpoint="http://s1.com")
        s2 = Source(name="S2", type=SourceType.API, endpoint="http://s2.com")
        db.add_all([s1, s2])
        db.commit()

        response = client.get("/api/v1/sources")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = {s["name"] for s in data}
        assert names == {"S1", "S2"}

    def test_update_source(self, client, db):
        source = Source(name="Old Name", type=SourceType.RSS, endpoint="http://old.com")
        db.add(source)
        db.commit()

        response = client.put(f"/api/v1/sources/{source.id}", json={"name": "New Name"})
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["endpoint"] == "http://old.com"

    def test_delete_source(self, client, db):
        source = Source(name="ToDelete", type=SourceType.RSS, endpoint="http://del.com")
        db.add(source)
        db.commit()

        response = client.delete(f"/api/v1/sources/{source.id}")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

        db.expire_all()
        assert db.query(Source).filter(Source.id == source.id).first() is None


class TestHealthAPI:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
