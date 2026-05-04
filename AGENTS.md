# Agent Hot News

AI 驱动的多源热点新闻实时检测与聚合展示系统。

## 技术栈

- **后端**：Python 3.12 + FastAPI + SQLAlchemy + APScheduler
- **数据库**：SQLite (`backend/hotnews.db`) + Redis（仅做 API 缓存）
- **AI**：OpenAI Embedding + GPT-4o-mini / 兼容 Ollama
- **前端**：React 18 + TypeScript + Tailwind CSS + Vite + SWR
- **部署**：Docker Compose（Redis + Frontend 容器化；后端本地启动，使用 SQLite）

## 关键目录

- `backend/app/` — FastAPI 后端（`main.py` 入口，`api/v1/` 路由，`collectors/` 采集器，`ai_pipeline/` AI 处理）
- `frontend/src/` — React 前端（`pages/` 页面，`hooks/` SWR + SSE，`components/` UI）
- `docs/` — 需求与代码审查文档

## 启动

```bash
# 本地开发（分别启动）
.\start-backend.bat    # 后端 http://localhost:51180
.\start-frontend.bat   # 前端 http://localhost:51130

# Docker（Redis + Frontend）
./start.sh
```

## 重要约定

- AGENTS.md 和 CLAUDE.md 需要同步
- `backend/hotnews.db` 是 SQLite 数据库，**已入库**，运行时会被修改。
- `start-backend.bat` 从 `.env` 加载环境变量（含 `OPENAI_BASE_URL`），无硬编码覆盖。
- Redis 仅用于 `backend/app/cache/` 中的 API 响应缓存装饰器（`@cache_response(ttl=60)`）。
- 新增采集器需继承 `app.collectors.base.BaseCollector`。
- 管理后台路由：`/admin`。
- 修改后自动化测试校验，BUG修改完补充TEST避免再出现
