from .base import BaseCollector, RawArticle
from .rss_collector import RSSCollector
from .api_collector import APICollector
from .github_trending_collector import GitHubTrendingCollector
from .juejin_collector import JuejinCollector
from .zhihu_collector import ZhihuCollector
from .weibo_hot_collector import WeiboHotCollector
from .manager import CollectorManager

__all__ = [
    "BaseCollector",
    "RawArticle",
    "RSSCollector",
    "APICollector",
    "GitHubTrendingCollector",
    "JuejinCollector",
    "ZhihuCollector",
    "WeiboHotCollector",
    "CollectorManager",
]
