# 2026-09-12 复盘：批量上传 422 + 黄兴路步行街定位到上海

开发内容：行程 `eb6d1401-7196-4619-b69d-b3827b36f1a0` 上「批量上传」失败；同一行程「黄兴路步行街」标在上海。两件事不是同一个 bug。

---

## 问题速查表

| # | 类别 | 问题 | 解法 |
|---|------|------|------|
| 1 | 上传校验 | `POST /trips/{id}/photos` 浏览器 422 | 自己读 multipart；空 `item_id` 当没传；兼容 `files` / `file` / `files[]` |
| 2 | 地理编码 | 长沙行程里「黄兴路步行街」落到杨浦黄兴路 | `citylimit=true` + 城市过滤 + 路名折叠；指定城市后禁止全国搜 |

---

## 1. 批量上传 422

**现象**

行程页点「批量上传」，网络面板 `POST /api/v1/trips/.../photos` → **422 Unprocessable Entity**。用 Python 按规范组 multipart 直连 `:8000` 则是 202。

**原因**

422 是 FastAPI **请求体校验失败**，发生在业务代码之前。这条接口原来是：

```python
files: list[UploadFile] = File(...)
item_id: UUID | None = Form(default=None)
```

`File` 和可选 `Form(UUID)` 叠在一起时，浏览器常见两种打法会直接 422：

1. 没挂节点时仍带上空字符串 `item_id=""` → 不是合法 UUID
2. 文件字段名不是精确的 `files`，或 `Content-Type` 被设成 `application/json`（`FormData` 不能手写 Content-Type，否则没有 boundary）

直连 Python 字段正确所以能过；用户从页面选图走的是浏览器表单。

**方案**

- `upload_photos` 改为 `await request.form(max_part_size=MAX_BYTES)`，不再用 `File(...)` + `Form(UUID)`
- 空 / 空白 `item_id` 视为未指定；非法 UUID 返回 400 中文说明
- 文件字段兼容 `files`、`file`、`files[]`
- 前端 `api.ts`：识别到 `FormData` 就删掉 `Content-Type`，让浏览器带 boundary；422 的 `detail` 展示给用户
- Vite 代理 `/api` 超时加到 180s，避免大图批量被代理掐断

**不要做的**

不要把 422 当成「照片格式不对」。格式拒绝是 415（HEIC）或业务 400/413。

---

## 2. 黄兴路步行街标到上海

**现象**

长沙一日行程，前 6 个点都在长沙（岳麓山一带 28.18, 112.93），「黄兴路步行街」却是 `31.280939, 121.528057`（上海杨浦黄兴路 / 黄兴公园附近）。

**原因（三层叠在一起）**

1. 高德 Place Text 的 `city` **默认只是偏好，不是硬限制**。没开 `citylimit=true` 时，长沙查询仍可能返回上海「黄兴路」。
2. 名称打分把「结果名是查询的子串」和「查询是结果的子串」打成同样高分。查询「黄兴路步行街」里，**上海「黄兴路」是子串 → 分更高**；长沙正式名是「黄兴南路步行街」，多一个「南」，反而不包含完整查询，分更低。
3. `_geocode_with_fallback` 在指定城市搜不到（或搜到了但没校验城市）时会 **放开城市做全国搜**。同名路一旦全国搜，上海更容易排前面。

这和「附近搜索误匹配」不是一类：城市模式本来就不用上一节点做 around；错在全国候选 + 子串打分。

**方案**

- Place Text：有城市就带 `citylimit=true`，再用 `cityname` / `adname` / 地址过滤
- 路名折叠：`[东南西北]路` → `路`，于是「黄兴南路步行街」与「黄兴路步行街」全等
- 子串匹配降档：结果名是查询的一段（「黄兴路」）低于折叠后全等
- 指定了 `preferred_city` **禁止全国搜**；命中外省城市的结果丢弃
- 城市模式若结果距上一节点 > 250km 也丢弃（长沙↔上海约 900km）
- 地理编码缓存 key 加 `v2`，避免继续用旧的上海结果
- 该行程按天 `reoptimize_day`（`reorder=False`）：黄兴路步行街改为 **28.188, 112.976**

跨城景点必须写 POI 自己的 `city`（或行程城市就是那座城），不能靠全国搜猜。

**验证**

- `tests/unit/test_geocode_resolve.py`：名称打分偏向「黄兴南路步行街」；城市过滤丢掉上海
- `tests/test_route_optimizer.py`：指定城市后不再 `city=""`；外省坐标会被拒绝
- 连同照片表单单测：42 passed（`--noconftest`）
