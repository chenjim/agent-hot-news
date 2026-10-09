from datetime import datetime, timedelta, timezone

from app.models.models import Article, HotEvent, EventArticle, Source, SourceType, SourceStatus


class TestHotEventsAPI:
    def test_list_hot_events_empty(self, client):
        # Use a unique category to avoid cache hits from other tests
        response = client.get("/api/v1/hot-events?category=__empty_test__")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_hot_events_with_data(self, client, db):
        now = datetime.now(timezone.utc)
        # 列表按 aggregated_at 倒序（与卡片展示字段一致）。
        # 故意让 last_updated_at 与 aggregated_at 顺序相反：e2 最后更新、但 e1
        # 更早聚合，断言顺序必须由 aggregated_at 决定 —— 回退到 last_updated_at 会挂。
        e1 = HotEvent(
            title="Event 1", summary="S1", category="tech", hot_score=100.0,
            first_seen_at=now - timedelta(hours=3),
            last_updated_at=now - timedelta(hours=1),
            aggregated_at=now,
        )
        e2 = HotEvent(
            title="Event 2", summary="S2", category="finance", hot_score=50.0,
            first_seen_at=now, last_updated_at=now,
            aggregated_at=now - timedelta(hours=2),
        )
        db.add_all([e1, e2])
        db.commit()

        response = client.get("/api/v1/hot-events")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["title"] == "Event 1"
        assert data[1]["title"] == "Event 2"

    def test_list_excludes_unpublished_events(self, client, db):
        # 未达标（aggregated_at 为空）的事件不上列表 —— 即使 last_updated_at 很新
        now = datetime.now(timezone.utc)
        cat = "__unpublished_test__"
        db.add(HotEvent(
            title="Unpublished", summary="S", category=cat, hot_score=10.0,
            last_updated_at=now, aggregated_at=None,
        ))
        db.add(HotEvent(
            title="Published", summary="S", category=cat, hot_score=10.0,
            last_updated_at=now - timedelta(hours=5), aggregated_at=now,
        ))
        db.commit()

        data = client.get(f"/api/v1/hot-events?category={cat}").json()
        assert [e["title"] for e in data] == ["Published"]
        assert data[0]["aggregated_at"] is not None

    def test_list_excludes_events_outside_aggregation_window(self, client, db):
        # 7 天窗口按 aggregated_at 算：7 天前聚合、今天刚更新的事件不展示
        now = datetime.now(timezone.utc)
        cat = "__stale_aggregate_test__"
        db.add(HotEvent(
            title="Old Aggregate", summary="S", category=cat, hot_score=10.0,
            last_updated_at=now, aggregated_at=now - timedelta(days=8),
        ))
        db.commit()

        assert client.get(f"/api/v1/hot-events?category={cat}").json() == []

    def test_list_hot_events_filter_category(self, client, db):
        now = datetime.now(timezone.utc)
        e1 = HotEvent(title="Tech News", summary="S1", category="tech", hot_score=10.0, last_updated_at=now, aggregated_at=now)
        e2 = HotEvent(title="Finance News", summary="S2", category="finance", hot_score=20.0, last_updated_at=now, aggregated_at=now)
        db.add_all([e1, e2])
        db.commit()

        response = client.get("/api/v1/hot-events?category=tech")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Tech News"

    def test_list_hot_events_offset_pagination(self, client, db):
        now = datetime.now(timezone.utc)
        # 唯一分类名避开其它用例的缓存；aggregated_at 依次递减决定顺序
        cat = "__offset_test__"
        for i in range(5):
            db.add(HotEvent(
                title=f"Offset {i}", summary="S", category=cat,
                hot_score=float(i), last_updated_at=now,
                aggregated_at=now - timedelta(minutes=i),
            ))
        db.commit()

        page1 = client.get(f"/api/v1/hot-events?category={cat}&limit=2").json()
        page2 = client.get(f"/api/v1/hot-events?category={cat}&limit=2&offset=2").json()
        page3 = client.get(f"/api/v1/hot-events?category={cat}&limit=2&offset=4").json()

        assert [e["title"] for e in page1] == ["Offset 0", "Offset 1"]
        assert [e["title"] for e in page2] == ["Offset 2", "Offset 3"]
        assert [e["title"] for e in page3] == ["Offset 4"]

    def test_list_hot_events_limit_cap(self, client):
        assert client.get("/api/v1/hot-events?limit=300").status_code == 200
        assert client.get("/api/v1/hot-events?limit=301").status_code == 422

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


from app.seed import DEFAULT_SOURCES


class TestSeedSources:
    def test_default_finance_sources_present(self, db):
        from app.seed import seed_sources

        seed_sources(db)
        names = {s.name for s in db.query(Source).all()}
        assert "经济观察网" in names
        assert "FT中文网" in names

    def test_default_sources_count(self, db):
        from app.seed import seed_sources

        seed_sources(db)
        count = db.query(Source).count()
        assert count == len(DEFAULT_SOURCES)

    def test_default_sources_update_existing_config(self, db):
        from app.seed import seed_sources, DEFAULT_SOURCES

        existing = Source(
            name="FT中文网",
            type=SourceType.RSS,
            endpoint="https://www.ftchinese.com/rss/news",
            config={"language": "zh"},
        )
        db.add(existing)
        db.commit()

        seed_sources(db)
        db.refresh(existing)
        assert existing.config.get("proxy") == "http://127.0.0.1:7890"
        assert "headers" in existing.config


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


class TestAdminTaskLogs:
    def test_log_ids_stay_unique_after_rotation(self, client):
        from app.api.v1.endpoints import admin

        admin._TASK_LOGS.clear()
        for _ in range(admin._MAX_LOGS + 5):
            admin._append_log("test-task", "success")

        ids = [int(entry["id"]) for entry in admin._TASK_LOGS]
        assert len(admin._TASK_LOGS) == admin._MAX_LOGS
        assert len(ids) == len(set(ids))
        assert ids == sorted(ids)
