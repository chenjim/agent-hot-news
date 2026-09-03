# Agent Hot News — 需求文档

> AI 驱动的多源热点新闻实时检测与聚合展示系统

---

## 1. 项目概述

### 1.1 背景
信息过载时代，用户需要从海量新闻源中快速获取真正有价值的**热点事件**，而非简单的新闻列表。传统新闻聚合（如 RSS 阅读器）仅做罗列，缺乏**智能去重、热度评估、话题聚类**能力。

### 1.2 目标
构建一个端到端系统：
- **后端**：从多个新闻源实时采集 → AI 分析提取热点 → 聚合去重 → 提供 API
- **前端**：以视觉化、可交互的方式展示**汇总后的热点数据**，而非原始新闻流水

### 1.3 核心原则
- **来源广**：覆盖国内外主流新闻、社交媒体、垂直社区
- **AI 驱动**：不是简单排序，而是理解内容、聚类话题、评估热度
- **汇总展示**：用户看到的是"今天这 5 件大事"，而非 500 条新闻

---

## 2. 用户场景

| 角色 | 场景 | 需求 |
|------|------|------|
| 普通用户 | 早上想知道"昨天发生了什么大事" | 一眼看到 TOP 热点，带摘要和关键信源 |
| 媒体人 | 追踪某个话题的发酵过程 | 查看话题的时间线、热度趋势、相关报道 |
| 分析师 | 了解国内外舆论场差异 | 对比同一事件在不同来源的报道角度 |

---

## 3. 功能需求

### 3.1 数据采集层（Data Ingestion）

#### 3.1.1 新闻源覆盖（第一版至少覆盖以下类别）

| 类别 | 示例来源 | 采集方式 |
|------|----------|----------|
| **国内综合** | 新浪新闻、网易新闻、腾讯新闻、搜狐新闻 | RSS / API / 爬虫 |
| **国内聚合** | 今日头条热榜、百度热搜、微博热搜 | API /  unofficial 端点 |
| **科技互联网** | 36氪、虎嗅、IT之家、TechCrunch (EN) | RSS / API |
| **财经商业** | 经济观察网、FT中文网、财新、华尔街见闻、雪球 | RSS / API |
| **社交媒体** | Twitter/X Trending、Reddit Hot、Hacker News | 官方 API / RSS |
| **国际媒体** | BBC、Reuters、CNN、The Guardian | RSS / API |
| **开发者社区** | GitHub Trending、Dev.to、掘金热榜 | API / 爬虫 |
| **视频平台** | B站热门、YouTube Trending | API |

> **原则**：尽可能多。新增一个源的成本要低（配置化接入）。

#### 3.1.2 采集策略
- **定时拉取**：每 5-15 分钟轮询一次（不同源可配置不同频率）
- **增量采集**：只采集上次之后的新内容
- **容错机制**：单个源失败不影响整体，记录失败日志，自动重试
- **去重预过滤**：基于 URL 的精确去重，避免重复存储

#### 3.1.3 原始数据存储
- 原始抓取内容（标题、摘要、正文、发布时间、来源、URL）
- 原始热度指标（如微博的阅读量、评论数；HN 的 points 等）

---

### 3.2 AI 处理层（AI Pipeline）

这是系统的核心差异化能力。

#### 3.2.1 内容清洗与结构化
- 提取标题、正文、发布时间、作者
- 去除广告、导航栏等噪音
- 语言检测（中文 / 英文 / 其他）

#### 3.2.2 热点识别（Hot Event Detection）

**方案 A：Embedding + 聚类（推荐）**
1. 对每篇新闻计算文本 Embedding（如 OpenAI text-embedding-3 / 本地模型）
2. 基于相似度进行聚类（HDBSCAN / DBSCAN）
3. 一个 cluster 即代表一个"话题"
4. 话题热度 = cluster 内文章数 × 平均原始热度 × 时间衰减因子

**方案 B：LLM 总结提取**
- 对聚类后的文章，用 LLM 生成：
  - 话题标题（5 字内概括）
  - 一句话摘要
  - 关键实体（人物、地点、组织）
  - 情感倾向（正面 / 负面 / 中性）

#### 3.2.3 跨源关联（Cross-Source Linking）
- 识别不同来源报道的**同一事件**
- 建立关联图谱：事件 ←→ 多来源报道
- 计算报道多样性指数（来源越多 = 热度可信度越高）

#### 3.2.4 热度趋势计算
- 时间衰减：新发生的事件权重更高
- 原始热度加权：来源本身的热度指标（阅读量、点赞、评论）
- 传播速度：单位时间内新增报道数量
- 最终热度分：`H = α·原始热度 + β·传播速度 - γ·时间衰减`

#### 3.2.5 定时任务
- AI 处理流水线每 10-30 分钟运行一次
- 增量处理：只处理新采集的数据，更新已有话题

---

### 3.3 后端 API 层

提供 RESTful API 供前端消费。

#### 3.3.1 热点列表 API
```
GET /api/hot-events
Query: ?category=all|tech|finance|social|global&limit=20&timeframe=24h
Response:
[
  {
    "id": "evt_abc123",
    "title": "OpenAI 发布 GPT-5",
    "summary": "OpenAI 于今日凌晨发布新一代大模型 GPT-5，支持多模态推理...",
    "category": "tech",
    "hot_score": 96.5,
    "trend": "up",          // up | down | stable
    "sources_count": 12,    // 多少家媒体报道
    "articles_count": 35,   // 相关文章数
    "first_seen_at": "2026-04-28T02:00:00Z",
    "last_updated_at": "2026-04-28T18:00:00Z",
    "entities": ["OpenAI", "GPT-5", "Sam Altman"],
    "sentiment": "positive",
    "cover_image": "https://..."  // 可选：话题封面图
  }
]
```

#### 3.3.2 热点详情 API
```
GET /api/hot-events/:id
Response:
{
  ...基础字段同上,
  "timeline": [            // 时间线
    {"time": "02:00", "source": "TechCrunch", "title": "..."},
    {"time": "08:30", "source": "36氪", "title": "..."}
  ],
  "sources": [             // 各来源报道
    {"name": "TechCrunch", "url": "...", "title": "...", "hot_score": 89}
  ],
  "related_events": [      // 相关话题
    {"id": "evt_xyz", "title": "Google 反击发布 Gemini 2"}
  ]
}
```

#### 3.3.3 实时推送（可选 V2）
- WebSocket `/ws/hot-events`：新热点出现或排名大幅变化时主动推送
- 或 Server-Sent Events (SSE) 做轻量实时更新

#### 3.3.4 来源管理 API（管理后台）
```
GET    /api/sources       # 列出所有来源及其健康状态
POST   /api/sources       # 新增来源
PUT    /api/sources/:id   # 修改来源配置
DELETE /api/sources/:id   # 停用来源
```

---

### 3.4 前端展示层

**核心定位**：展示的是**AI 汇总后的热点数据**，不是原始新闻列表。

#### 3.4.1 页面结构

**首页 — 热点大盘**
- 顶部：实时时钟 + "最后更新于 3 分钟前"
- 核心区域：**TOP 热点卡片流**，按热度排序
  - 每张卡片：话题标题、一句话摘要、热度分、来源数、趋势箭头
  - 点击展开详情侧栏 / 跳转详情页
- 侧边/底部：分类筛选标签（全部 / 科技 / 财经 / 国际 / 社会）
- 可选：热度趋势迷你图（24h 内的热度变化曲线）

**详情页 — 事件深挖**
- 话题标题 + AI 生成摘要
- **传播时间线**：各来源报道的先后顺序
- **来源对比**：同一事件，国内媒体 vs 国外媒体怎么说（标题对比）
- **关键实体**：人物、地点、组织的高亮展示
- **相关话题**：底部推荐相似事件

#### 3.4.2 视觉要求（frontend-design 技能）
- **有设计感的深色/浅色主题**：不是 Bootstrap 默认白底
- **数据可视化**：热度分数用环形进度条、趋势用小折线图
- **动态效果**：新热点出现时的滑入动画、热度排名的实时换位动画
- **响应式**：桌面端三栏、平板两栏、移动端单栏

#### 3.4.3 实时感
- 页面标题显示当前热点数量（如"🔥 12 个正在发酵的热点"）
- 自动轮询刷新（每 60 秒），或 SSE 实时更新
- 新热点出现时有 toast 通知

---

## 4. 数据模型（初步）

```
Article（原始文章）
  - id, url, title, summary, content, source_name, source_url
  - published_at, fetched_at, raw_hot_score, language

HotEvent（AI 生成的话题/热点）
  - id, title, summary, category, hot_score, trend
  - sentiment, entities(JSON), articles_count, sources_count
  - first_seen_at, last_updated_at, cover_image

EventArticle（关联表：热点 ←→ 文章）
  - event_id, article_id, relevance_score

Source（来源配置）
  - id, name, type(rss|api|scraper), endpoint, config(JSON)
  - fetch_interval, status(active|error|paused), last_fetched_at
```

---

## 5. 技术栈建议

| 层级 | 推荐方案 | 备选 |
|------|----------|------|
| **后端语言** | Python (FastAPI / Flask) | Node.js + Express |
| **数据库** | PostgreSQL + Redis | MongoDB + Redis |
| **AI / Embedding** | OpenAI API / 通义千问 API | Ollama 本地模型 |
| **聚类** | sklearn (DBSCAN) + sentence-transformers | 纯 LLM 聚类 |
| **任务调度** | Celery + Redis | APScheduler |
| **前端框架** | React 19 + TypeScript | Vue 3 |
| **样式方案** | Tailwind CSS + shadcn/ui | 纯 Tailwind |
| **可视化** | Recharts / Tremor | D3.js |
| **部署** | Docker + Docker Compose | 云服务器原生部署 |

---

## 6. 非功能性需求

### 6.1 性能
- 热点列表 API 响应 < 200ms（走缓存）
- 前端首屏加载 < 1.5s
- 支持同时采集 20+ 来源，每日处理 5000+ 篇文章

### 6.2 可靠性
- 采集失败自动重试（指数退避）
- AI 处理失败可手动重跑
- 关键数据每日自动备份

### 6.3 成本控制
- Embedding 和 LLM 调用是主要成本，需要：
  - 缓存已计算的文章 Embedding
  - 对短文本优先使用轻量模型
  - 提供"本地模式"：用 Ollama 跑本地模型，零 API 成本

### 6.4 扩展性
- 新增来源只需配置，不改动代码
- AI 模型可替换（接口抽象）
- 前端支持多语言（预留 i18n）

---

## 7. 里程碑规划

### Phase 1 — MVP（2-3 周）
- [ ] 采集层：接入 5-8 个核心来源（微博热搜、36氪、HN、TechCrunch 等）
- [ ] AI 层：基础 Embedding + 聚类，生成话题标题和摘要
- [ ] API：热点列表 + 详情接口
- [ ] 前端：热点大盘页面，基础展示

### Phase 2 — 增强（2 周）
- [ ] 来源扩展到 15+
- [ ] 热度趋势图、时间线展示
- [ ] 来源对比功能
- [ ] 前端视觉升级（frontend-design）

### Phase 3 — 实时 & 高级（2 周）
- [ ] SSE / WebSocket 实时推送
- [ ] 情感分析、实体识别增强
- [ ] 管理后台（来源配置、任务监控）
- [ ] 本地模型支持（Ollama）

---

## 8. 风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| 来源反爬 / API 限制 | 数据采集不稳定 | 多源互补、降低频率、使用 RSS 优先 |
| AI API 成本高 | 运营成本 | Embedding 缓存、本地模型降级方案 |
| 聚类质量差（误合/漏分） | 热点识别不准 | 调参 + LLM 后校验 + 人工反馈回路 |
| 内容合规风险 | 法律问题 | 仅聚合标题+摘要、不存储全文、加免责声明 |

---

## 9. 成功指标

- 每日识别出 **20+ 有效热点事件**
- 热点覆盖的来源数 ≥ 3（跨源验证）
- 前端页面停留时长 > 2 分钟
- 采集成功率 > 95%

---

*文档版本: v1.0*
*更新日期: 2026-04-28*
