# Agent Hot News

AI 驱动的多源热点新闻实时检测与聚合展示系统。

## 核心特性

- **多源采集**：RSS、API、爬虫配置化接入，覆盖科技、财经、国际、社交媒体
- **AI 热点识别**：Embedding 向量聚类 + LLM 总结提取，自动发现"今天这 5 件大事"
- **热度计算**：原始热度 × 传播速度 × 来源多样性 - 时间衰减
- **汇总展示**：前端展示 AI 聚合后的热点事件，非原始新闻列表
- **管理后台**：可视化监控统计、来源 CRUD、手动触发采集与 AI 处理
- **SSE 实时推送**：新热点事件和排名大幅变动时，前端自动收到实时通知

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.12 + FastAPI + SQLAlchemy + APScheduler |
| 数据库 | PostgreSQL + Redis |
| AI | OpenAI Embedding + GPT / 兼容本地 Ollama |
| 前端 | React 18 + TypeScript + Tailwind CSS + SWR |
| 部署 | Docker Compose |

## 快速启动

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
```

### 2. Docker Compose 启动

```bash
docker-compose up --build
```

- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`
- 管理后台：`http://localhost:3000/admin`

### 3. 本地开发（不依赖 Docker）

**后端：**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**前端：**
```bash
cd frontend
npm install
npm run dev
```

## 系统架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│  新闻源      │────▶│  采集器      │────▶│  Article (PG)   │
│ RSS/API/爬虫 │     │ Collector   │     │ 原始文章表       │
└─────────────┘     └─────────────┘     └─────────────────┘
                                                │
                                                ▼
                                      ┌─────────────────┐
                                      │  AI Pipeline    │
                                      │ 1. Embedding    │
                                      │ 2. DBSCAN 聚类   │
                                      │ 3. LLM 总结     │
                                      │ 4. 热度评分     │
                                      └─────────────────┘
                                                │
                                                ▼
                                      ┌─────────────────┐
                                      │  HotEvent (PG)  │
                                      │ 聚合热点事件表   │
                                      └─────────────────┘
                                                │
                    ┌───────────────────────────┘
                    ▼
          ┌─────────────────┐
          │  FastAPI        │
          │  /api/v1/hot-events
          │  /api/v1/admin/*
          │  /api/v1/sse/*
          └─────────────────┘
                    │
                    ▼
          ┌─────────────────┐
          │  React +        │
          │  Tailwind       │
          │  热点大盘        │
          │  管理后台        │
          └─────────────────┘
```

## 项目结构

```
agent-hot-news/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # REST API
│   │   ├── collectors/         # 多源采集器
│   │   ├── ai_pipeline/        # Embedding + 聚类 + LLM
│   │   ├── models/             # SQLAlchemy 数据模型
│   │   ├── scheduler/          # 定时任务
│   │   ├── core/               # 配置
│   │   ├── cache/              # Redis 缓存装饰器
│   │   ├── database.py         # 数据库连接
│   │   ├── main.py             # FastAPI 入口
│   │   └── seed.py             # 默认来源种子
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/         # UI 组件
│   │   ├── pages/              # 页面
│   │   ├── hooks/              # API hooks (SWR)
│   │   ├── types/              # TypeScript 类型
│   │   └── lib/                # 工具函数
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── docs/
    ├── requirement.md          # 需求文档
    └── CODE_REVIEW.md          # 代码审查报告
```

## 内置新闻源

系统启动时会自动种子化以下来源：

| 来源 | 类型 | 语言 | 说明 |
|------|------|------|------|
| 36氪 | RSS | 中文 | 科技创业媒体 |
| Hacker News | API | 英文 | 全球技术社区热帖 |
| TechCrunch | RSS | 英文 | 国际科技媒体 |
| Solidot | RSS | 中文 | 开源/科技资讯 |
| GitHub Trending | 爬虫 | 英文 | GitHub 当日趋势仓库 |
| 掘金 | API | 中文 | 技术社区推荐文章 |
| 知乎 | API | 中文 | 知乎全站热榜 |
| 微博热搜 | 爬虫 | 中文 | 微博实时热搜榜 |

## API 概览

### 热点事件
- `GET /api/v1/hot-events?category=&limit=20&timeframe=24h` — 热点事件列表
- `GET /api/v1/hot-events/{id}` — 热点事件详情（含时间线与来源报道）

### 来源管理
- `GET /api/v1/sources` — 列出所有来源
- `POST /api/v1/sources` — 新增来源
- `PUT /api/v1/sources/{id}` — 更新来源
- `DELETE /api/v1/sources/{id}` — 删除来源
- `POST /api/v1/sources/{id}/fetch` — 手动触发单个来源采集

### 文章
- `GET /api/v1/articles?source_name=&is_processed=&limit=50&offset=0` — 原始文章列表

### 管理后台
- `GET /api/v1/admin/stats` — 系统统计仪表盘
- `GET /api/v1/admin/logs?limit=100` — 最近任务执行日志
- `POST /api/v1/admin/trigger-fetch` — 手动触发全量采集
- `POST /api/v1/admin/trigger-ai` — 手动触发 AI 处理

### SSE 实时推送
- `GET /api/v1/sse/hot-events` — Server-Sent Events，推送新事件与排名变动

## 添加新的新闻源

通过 API 或直接在数据库中添加：

```bash
curl -X POST http://localhost:8000/api/v1/sources \
  -H "Content-Type: application/json" \
  -d '{
    "name": "某科技博客",
    "type": "rss",
    "endpoint": "https://example.com/feed",
    "interval": 600
  }'
```

## License

MIT
