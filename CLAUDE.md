# Agent Hot News

AI 驱动的多源热点新闻实时检测与聚合展示系统。

## 技术栈

- **后端**：Python 3.12 + FastAPI + SQLAlchemy + APScheduler
- **数据库**：PostgreSQL 17 + pgvector（向量存储）+ Redis（API 缓存）
- **AI**：OpenAI Embedding + GPT-4o-mini / 兼容 Ollama
- **前端**：React 18 + TypeScript + Tailwind CSS + Vite + SWR
- **部署**：Docker Compose 全容器化（Redis + PostgreSQL + Backend + Frontend）

## 关键目录

- `backend/app/` — FastAPI 后端（`main.py` 入口，`api/v1/` 路由，`collectors/` 采集器，`ai_pipeline/` AI 处理）
- `backend/requirements.txt` — 后端全量依赖（含 pytest，可在容器内跑测试）
- `frontend/src/` — React 前端（`pages/` 页面，`hooks/` SWR + SSE，`components/` UI）
- `docs/` — 需求与代码审查文档

## 启动

```bash
./start.sh            # 全量 docker compose up -d --build，后端 http://localhost:51180
./start.sh -f         # 前台模式，Ctrl+C 停止

# 等价手动
docker compose up -d --build
docker compose logs -f backend
```

## 重要约定

- Redis 仅用于 `backend/app/cache/` 中的 API 响应缓存装饰器（`@cache_response(ttl=60)`）。
- PostgreSQL + pgvector 存储向量嵌入，支持 HNSW 索引加速相似度搜索。
- 新增采集器需继承 `app.collectors.base.BaseCollector`。
- 管理后台路由：`/admin`。
- 修改后自动化测试校验，BUG修改完补充TEST避免再出现
