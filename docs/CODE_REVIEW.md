# 代码审查报告

## 审查日期
2026-04-29

## 审查范围
后端（FastAPI + SQLAlchemy + APScheduler）+ 前端（React + TypeScript + Tailwind）

## 待修复问题

### 🟢 Low（优化建议）

1. **[backend/app/api/v1/endpoints/sources.py]** `endpoint` 字段在 Pydantic Schema 中类型为普通 `str`，缺少 URL 格式校验，可能保存非法地址导致采集失败。
   - **修复建议**：将 `endpoint` 改为 `HttpUrl` 类型，或在前端表单中增加 `type="url"`（前端已具备）。

2. **[frontend/src/hooks/useApi.ts]** `fetcher` / `postJson` 等函数未设置 `credentials: 'include'`，若后续引入 Cookie/Session 认证将直接失效。
   - **修复建议**：为所有 fetch 调用增加 `credentials: 'include'`。

## 安全评估

| 风险等级 | 问题 | 建议 |
|---------|------|------|
| 🟢 低 | SQL 注入 | 所有查询均使用 SQLAlchemy 参数化绑定，未发现字符串拼接 SQL 的风险。 |
| 🟢 低 | XSS | 前端使用 React 默认转义，未发现 `dangerouslySetInnerHTML` 或原生 `innerHTML` 注入点。 |
| 🟡 中 | 敏感信息泄露 | `.env.example` 包含默认数据库密码 `postgres:postgres`，生产环境部署时必须替换；`DEBUG=true` 不应在生产环境开启。 |
| 🟢 低 | CORS | DEBUG 模式下已移除通配符，改为显式本地地址；生产环境仅保留 `http://localhost:51130`，符合安全预期。 |

## 性能评估

| 问题 | 等级 | 说明 |
|------|------|------|
| 缓存策略 | 🟢 Low | `hot-events` 列表已加 `@cache_response(ttl=60)`，合理。 |
| 分页 | 🟢 Low | `articles` 列表已支持 `limit`/`offset`；`hot-events` 已支持 `limit` 并限制 `le=100`。 |

## 总体评价

项目整体架构清晰，采用配置化采集器 + Embedding 聚类 + LLM 总结的 AI Pipeline 设计合理，前后端分离且组件化程度较高。

建议后续引入 **类型安全的 API 客户端生成**（如 OpenAPI Generator 或 `orval`）以从根本上避免接口契约漂移。
