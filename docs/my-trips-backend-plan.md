# 我的行程后端：阶段②–④方案与测试计划

阶段①盘点见 `docs/my-trips-backend-inventory.md`。本文件先固定最小改动，再改代码。目的地时区不在本文件的实现范围内。

## 阶段② 匿名设备凭证 + 服务端归属

### 最小改动方案

选型：**HttpOnly Cookie `ta_device`**，值是服务端生成的 UUID 字符串。

不用前端自造 `device_key` 再在列表里过滤。浏览器走同源 `/api`（Vite 代理到后端），`fetch` 默认同源会带上 Cookie。非浏览器测试用同一个 Cookie 名。

- 请求没有合法 `ta_device` 时，服务端发新 UUID，`Set-Cookie`：`HttpOnly`、`SameSite=Lax`、`Path=/`、一年。有合法 Cookie 则沿用，不轮换。
- 新列 `trips.device_id`（`String(64)`，可空，有索引）。`POST /trips` 把当前 Cookie 写入该列。
- 读和写只命中 `device_id` 等于当前 Cookie 的行。包括 `GET /trips`、`GET /trips/{id}`、PATCH、日程增删改、sync、reoptimize、reorder、导入、chat、delta、progress。照片路由的 `_get_trip` 同样校验，避免用 trip id 读照片绕过。
- 跨设备用 ID 直访：**404** `Trip not found`。不返回 403，避免区分「不存在」和「是别人的」。
- 幂等键命中别人的 job：同样 404，不把那次行程返回给当前设备。
- **旧匿名数据**：`device_id` 为空（含 `user_id` 为空、也没有设备绑定的历史行）。任何设备的列表都查不到。用 ID 直访也是 404。不自动认领。没有一次性 orphan 标记列；空 `device_id` 就是 orphan。
- 不新增登录、JWT、用户表，也不新增 retry HTTP。仓库没有 `POST /trips/{id}/retry`。写操作验收用 `PATCH /trips/{id}`。Job 内部 `retry_wait` 保持原样。
- `GET /jobs/{id}` 仍按 job id 读取（盘点里的相邻接口）。本次不改 job 路由，避免扩大面；行程列表和详情不会靠它暴露别人的行程正文。

### 测试计划

`tests/integration/test_trip_device_ownership.py`（真实 DB）：

- 设备 A 创建后，A 可以 list、get、patch；设备 B 的 list 不含该行程，B 对同一 id 的 get 和 patch 为 404。
- `device_id` 与 `user_id` 都为空的行：两个设备的 list 都没有它，直链 get 为 404。
- 不测不存在的 retry 路由。阶段②报告写明：无 retry HTTP，写路径以 PATCH 代表。

## 阶段③ 无日期草稿可入库可再开

### 最小改动方案

- 迁移把 `trips.start_date`、`trips.end_date` 改为可空。`itinerary_days.date` 保持必填：无日期草稿不产生 day 行。
- `TripCreate.start_date` / `end_date` 改为可选。两个都空：入库 `status=draft`，不创建 generation job（worker 仍要求日期，不能拿空日期去生成）。两个都有：保持今天的 `generating` + job。只填一个：422。
- `TripUpdate` 仍只改标题，不要求带日期。已有 PATCH 因此不会把草稿日期变成必填。
- `TripOut` / `TripBrief` 的日期改为 `date | None`。列表和详情能读到 `draft`。
- 加一天、删天重排、导入 POI 在 `start_date` 为空时返回 400，避免 `None + timedelta`。
- 前端不新做列表页。`Trip` 类型日期改为可空。现有首页卡片和 `/trips/:id` 标题用「日期未定」，避免把空值拼进句子。`TripDetail` 对空 `days` 已有空态，保留。

### 测试计划

同一集成文件追加：

- `POST /trips` 不带日期 → 201，`status=draft`，日期为 null，`job_id` 为 null，无 day。
- 同一设备 `GET /trips` 与 `GET /trips/{id}` 能读到该草稿。
- 只带 `start_date` → 422。
- 带齐日期的创建仍是 `generating`（不调用 LLM，只看响应字段）。

## 阶段④ 生成中 / 失败可打开

### 最小改动方案

不新增状态机。`GET /trips/{id}` 不按 `status` 拒绝。用本设备归属插入 `generating` 与 `generation_failed`、且 `days` 为空的行，证明详情 200。

前端：`TripDetail` 在 `days` 为空时不渲染日卡片和路线图。补一行 `const days = displayTrip.days ?? []` 已存在；再确认空数组合法。不做出页内重试按钮。

### 测试计划

- 本设备名下 `status=generating`、`days=[]` 的 `GET /trips/{id}` 为 200，且 `status` 原样返回。
- 同样断言 `generation_failed`。
- 另一设备访问这两条仍是 404（归属仍然有效）。

## 明确不做

目的地时区规则（展示、入库、按目的地换算「今天」）本次不实现。
