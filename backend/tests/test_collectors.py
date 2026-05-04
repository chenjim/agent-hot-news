import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.collectors.base import BaseCollector, RawArticle
from app.collectors.rss_collector import RSSCollector
from app.collectors.api_collector import APICollector
from app.collectors.manager import CollectorManager
from app.collectors.baidu_hot_collector import BaiduHotCollector
from app.collectors.github_trending_collector import GitHubTrendingCollector
from app.collectors.hackernews_collector import HackerNewsCollector
from app.collectors.juejin_collector import JuejinCollector
from app.collectors.zhihu_collector import ZhihuCollector
from app.collectors.weibo_hot_collector import WeiboHotCollector
from app.collectors.tianapi_collector import TianapiCollector
from app.models.models import Source, SourceType, SourceStatus


class DummyCollector(BaseCollector):
    async def fetch(self):
        return []


class TestBaseCollector:
    def test_normalize_url(self):
        collector = DummyCollector({"name": "test", "endpoint": "http://example.com"})

        assert collector._normalize_url("http://example.com/article?id=1") == "http://example.com/article"
        assert collector._normalize_url("http://example.com/article/") == "http://example.com/article"
        assert collector._normalize_url("  http://example.com/article?x=1  ") == "http://example.com/article"
        assert collector._normalize_url("https://site.com/path/?") == "https://site.com/path"


class TestRSSCollector:
    @pytest.mark.asyncio
    async def test_fetch_rss_success(self):
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Test Article</title>
              <link>http://example.com/article?track=1</link>
              <description>This is a test summary.</description>
              <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
            </item>
            <item>
              <title>Second Article</title>
              <link>http://example.com/second/</link>
              <pubDate>Tue, 02 Jan 2024 12:30:45 GMT</pubDate>
            </item>
          </channel>
        </rss>"""

        mock_response = MagicMock()
        mock_response.text = rss_xml
        mock_response.content = rss_xml.encode('utf-8')
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = RSSCollector({"name": "Test RSS", "endpoint": "http://example.com/rss"})

        with patch("app.collectors.rss_collector.httpx.AsyncClient", return_value=mock_client):
            articles = await collector.fetch()

        assert len(articles) == 2
        assert articles[0].title == "Test Article"
        assert articles[0].url == "http://example.com/article"
        assert articles[0].summary == "This is a test summary."
        assert articles[0].published_at == datetime(2024, 1, 1, 0, 0, 0)
        assert articles[0].source_name == "Test RSS"
        assert articles[0].source_url == "http://example.com/rss"

        assert articles[1].title == "Second Article"
        assert articles[1].url == "http://example.com/second"
        assert articles[1].published_at == datetime(2024, 1, 2, 12, 30, 45)

    @pytest.mark.asyncio
    async def test_fetch_rss_empty(self):
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel></channel></rss>"""

        mock_response = MagicMock()
        mock_response.text = rss_xml
        mock_response.content = rss_xml.encode('utf-8')
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = RSSCollector({"name": "Empty RSS", "endpoint": "http://example.com/empty"})

        with patch("app.collectors.rss_collector.httpx.AsyncClient", return_value=mock_client):
            articles = await collector.fetch()

        assert articles == []

    @pytest.mark.asyncio
    async def test_fetch_rss_failure(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))

        collector = RSSCollector({"name": "Bad RSS", "endpoint": "http://example.com/bad"})

        with patch("app.collectors.rss_collector.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Exception, match="RSS fetch failed for Bad RSS"):
                await collector.fetch()


class TestAPICollector:
    @pytest.mark.asyncio
    async def test_fetch_api_with_list_path(self):
        api_response = {
            "data": {
                "items": [
                    {"title": "Item 1", "url": "http://a.com/1", "score": 100, "created": "2024-01-01T12:00:00"},
                    {"title": "Item 2", "url": "http://a.com/2", "score": 200, "created": "2024-01-02T12:00:00"},
                ]
            }
        }

        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=api_response)
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        config = {
            "name": "Test API",
            "endpoint": "http://api.example.com/items",
            "config": {
                "list_path": "data.items",
                "field_mapping": {
                    "title": "title",
                    "url": "url",
                    "hot_score": "score",
                    "published_at": "created",
                },
            },
        }
        collector = APICollector(config)

        with patch("app.collectors.api_collector.httpx.AsyncClient", return_value=mock_client):
            articles = await collector.fetch()

        assert len(articles) == 2
        assert articles[0].title == "Item 1"
        assert articles[0].url == "http://a.com/1"
        assert articles[0].raw_hot_score == 100.0
        assert articles[0].published_at == datetime(2024, 1, 1, 12, 0, 0)
        assert articles[1].title == "Item 2"
        assert articles[1].raw_hot_score == 200.0
        assert articles[1].published_at == datetime(2024, 1, 2, 12, 0, 0)

    @pytest.mark.asyncio
    async def test_fetch_api_date_parsing(self):
        api_response = {
            "list": [
                {"title": "A", "url": "http://a.com", "date": "2024-03-15 08:30:00"},
                {"title": "B", "url": "http://b.com", "date": "2024-03-15T08:30:00"},
                {"title": "C", "url": "http://c.com", "date": "Fri, 15 Mar 2024 08:30:00"},
            ]
        }

        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=api_response)
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        config = {
            "name": "Date API",
            "endpoint": "http://api.example.com/list",
            "config": {
                "list_path": "list",
                "field_mapping": {
                    "title": "title",
                    "url": "url",
                    "published_at": "date",
                },
            },
        }
        collector = APICollector(config)

        with patch("app.collectors.api_collector.httpx.AsyncClient", return_value=mock_client):
            articles = await collector.fetch()

        assert len(articles) == 3
        # The first two formats are handled by str()[:19] matching
        assert articles[0].published_at == datetime(2024, 3, 15, 8, 30, 0)
        assert articles[1].published_at == datetime(2024, 3, 15, 8, 30, 0)
        # RFC 822 format is truncated by [:19] and cannot be parsed, so it falls back to None
        assert articles[2].published_at is None


class TestCollectorManager:
    def test_get_active_sources(self, db):
        s1 = Source(name="Active 1", type=SourceType.RSS, endpoint="http://a.com", status=SourceStatus.ACTIVE)
        s2 = Source(name="Paused 1", type=SourceType.API, endpoint="http://b.com", status=SourceStatus.PAUSED)
        s3 = Source(name="Active 2", type=SourceType.RSS, endpoint="http://c.com", status=SourceStatus.ACTIVE)
        db.add_all([s1, s2, s3])
        db.commit()

        manager = CollectorManager(db)
        active = manager.get_active_sources()

        assert len(active) == 2
        assert {s.name for s in active} == {"Active 1", "Active 2"}

    @pytest.mark.asyncio
    async def test_fetch_all_aggregates_results(self, db, monkeypatch):
        s1 = Source(name="Source A", type=SourceType.RSS, endpoint="http://a.com", status=SourceStatus.ACTIVE)
        s2 = Source(name="Source B", type=SourceType.API, endpoint="http://b.com", status=SourceStatus.ACTIVE)
        db.add_all([s1, s2])
        db.commit()

        async def mock_fetch(self):
            return [RawArticle(url=f"http://{self.name.lower().replace(' ', '')}.com/1", title=f"From {self.name}")]

        monkeypatch.setattr(RSSCollector, "fetch", mock_fetch)
        monkeypatch.setattr(APICollector, "fetch", mock_fetch)

        manager = CollectorManager(db)
        articles = await manager.fetch_all()

        assert len(articles) == 2
        titles = {a.title for a in articles}
        assert titles == {"From Source A", "From Source B"}

    @pytest.mark.asyncio
    async def test_fetch_all_skips_failed_source(self, db, monkeypatch):
        s1 = Source(name="Good", type=SourceType.RSS, endpoint="http://good.com", status=SourceStatus.ACTIVE)
        s2 = Source(name="Bad", type=SourceType.API, endpoint="http://bad.com", status=SourceStatus.ACTIVE)
        db.add_all([s1, s2])
        db.commit()

        async def good_fetch(self):
            return [RawArticle(url="http://good.com/1", title="Good")]

        async def bad_fetch(self):
            raise Exception("Boom")

        monkeypatch.setattr(RSSCollector, "fetch", good_fetch)
        monkeypatch.setattr(APICollector, "fetch", bad_fetch)

        manager = CollectorManager(db)
        articles = await manager.fetch_all()

        assert len(articles) == 1
        assert articles[0].title == "Good"

        db.refresh(s2)
        assert s2.status == SourceStatus.ERROR
        assert "Boom" in s2.last_error


class TestBaiduHotCollector:
    @pytest.mark.asyncio
    async def test_fetch_baidu_hot_success(self):
        html = """<html><body>
        <div class="category-wrap_iQLoo">
            <a class="img-wrapper_29V76" href="https://www.baidu.com/s?wd=%E6%B5%8B%E8%AF%95%E6%A0%87%E9%A2%98"></a>
            <div class="index_1Ew5p">1</div>
            <div class="hot-index_1Bl1a">1,234,567</div>
        </div>
        <div class="category-wrap_iQLoo">
            <a class="img-wrapper_29V76" href="https://www.baidu.com/s?wd=%E7%AC%AC%E4%BA%8C%E6%9D%A1"></a>
            <div class="index_1Ew5p">2</div>
            <div class="hot-index_1Bl1a">890123</div>
        </div>
        </body></html>"""

        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = BaiduHotCollector(
            {"name": "baidu_hot", "endpoint": "https://top.baidu.com/board?tab=realtime", "config": {"language": "zh"}}
        )

        with patch("app.collectors.baidu_hot_collector.httpx.AsyncClient", return_value=mock_client):
            with patch("app.collectors.baidu_hot_collector.settings") as mock_settings:
                mock_settings.BAIDU_COOKIE = "test=1"
                articles = await collector.fetch()

        assert len(articles) == 2
        assert articles[0].title == "测试标题"
        assert articles[0].raw_hot_score == 1234567.0
        assert articles[0].extra["rank"] == 1
        assert articles[1].title == "第二条"
        assert articles[1].raw_hot_score == 890123.0

    @pytest.mark.asyncio
    async def test_fetch_baidu_hot_empty(self):
        html = "<html><body></body></html>"
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = BaiduHotCollector(
            {"name": "baidu_hot", "endpoint": "https://top.baidu.com/board?tab=realtime", "config": {}}
        )

        with patch("app.collectors.baidu_hot_collector.httpx.AsyncClient", return_value=mock_client):
            with patch("app.collectors.baidu_hot_collector.settings") as mock_settings:
                mock_settings.BAIDU_COOKIE = ""
                articles = await collector.fetch()

        assert articles == []


class TestGitHubTrendingCollector:
    @pytest.mark.asyncio
    async def test_fetch_github_trending_stars_today(self):
        html = """<html><body>
        <article class="Box-row">
            <h2><a href="/owner/repo1">owner / repo1</a></h2>
            <p class="col-9 color-fg-muted">Description 1</p>
            <span class="d-inline-block float-sm-right">1,234 stars today</span>
        </article>
        <article class="Box-row">
            <h2><a href="/owner/repo2">owner / repo2</a></h2>
            <p class="col-9">Description 2</p>
            <a href="/owner/repo2/stargazers">5,678</a>
        </article>
        </body></html>"""

        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = GitHubTrendingCollector(
            {"name": "github_trending", "endpoint": "https://github.com/trending", "config": {"language": "en"}}
        )

        with patch("app.collectors.github_trending_collector.httpx.AsyncClient", return_value=mock_client):
            articles = await collector.fetch()

        assert len(articles) == 2
        assert articles[0].title == "owner/repo1"
        assert articles[0].raw_hot_score == 1234.0
        assert articles[0].summary == "Description 1"
        assert articles[1].title == "owner/repo2"
        assert articles[1].raw_hot_score == 5678.0
        assert articles[1].summary == "Description 2"

    @pytest.mark.asyncio
    async def test_fetch_github_trending_empty(self):
        mock_response = MagicMock()
        mock_response.text = "<html><body></body></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = GitHubTrendingCollector(
            {"name": "github_trending", "endpoint": "https://github.com/trending", "config": {}}
        )

        with patch("app.collectors.github_trending_collector.httpx.AsyncClient", return_value=mock_client):
            articles = await collector.fetch()

        assert articles == []


class TestHackerNewsCollector:
    @pytest.mark.asyncio
    async def test_fetch_hackernews_success(self):
        story_ids = [1, 2, 3]
        items = {
            1: {
                "type": "story", "title": "Story 1", "url": "http://example.com/1",
                "score": 100, "time": 1700000000, "descendants": 10, "by": "user1",
            },
            2: {"type": "comment", "text": "A comment"},
            3: {
                "type": "story", "title": "Story 3", "score": 50,
                "time": 1700000100, "descendants": 5, "by": "user3",
            },
        }

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "topstories.json" in str(url):
                resp.json = lambda: story_ids
            else:
                story_id = int(str(url).split("/")[-1].split(".")[0])
                resp.json = lambda sid=story_id: items.get(sid, {})
            return resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=mock_get)

        collector = HackerNewsCollector(
            {"name": "Hacker News", "endpoint": "https://hacker-news.firebaseio.com/v0/topstories.json", "config": {"language": "en"}}
        )

        with patch("app.collectors.hackernews_collector.httpx.AsyncClient", return_value=mock_client):
            articles = await collector.fetch()

        assert len(articles) == 2
        titles = [a.title for a in articles]
        assert "Story 1" in titles
        assert "Story 3" in titles
        assert articles[0].raw_hot_score == 100.0
        assert articles[0].extra["hn_id"] == 1
        assert articles[1].extra["hn_id"] == 3

    @pytest.mark.asyncio
    async def test_fetch_hackernews_self_post(self):
        """Self-posts without url should use HN discussion URL."""
        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "topstories.json" in str(url):
                resp.json = lambda: [42]
            else:
                resp.json = lambda: {
                    "type": "story", "title": "Ask HN", "score": 10,
                    "time": 1700000000, "descendants": 3, "by": "asker",
                }
            return resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=mock_get)

        collector = HackerNewsCollector(
            {"name": "Hacker News", "endpoint": "https://hacker-news.firebaseio.com/v0/topstories.json", "config": {}}
        )

        with patch("app.collectors.hackernews_collector.httpx.AsyncClient", return_value=mock_client):
            articles = await collector.fetch()

        assert len(articles) == 1
        assert articles[0].url == "https://news.ycombinator.com/item"


class TestJuejinCollector:
    @pytest.mark.asyncio
    async def test_fetch_juejin_success(self):
        api_data = {
            "data": [
                {
                    "item_info": {
                        "article_info": {
                            "title": "Article 1",
                            "article_id": "abc123",
                            "brief_content": "Summary 1",
                            "view_count": 1000,
                        }
                    }
                },
                {
                    "item_info": {
                        "article_info": {
                            "title": "Article 2",
                            "article_id": "def456",
                            "view_count": 500,
                        }
                    }
                },
            ]
        }

        mock_response = MagicMock()
        mock_response.json = lambda: api_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        collector = JuejinCollector(
            {"name": "juejin", "endpoint": "https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed", "config": {"language": "zh"}}
        )

        with patch("app.collectors.juejin_collector.httpx.AsyncClient", return_value=mock_client):
            articles = await collector.fetch()

        assert len(articles) == 2
        assert articles[0].title == "Article 1"
        assert articles[0].url == "https://juejin.cn/post/abc123"
        assert articles[0].summary == "Summary 1"
        assert articles[0].raw_hot_score == 1000.0
        assert articles[0].extra["rank"] == 1
        assert articles[1].raw_hot_score == 500.0


class TestZhihuCollector:
    @pytest.mark.asyncio
    async def test_fetch_zhihu_success(self):
        api_data = {
            "data": [
                {
                    "target": {
                        "title": "Question 1",
                        "url": "/question/1",
                        "excerpt": "Excerpt 1",
                    },
                    "detail_text": "1369 万热度",
                },
                {
                    "target": {
                        "title": "Question 2",
                        "url": "https://www.zhihu.com/question/2",
                        "detail": "Detail 2",
                    },
                    "detail_text": "5000",
                },
            ]
        }

        mock_response = MagicMock()
        mock_response.json = lambda: api_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = ZhihuCollector(
            {"name": "zhihu", "endpoint": "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=50", "config": {"language": "zh"}}
        )

        with patch("app.collectors.zhihu_collector.httpx.AsyncClient", return_value=mock_client):
            with patch("app.collectors.zhihu_collector.settings") as mock_settings:
                mock_settings.ZHIHU_COOKIE = "test=1"
                articles = await collector.fetch()

        assert len(articles) == 2
        assert articles[0].title == "Question 1"
        assert articles[0].url == "https://www.zhihu.com/question/1"
        assert articles[0].raw_hot_score == 13690000.0
        assert articles[0].extra["hot_text"] == "1369 万热度"
        assert articles[1].raw_hot_score == 5000.0
        assert articles[1].url == "https://www.zhihu.com/question/2"


class TestWeiboHotCollector:
    @pytest.mark.asyncio
    async def test_fetch_weibo_hot_success(self):
        html = """<html><body>
        <table><tbody>
            <tr><td class="ranktop">1</td><td><a href="/weibo?q=test1">Test 1</a></td><td><span>1000000</span></td></tr>
            <tr><td class="ranktop">2</td><td><a href="/weibo?q=test2">Test 2</a></td><td><span>500000</span></td></tr>
            <tr><td>not a rank</td><td><a href="/weibo?q=skip">Skip</a></td><td><span>1</span></td></tr>
        </tbody></table>
        </body></html>"""

        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = WeiboHotCollector(
            {"name": "weibo", "endpoint": "https://s.weibo.com/top/summary", "config": {"language": "zh"}}
        )

        with patch("app.collectors.weibo_hot_collector.httpx.AsyncClient", return_value=mock_client):
            with patch("app.collectors.weibo_hot_collector.settings") as mock_settings:
                mock_settings.WEIBO_COOKIE = "test=1"
                articles = await collector.fetch()

        assert len(articles) == 2
        assert articles[0].title == "Test 1"
        assert articles[0].raw_hot_score == 1000000.0
        assert articles[0].extra["rank"] == 1
        assert articles[1].title == "Test 2"
        assert articles[1].extra["rank"] == 2


class TestTianapiCollector:
    @pytest.mark.asyncio
    async def test_fetch_tianapi_newslist(self):
        api_data = {
            "code": 200,
            "newslist": [
                {"hotword": "Topic 1", "hotwordnum": "演出 1038974", "url": "http://a.com/1"},
                {"hotword": "Topic 2", "hotwordnum": " ", "url": "http://a.com/2"},
            ],
        }

        mock_response = MagicMock()
        mock_response.json = lambda: api_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = TianapiCollector(
            {"name": "tianapi_douyinhot", "endpoint": "https://apis.tianapi.com/douyinhot/index", "config": {"language": "zh"}}
        )

        mock_settings = MagicMock()
        mock_settings.TIANAPI_KEY = "test_key"

        with patch("app.collectors.tianapi_collector.httpx.AsyncClient", return_value=mock_client):
            with patch("app.collectors.tianapi_collector.get_settings", return_value=mock_settings):
                articles = await collector.fetch()

        assert len(articles) == 2
        assert articles[0].title == "Topic 1"
        assert articles[0].raw_hot_score == 1038974.0
        assert articles[0].url == "http://a.com/1"
        assert articles[1].title == "Topic 2"
        assert articles[1].raw_hot_score == 0.0

    @pytest.mark.asyncio
    async def test_fetch_tianapi_result_list(self):
        api_data = {
            "code": 200,
            "result": {
                "list": [
                    {"word": "Word 1", "hotindex": 500},
                    {"word": "Word 2", "hotindex": 300, "description": "Desc 2"},
                ]
            },
        }

        mock_response = MagicMock()
        mock_response.json = lambda: api_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = TianapiCollector(
            {"name": "tianapi_networkhot", "endpoint": "https://apis.tianapi.com/networkhot/index", "config": {}}
        )

        mock_settings = MagicMock()
        mock_settings.TIANAPI_KEY = "test_key"

        with patch("app.collectors.tianapi_collector.httpx.AsyncClient", return_value=mock_client):
            with patch("app.collectors.tianapi_collector.get_settings", return_value=mock_settings):
                articles = await collector.fetch()

        assert len(articles) == 2
        assert articles[0].title == "Word 1"
        assert articles[0].raw_hot_score == 500.0
        assert articles[1].summary == "Desc 2"

    @pytest.mark.asyncio
    async def test_fetch_tianapi_no_key(self):
        collector = TianapiCollector(
            {"name": "tianapi_test", "endpoint": "https://apis.tianapi.com/test/index", "config": {}}
        )

        mock_settings = MagicMock()
        mock_settings.TIANAPI_KEY = ""

        with patch("app.collectors.tianapi_collector.get_settings", return_value=mock_settings):
            with pytest.raises(Exception, match="TIANAPI_KEY not configured"):
                await collector.fetch()

    @pytest.mark.asyncio
    async def test_fetch_tianapi_error_code(self):
        api_data = {"code": 250, "msg": "API limit exceeded"}

        mock_response = MagicMock()
        mock_response.json = lambda: api_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = TianapiCollector(
            {"name": "tianapi_test", "endpoint": "https://apis.tianapi.com/test/index", "config": {}}
        )

        mock_settings = MagicMock()
        mock_settings.TIANAPI_KEY = "test_key"

        with patch("app.collectors.tianapi_collector.httpx.AsyncClient", return_value=mock_client):
            with patch("app.collectors.tianapi_collector.get_settings", return_value=mock_settings):
                with pytest.raises(Exception, match="API limit exceeded"):
                    await collector.fetch()
