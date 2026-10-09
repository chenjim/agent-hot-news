# Agent Hot News API

所有接口挂在 `/api/v1` 前缀下，服务地址 `https://f.h89.cn:51130`。

- 响应一律 JSON，编码 UTF-8。
- **读接口**需要 `READ_TOKEN`，**写接口**需要 `WRITE_TOKEN`（见下方「鉴权」）。
- `/health` 不需要令牌（容器健康检查用）。

---

## 鉴权

令牌在项目根 `.env` 里配置：

```
READ_TOKEN=<读令牌>     # 保护所有 GET 接口
WRITE_TOKEN=<写令牌>    # 保护所有写接口
```

三种携带方式，任选其一（优先级从高到低）：

| 方式 | 示例 |
|------|------|
| 专用请求头 | `X-Read-Token: <token>` / `X-Write-Token: <token>` |
| Bearer | `Authorization: *** <token>` |
| 查询参数 | `?token=<token>`（**仅读接口/SSE**，EventSource 带不了请求头；写接口不接受 query 令牌，避免令牌进访问日志） |

规则：

- 读令牌只能调读接口，写令牌只能调写接口，**互不通用**。
- 校验失败返回 `401` + `{"detail":"Missing or invalid access token"}`。
- 令牌留空 = 关闭鉴权（本地开发用，生产不要留空）。
- 前端页面已内置读令牌（`VITE_READ_TOKEN`，构建期注入），写令牌不进前端。

生成新令牌：`openssl rand -hex 16`

---

## 数据规则（重要）

1. **原文不入库**。采集到的正文先经 LLM 摘要，只把摘要落库；`articles.content` 列恒为 `NULL`。
   - 判定阈值：`summary + content` 合计 **> 300 字** → 走 LLM 摘要（原文完整喂给模型，不截断，只留 50000 字安全阀）。
   - 合计 ≤ 300 字 → 不调 LLM，`content` 并进 `summary` 原样保留。
   - LLM 失败 → **该条跳过不落库**（指数退避 2s/6s/15s 重试，仍失败则下一轮采集重入），打 ERROR 日志，绝不存半截结果。
2. **接口不返回原文**。`/hot-events/{id}` 的 `sources[]` 不含 `content` 字段。
3. **链接可浏览性**。`sources[].browsable` 表示该链接能否在浏览器打开：
   - 伪 URL（`tianapi://` 等）或探测失败（403、超时、非网页）→ `false`，前端用标题走必应搜索兜底；
   - 探测不走出站代理（和访客直连一致），成功缓存 24h、失败 2h；
   - 只探测解析到公网地址的链接（环回/私网/链路本地/元数据地址一律拦截，防 SSRF）；
   - 详情接口整体探测预算 7s，超时则退回「是 http 就算可用」，接口不会挂住。
4. 存量原文回填：`backend/scripts/purge_originals.py`（先 `--dry-run` 看数量）。

---

## 接口清单

### 健康检查

```
GET /health
```
无需令牌。返回 `{"status":"ok","time":"..."}`。

---

### 读接口（READ_TOKEN）

#### 1. 热点事件列表

```
GET /api/v1/hot-events
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `category` | string | 过滤分类：`tech` / `finance` / `social` / `global` / `sports` / `entertainment` / `health` / `other`，不传=全部 |
| `limit` | int | 返回条数，1–300，默认 30 |
| `offset` | int | 分页偏移，默认 0，配合 limit 做无限滚动 |
| `tz` | string | 时区，默认 `Asia/Shanghai`，用于「今天」分组 |

只返回**已发布**的事件：文章数满 3 篇（`MIN_PUBLISH_ARTICLES`）且来源 ≥ 2 个（`MIN_EVENT_SOURCES`）才会被打上 `aggregated_at`，未达标事件不上列表（详情直链仍可访问）。窗口与排序都按 `aggregated_at` 算——取最近 7 天聚合的事件，按其**倒序**（与首页卡片展示的时间字段一致），带 60s 响应缓存。该时间在达标瞬间写入后**永不更新**，老事件不会因为后续追加报道跳回列表前排。

```bash
curl -H "X-Read-Token: $READ_TOKEN" \
  "https://f.h89.cn:51130/api/v1/hot-events?limit=30&tz=Asia/Shanghai"
```

返回项字段：`id, title, summary, detail, category, hot_score, trend, sentiment, entities, articles_count, sources_count, first_seen_at, last_updated_at, aggregated_at, cover_image`。

其中 `last_updated_at` 已降级为纯内部字段（7 天召回窗口、每日清理用），不再决定顺序；`aggregated_at` 才是发布/展示时间。

其中 `summary`（≤60 字）和 `detail`（150–300 字）都是 LLM 基于各来源摘要重新生成的原创文本。

#### 2. 事件详情

```
GET /api/v1/hot-events/{event_id}
```

在列表字段基础上追加：

| 字段 | 说明 |
|------|------|
| `timeline[]` | `time` / `source` / `title`，传播时间线；`time` 为 `published_at`，为空时回退 `fetched_at`（采集时间），并按该值倒序（`coalesce`，避免 NULL 抢到最前） |
| `sources[]` | `name` / `url` / `title` / `hot_score` / **`browsable`** |
| `related_events[]` | 预留，目前恒为空数组 |

> `sources[]` **不含** `content`（原文不外传）。`browsable=false` 时前端跳搜索兜底链接。

```bash
curl -H "X-Read-Token: $READ_TOKEN" \
  "https://f.h89.cn:51130/api/v1/hot-events/123"
```

#### 3. 文章列表

```
GET /api/v1/articles
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `source_name` | string | 按来源过滤 |
| `is_processed` | bool | 是否已被 AI 处理 |
| `limit` | int | 1–200，默认 50 |
| `offset` | int | 分页偏移 |

字段：`id, url, title, summary, source_name, source_url, published_at, fetched_at, raw_hot_score, language, is_processed`。
`summary` 是 AI 摘要（≤300 字阈值规则见上），**不含** `content` 字段。

#### 4. 来源列表

```
GET /api/v1/sources          # 全部来源
GET /api/v1/sources/{id}     # 单个来源
```

`?status=active|error|paused` 过滤。字段：`id, name, type(rss|api|scraper), endpoint, config, status, last_fetched_at, last_error, created_at`。

#### 5. 管理看板统计

```
GET /api/v1/admin/stats?tz=Asia/Shanghai
```

返回 `articles_today, events_today, total_articles, total_events, active_sources, total_sources, uptime_seconds, first_started_at, sources_health[], server_time`。
`uptime_seconds` 为累计运行时长（自 `first_started_at` 起算，跨进程重启持久化，落盘于 `backend/data/system_meta.json`，仅首次调用时用「进程启动时间」与「库内最早业务记录」的较早者初始化一次）。
`sources_health[]` 含 `id, name, type, status, last_fetched_at, last_error, fetched_today`。

#### 6. 任务日志

```
GET /api/v1/admin/logs?limit=100
```

`limit` 1–1000。返回内存中最近 N 条：`id, task, status(success|failed), message, created_at`。

#### 7. SSE 实时推送

```
GET /api/v1/sse/hot-events
```

**必须用查询参数带令牌**（EventSource 无法设置请求头）：

```js
new EventSource(`/api/v1/sse/hot-events?token=${READ_TOKEN}`);
```

事件类型：`new_event`（`event_id, title, rank, hot_score`）、`rank_change`（`event_id, title, old_rank, new_rank, hot_score`）。每 30s 发一次 `:keep-alive` 注释保活。

---

### 写接口（WRITE_TOKEN）

> 后台页面已移除这些操作入口，只保留后端能力 —— 用 curl / 脚本调用，务必带 `X-Write-Token`。

#### 8. 新建来源

```
POST /api/v1/sources
Content-Type: application/json

{
  "name": "Solidot",
  "type": "rss",                  // rss | api | scraper
  "endpoint": "https://feeds.feedburner.com/solidot",
  "config": {"language": "zh"}
}
```

返回新建的来源对象。`name` 全局唯一，重复会报错。

#### 9. 修改来源

```
PUT /api/v1/sources/{id}
Content-Type: application/json

{"status": "paused"}              // 任意 Source 字段，只改传入的字段
```

`status` 可选 `active` / `error` / `paused`（`paused` 会跳过采集）。

#### 10. 删除来源

```
DELETE /api/v1/sources/{id}
```

返回 `{"ok": true}`。已采集的文章不受影响。

#### 11. 手动采集单个来源

```
POST /api/v1/sources/{id}/fetch
```

同步执行：抓取 → LLM 摘要 → 落库。返回 `{"status":"ok","fetched":N,"new":M}`。
失败返回 500 并把该来源标记为 `error`。

#### 12. 触发全量采集

```
POST /api/v1/admin/trigger-fetch
```

5 分钟冷却期内重复调用会直接返回 `{"status":"ok","message":"...skipping"}`。
返回 `{"status":"ok","message":"..."}`。

#### 13. 触发 AI 处理

```
POST /api/v1/admin/trigger-ai
```

同样 5 分钟冷却。返回 `{"status":"ok","message":"..."}`。

---

## 错误码

| 状态码 | 含义 |
|--------|------|
| `200` | 成功 |
| `401` | 令牌缺失或错误（`Missing or invalid access token`） |
| `404` | 资源不存在（`Event not found` / `Source not found`） |
| `422` | 参数校验失败（FastAPI 默认） |
| `500` | 服务端错误（采集/处理失败，详情见 `detail` 与任务日志） |

---

## 完整示例

```bash
BASE=https://f.h89.cn:51130
READ_TOKEN=你的读令牌
WRITE_TOKEN=你的写令牌

# 读：拉今天的热点
curl -s -H "X-Read-Token: $READ_TOKEN" "$BASE/api/v1/hot-events?limit=10" | jq '.[].title'

# 读：事件详情（看哪些来源链接打不开）
curl -s -H "X-Read-Token: $READ_TOKEN" "$BASE/api/v1/hot-events/123" \
  | jq '.sources[] | {name, browsable, url}'

# 读：SSE（只能 query 带令牌）
curl -N "$BASE/api/v1/sse/hot-events?token=$READ_TOKEN"

# 写：暂停某个来源
curl -s -X PUT -H "X-Write-Token: $WRITE_TOKEN" -H "Content-Type: application/json" \
  -d '{"status":"paused"}' "$BASE/api/v1/sources/12"

# 写：手动跑一次采集
curl -s -X POST -H "X-Write-Token: $WRITE_TOKEN" "$BASE/api/v1/admin/trigger-fetch"
```
