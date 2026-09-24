# 我的行程：后端盘点（阶段①）

只读盘点。本文件不改业务行为。范围是创建、列表、详情、修改、重试行情。照片归档、攻略源、事实核查只在「相邻但未纳入归属」里点名。

定稿约束（本次只记录，不在本阶段实现）：整卡进入现有 `/trips/:id`；生成状态与草稿日期独立；未定日期要能入库再打开；匿名按设备隔离且必须服务端校验；目的地时区本次不实现。

## 阶段①最小改动方案

不改路由、schema、ORM、迁移或前端。只把现有契约和测试缺口写进本文件，供阶段②–④按缺口补。

## 阶段①测试计划

无业务代码改动，不新增测试。验收方式：对照 `app/api/v1/trips.py`、`app/schemas/trip.py`、`app/models/trip.py` 与本文件路由表，确认方法、路径、handler、字段与缺口一致。

## HTTP 路由

前缀均为 `/api/v1`（`app/main.py` include）。Handler 均在 `app/api/v1/trips.py`，除非另注。

| 方法 | 路径 | Handler | 与行程的关系 |
|---|---|---|---|
| POST | `/trips/suggest` | `suggest_trip` | 解析自然语言，不入库 |
| POST | `/trips` | `create_trip` | 创建。立刻 `status=generating` 并写 `generation_jobs`。支持请求头 `idempotency-key` |
| GET | `/trips` | `list_trips` | 全部行程简表，按 `created_at` 倒序。无调用方过滤 |
| GET | `/trips/{trip_id}` | `get_trip` | 详情，含 days/items |
| PATCH | `/trips/{trip_id}` | `update_trip` | 只改 `destination` |
| GET | `/trips/{trip_id}/progress` | `get_generation_progress` | 最新 job 进度。不校验行程是否存在 |
| GET | `/trips/{trip_id}/progress/stream` | `get_generation_progress_stream` | 同上，SSE |
| PATCH | `/trips/{trip_id}/items/{item_id}` | `update_itinerary_item` | 改节点 |
| POST | `/trips/{trip_id}/items` | `create_itinerary_item` | 新增节点 |
| DELETE | `/trips/{trip_id}/items/{item_id}` | `delete_itinerary_item` | 删除节点 |
| POST | `/trips/{trip_id}/days` | `create_day_endpoint` | 加一天。`date = start_date + offset` |
| DELETE | `/trips/{trip_id}/days/{day_id}` | `delete_day_endpoint` | 删一天并按 `start_date` 重排日期 |
| POST | `/trips/{trip_id}/sync` | `sync_trip_endpoint` | 排序与名称 |
| POST | `/trips/{trip_id}/days/{day_id}/reoptimize` | `reoptimize_day` | 重算当天交通与时间 |
| POST | `/trips/{trip_id}/days/{day_id}/reorder` | `reorder_day_items` | 当天重排 |
| POST | `/trips/{trip_id}/entities/import` | `import_entities_to_trip` | 导入攻略 POI。新 day 的日期依赖 `start_date` |
| POST | `/trips/{trip_id}/chat` | `trip_chat` | 同步对话 |
| POST | `/trips/{trip_id}/chat/stream` | `trip_chat_stream` | SSE 对话 |
| POST | `/trips/{trip_id}/deltas/apply` | `apply_trip_delta` | 应用一条 AI delta |

重试：没有面向用户的 retry/regenerate HTTP 路由。`regenerate_trip`（`app/services/trip_editor.py`）只被 `create_trip_with_itinerary` 调用，当前创建 API 不走它。Job 失败后的 `retry_wait` 在 `app/services/generation_jobs.py` / `job_worker.py` 内部，没有 `POST /trips/{id}/retry`。相邻只读：`GET /jobs/{job_id}`、`GET /jobs/{job_id}/events`（`app/api/v1/jobs.py`），按 job id 读取，不看行程归属。

照片路由挂在同一 `/trips` 前缀（`app/api/v1/photos.py`），本次「修改行程」不把它们当成行程 CRUD，但它们用 trip id 直访且 `_get_trip` 不校验调用方。阶段②会一并挡上，避免 ID 直访绕过归属。

## Schema 与 ORM 关键字段

`Trip`（`trips`）：

| 字段 | ORM | 请求/响应 | 备注 |
|---|---|---|---|
| `id` | UUID PK | `TripOut` / `TripBrief` | |
| `user_id` | `String(64)` 可空 | 不出现在 schema | 无登录。现有行多为空 |
| `device_id` | 无 | 无 | 无设备绑定 |
| `destination` | `String(128)` 必填 | `TripCreate` 必填；`TripUpdate` 可选 | PATCH 只改这一项 |
| `city` | 可空 | `TripCreate` 可选 | |
| `start_date` / `end_date` | `Date` 必填（`0001_baseline`） | `TripCreate` / `TripOut` / `TripBrief` 必填 `date`；`TripSuggestOut` 可空 | 不能存无日期草稿 |
| `people_count` | int 默认 1 | 创建默认 1 | |
| `budget_min` / `budget_max` | 可空 int | 创建可选 | |
| `user_prompt` / `must_visit` | Text / JSONB 可空 | 创建可选 | |
| `status` | `String(32)` 默认 `"draft"` | `TripOut.status` | 创建 API 写 `"generating"`。终态还有 `"generated"`、`"generation_failed"`。模型默认 `"draft"` 几乎不被创建 API 使用 |
| `created_at` / `updated_at` | timestamptz | `TripOut` | 列表不返回 |
| `days` | relationship | `TripOut.days` | 列表用 `TripBrief`，不含 days |

`ItineraryDay.date` 为必填 `Date`。`ItineraryDayOut.date` 同样必填。无行程日期时，加天、删天重排、导入 POI 都会做 `start_date + timedelta`。

`GenerationJob.status`：`pending` / `running` / `retry_wait` / `succeeded` / `failed`。这是 job 状态，不是行程状态。行程失败枚举名是 `generation_failed`。

创建请求体 `TripCreate` 另有 `selected_entities`，写入 job payload，不进 `Trip` 列。

## 现有测试与覆盖缺口

| 文件 | 覆盖了什么 | 缺口 |
|---|---|---|
| `tests/test_trip_flow.py` | `POST/GET /trips`、`GET /trips/{id}`、直接插库。`test_create_trip_api` / `test_get_trip` 被标成 agent（期望同步生成 days），默认 `not agent` 不跑。`test_list_trips` 只断言返回数组 | 无归属、无 404 跨用户、无 PATCH、无空日期、无 `generating` / `generation_failed` 详情 |
| `tests/integration/test_generation_job_api.py` | 创建、幂等键、`GET /trips/{id}`、progress、`/jobs/{id}` | 同一 `TestClient`，看不出跨设备。进度接口不检查行程是否存在 |
| `tests/integration/test_candidate_fill_job.py` | 带 `selected_entities` 的创建 | 无归属 |
| `tests/integration/test_generation_finalization.py` | worker 把行程标成 `generation_failed`，重试保持 `generating` | 不走 HTTP 详情 |
| `tests/integration/test_job_worker_reliability.py` | job `retry_wait` | 无 HTTP retry |
| `tests/unit/test_trip_chat.py`、`test_trip_chat_stream.py` | chat / SSE。stream 用 MagicMock 行程 | 不校验调用方 |
| `tests/unit/test_generation_jobs.py` | job 状态机 | 不覆盖行程 HTTP |
| 前端 | 无测试脚本 | `TripDetail` 已对 `days.length === 0` 显示「该行程暂无内容」。`start_date` 类型是必填 `string`，空日期只会拼进标题，目前不会抛异常 |

没有测试覆盖：设备隔离、`user_id` 为空且无设备绑定的旧行、`start_date`/`end_date` 为空的创建与再读、`status=generating|generation_failed` 的 `GET /trips/{id}`。
