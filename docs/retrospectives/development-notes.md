# 开发问题与解决方案记录

> 本文档用于复盘实际开发中遇到的问题、定位过程与最终方案，方便后续继续开发时快速回忆上下文。
>
> 复盘原则：只记录用户发现/反馈的问题；开发过程中自己完成的小问题不写复盘，除非影响产品决策或后续维护。

## 1. P0-1：前端最小可用闭环

### 问题
- 首页原本只有一个跳转到 `/trips/demo` 的链接，没有真实创建行程表单。
- 详情页原本只显示行程 ID，没有读取和展示后端返回的 Day-by-Day 行程。
- 前端 `Trip` 类型缺少 `days` 等字段，和后端 `TripOut` 不完全一致。

### 解决方案
- 新增 4 个组件：
  - `TripCreateForm`：表单 + 调 `POST /api/v1/trips` + 成功后跳转详情页。
  - `TripDetail`：行程摘要 + 渲染 Day 卡片。
  - `ItineraryDayCard`：单天行程卡片。
  - `ItineraryItemCard`：单节点展示时间段、地点、结构化信息。
- 补齐 `Trip` / `DayView` / `ItineraryItem` 类型，和后端 `TripOut` 对齐。
- 表单做了基础防呆：
  - 目的地非空
  - 日期必填
  - `end_date >= start_date`
  - 人数必须为 1-20 的整数

### 关键结论
- 详情页“简介”没有扩展后端字段，先用现有结构化字段拼接展示，避免为 UI 反向要求后端捏造字段。
- `useAgents.ts` 中的 `/jobs` 调用是死代码，当前后端不存在该端点，暂不修复。

## 2. 行程地图展示（高德 JS API）

### 问题 / 需求
- 希望在行程详情页看到每个 Day 的 POI 在地图上的位置。
- 选择高德 JS API，因为后端地理编码已经使用高德，坐标体系一致（GCJ-02），没有跨地图坐标系偏移。
- 展示方式确认：按天切换，同一天按顺序用直线连接。

### 解决方案
- 新增 `src/frontend/src/lib/amap.ts`：
  - 动态加载高德 JS API v2，不增加 npm 依赖。
  - 加载前设置安全密钥 `window._AMapSecurityConfig`。
- 新增 `src/frontend/src/components/TripMap.tsx`：
  - Day 切换按钮。
  - 当前天所有 POI 标记。
  - 同一天 POI 按 `seq` 直线连接。
  - 点击标记弹出信息窗。
  - 切换 Day 时清理旧 Marker / Polyline / InfoWindow。
- 地图密钥放在 `src/frontend/.env`：
  - `VITE_AMAP_KEY`
  - `VITE_AMAP_SECURITY_CODE`
- `.env` 已被 `.gitignore` 忽略，不提交仓库；`.env.example` 只放占位符。

### 注意
- 高德前端必须使用 **JS API Key**，不是 Web 服务 Key。
- 修改 `.env` 后需要重启前端 dev server，Vite 才会重新读取环境变量。

## 3. POI 同名歧义：玉湖湿地公园坐标错误

### 问题现象
- 萍乡 2 日游中，第二天“玉湖湿地公园”在地图上显示在江西萍乡以外。
- 后端实际保存的坐标是：
  - `lat=33.120648, lng=114.002601`
- 这是另一个城市的同名公园，不是萍乡本地。

### 根因
- 路线优化调用高德地理编码时没有传城市：
  ```python
  geocode_poi(item["poi_name"])
  ```
- 高德遇到同名 POI 时返回了第一个匹配结果。
- 验证：
  ```text
  geocode_poi("玉湖湿地公园")            → 外地坐标
  geocode_poi("玉湖湿地公园", city="萍乡") → 萍乡本地坐标
  ```

### 第一轮修复
- 在 `app/services/itinerary.py` 中把行程目的地写入行程 JSON：
  ```python
  itinerary["city"] = trip.destination
  ```
- 在 `app/agents/tools/route_optimizer.py` 中读取该城市并传给地理编码：
  ```python
  geocode_poi(item["poi_name"], city=city)
  ```

### 发现的新风险
- 如果整趟行程所有 POI 都强制使用同一个目的地城市，跨城景点可能搜不到或匹配错误。
- 例如“杭州 2 日游”去乌镇（嘉兴），不能所有点都用“杭州”搜索。

## 4. 最终升级：POI 级城市 + 回退链

### 设计目标
- 既解决同名 POI 歧义，又支持跨城景点。

### 最终方案
1. **POI 级城市优先**
   - `itinerary_gen` 输出每个 POI 时可带 `city` 字段。
   - 路线优化时优先使用该 POI 自己的 `city`。
   - 如果 POI 没有 `city`，再使用行程级 `fallback_city`。

2. **地理编码回退链**
   - 第一步：用 `POI 城市 / 行程城市` 做严格搜索。
   - 第二步：严格搜索不到时，放开城市限制做无城市搜索，兼容跨城景点。
   - 第三步：仍然找不到时，才使用 mock 坐标兜底，保证行程前端始终可展示。

### 涉及文件
- `src/backend/app/agents/tools/geo.py`
  - `geocode_poi` 增加 `mock_fallback` 参数，支持“严格模式”和“兜底模式”。
- `src/backend/app/agents/tools/route_optimizer.py`
  - 新增 `_geocode_with_fallback`。
  - 优先使用 `item["city"]`，回退到行程 `city`。
- `src/backend/app/agents/itinerary_gen.py`
  - 输出 JSON 中增加 `city` 字段说明。
- `src/backend/tests/test_route_optimizer.py`
  - 增加城市传递、回退链相关回归测试。

### 验证结果
- `pytest --noconftest tests/test_route_optimizer.py -k "not agent"`
  - 23 passed。
- 直接验证：
  ```text
  optimize_itinerary("city=杭州, item.city=萍乡, 玉湖湿地公园")
  → 返回萍乡坐标 lat=27.655492, lng=113.891267
  ```

## 5. 已知待办 / 隐患

- [ ] `useAgents.ts` 调用了不存在的 `/jobs/{id}` 端点，需要单独清理或补齐后端。
- [ ] 已存在的旧行程数据仍保留错误坐标；新代码只影响新生成的行程。
- [ ] 跨城场景目前依赖 LLM 在 `city` 字段中正确填写城市；这属于 Agent prompt 层面的约束，后续可考虑用结构化工具输出强制保证。
- [ ] 若需支持真实路线（非直线），后续可接入高德路径规划 API 在地图上绘制实际路线。


## 6. Railway 部署与前后端通信

### 部署形态
- Railway 上运行三个服务：
  - PostgreSQL（Railway 托管，替代本地 docker-compose）
  - backend（FastAPI）
  - frontend（Nginx + 静态文件）
- 代码侧准备：
  - 后端 `Dockerfile` + `start.sh`，启动前自动执行 `alembic upgrade head`
  - 前端多阶段 `Dockerfile`：Node 构建 → Nginx 托管 `dist/`
  - Nginx 使用官方模板机制自动 envsubst `BACKEND_URL` 和 `PORT`
  - `config.py` 兼容 Railway 的 `postgres://` → `postgresql://`

### 前后端通信流程
```text
浏览器
  ↓
访问前端公网域名
  ↓
Nginx 返回 HTML/JS/CSS
  ↓
前端 JS 请求 /api/v1/...
  ↓
Nginx 收到 /api 请求
  ↓
代理到 http://backend:8080
  ↓
FastAPI 处理并返回 JSON
  ↓
Nginx 返回给浏览器
```

### 关键设计：同源代理
- 前端生产环境不直接请求后端公网地址。
- 所有 `/api` 请求都走前端同域名，由 Nginx 反向代理到后端。
- 好处：
  - 浏览器不需要处理 CORS。
  - 前端代码里仍然使用 `/api/v1`，不需要根据环境切换 base URL。

### 关键环境变量
前端服务：
- `BACKEND_URL=http://backend:8080`
  - Nginx 把 `/api` 转发到 Railway 内部后端服务。
- `PORT=8080`
  - Nginx 监听 Railway 期望的端口。
- `VITE_AMAP_KEY`
- `VITE_AMAP_SECURITY_CODE`
  - 构建时写入前端静态资源，用于高德地图。

后端服务：
- `PORT=8080`
  - FastAPI 监听端口。
- `DATABASE_URL`
  - Railway PostgreSQL 连接串，代码已做 `postgres://` 兼容。
- `LLM_API_KEY / AMAP_API_KEY / QWEATHER_* / TAVILY_* / FIRECRAWL_*`
  - AI、高德、和风、MCP 搜索所需密钥。

### 部署踩坑记录
1. **Railway 内部地址不要写成 `backend.railway.internal:8000`**
   - 正确使用短服务名：`backend:8080`。
   - `.railway.internal` 不一定可解析，短服务名在同项目内更稳定。

2. **端口不要写死 8000**
   - Railway 会注入 `PORT=8080`。
   - 后端和前端都应按环境变量 `PORT` 监听。

3. **Railway 公共域名端口要和 Nginx 监听端口一致**
   - 如果 Railway 前端服务配置的 Port 是 `80`，但 Nginx 监听 `8080`，会得到 `Application failed to respond`。
   - 最终把 Railway 前端服务的 Port 改为 `8080`，与 Nginx 对齐后成功。

4. **Nginx 需要同时监听 IPv4 和 IPv6**
   - 容器内 `localhost` 可能解析到 `::1`。
   - 只监听 IPv4 时，`wget localhost:8080` 会连接拒绝。
   - 修复：`listen ${PORT};` + `listen [::]:${PORT};`。

### 为什么前后端都监听 8080？
- 8080 不是代码里写死的，而是 **Railway 自动注入的 `PORT` 环境变量**。
- 后端 `start.sh`：
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
  ```
  即：有 `PORT` 用 `PORT`，没有则默认 8000。
- 前端 Nginx 模板：
  ```nginx
  listen ${PORT};
  listen [::]:${PORT};
  ```
  即：Nginx 监听 `PORT` 指定的端口。
- Railway 给前后端各自注入 `PORT=8080`，所以两边都监听 8080。
- 前后端是不同容器，各自网络空间独立，因此同一个端口号不会冲突。
- 如果修改端口：
  - 后端设 `PORT=新端口`
  - 前端设 `PORT=新端口`
  - 前端 `BACKEND_URL` 改为 `http://backend:新端口`
  - Railway 前端公网 Port 也要同步修改


### 面试可以怎么讲
> “生产环境我采用同源代理架构：前端 Nginx 同时托管静态资源和反向代理 `/api` 到后端内部服务，避免 CORS，也让浏览器只需要知道前端域名。后端通过 Railway 的内部服务地址 `backend:8080` 通信，数据库使用 Railway 托管的 PostgreSQL，部署时由启动脚本自动执行 Alembic migration。”


## 7. 【重点】外部 API 超时问题与工程化解法

> 这是面试中最值得展开讲的一个点：外部依赖不稳定时，如何做快速失败、降级兜底、异步化和用户体验。

### 问题现象
- 生成行程时会调用高德地理编码、高德路径规划、LLM 等外部服务。
- Railway 环境下访问 `restapi.amap.com` 可能超时。
- 单次超时 `10s`，多个 POI/多对路径叠加后，整个请求可能超过 30s 甚至更久。
- 前端最终表现为：
  - `net::ERR_CONNECTION_CLOSED`
  - 或“创建失败，请稍后重试”

### 根因
- 不是代码逻辑错误，而是外部 API 网络不稳定。
- 代码已有降级到 mock/估算，但降级前仍会等待固定超时时间。
- 请求链路过长 + 同步等待，导致用户感知为失败。

### 正确解法（四层设计）

1. **快速失败**
   - 外部 API 超时从 `10s` 调小到 `3-5s`。
   - 不等满超时再降级。

2. **熔断 / 降级兜底**
   - 连续 N 次外部请求失败后，短时间内不再请求该外部服务。
   - 直接使用 mock / 本地估算，保证行程仍能生成。

3. **异步化**
   - `POST /trips` 不再同步等待全部生成完成。
   - 改为：立即返回任务 ID + 后台任务执行。
   - 前端轮询任务状态，或使用 SSE/WebSocket 推送进度。

4. **进度可见**
   - 前端展示：
     - “正在搜索景点”
     - “正在生成行程”
     - “正在优化路线”
     - “正在校验开放时间”
   - 让用户知道系统在工作，而不是感觉卡死。

### 补充优化
- **缓存**：相同 POI 的地理编码/开放时间结果做缓存，减少重复外部请求。
- **可观测性**：记录每次外部 API 的耗时、失败率、降级率，便于定位。

### 面试回答模板
> “生成行程时会调用高德地理编码和路径规划，但高德在某些网络环境下会超时。我的处理思路分两层：
>
> 第一层是**快速失败和降级**。外部 API 超时不能设太长，否则用户会一直等。我会把超时缩短，并加熔断机制：连续失败几次后，短时间内不再请求高德，直接走本地估算/mock 数据，保证用户仍然能拿到一份可用的行程，而不是创建失败。
>
> 第二层是**异步化和进度反馈**。创建行程后立刻返回任务 ID，后端后台执行 LLM 生成、地理编码、路线优化，前端轮询或通过 SSE 显示进度，比如‘正在搜索景点’、‘正在优化路线’、‘正在校验开放时间’。这样即使外部 API 慢，用户也能看到系统在工作。
>
> 另外我还会做**缓存**：同一个 POI 的地理编码结果缓存下来，避免重复请求高德。目前项目里已经做了 mock/估算降级，下一步就是升级成异步任务 + 进度条 + 熔断。”

### 面试关键词
- 外部依赖不可靠
- 快速失败
- 熔断
- 降级兜底
- 异步任务
- 任务队列
- 进度可见性
- 缓存
- 可观测性


## 8. 城市模式 / 景区模式路线规划

> 详细问题、权衡和解决过程见：[scenic-routes-retrospective.md](./scenic-routes-retrospective.md)

### 背景
- 高德 Web服务路径规划不支持景区内部路线、索道、景区接驳车等内部交通。
- 不能调用或虚构“景区路线 API”，也不能假装能拿到索道/接驳车真实轨迹。

### 方案
- 行程按天区分 `route_type`：
  - `city`：城市常规路线，沿用高德步行/公交。
  - `scenic`：景区内部，只用高德步行/驾车连接已定位 POI/站点。
- 索道、接驳车、登山步道等作为**业务层标注**：
  - `transport_mode = cable_car / shuttle / hiking`
  - `route_polyline = null`（不画成高德真实道路）
  - `route_verified = false`
  - `travel_advice` 提示“以景区现场指引/官方班次为准”
- 前端景区模式用虚线/特殊颜色表示参考路线，不冒充真实道路。

### 实现位置
- `route_optimizer.py`：按 `route_type` 选择矩阵交通方式，回填景区交通建议。
- `itinerary_days.route_type` + `itinerary_items.route_verified/travel_advice`。
- 前端 `TripMap` / `ItineraryItemCard` 展示模式标识和提示。


## 9. Phase A 用户反馈：地图和列表不能同时看到

### 现象
- 当天行程点很多时，点击地图上靠后的 Marker。
- 页面会自动滚动到列表对应卡片，导致地图滚出视口，地图和列表无法同时看到。

### 原因
- 原实现使用 `scrollIntoView({ block: "center" })`，滚动的是整个页面。
- 行程点一多，列表很长，滚动的距离就会很大。

### 解决
- 当天行程列表放入固定高度容器：
  ```text
  max-h-[60vh] overflow-y-auto
  ```
- 列表内部独立滚动，不再拖动整个页面。
- `scrollIntoView` 改为 `block: "nearest"`，只做最小必要滚动。
- 桌面端地图增加 `lg:sticky lg:top-4`，保证即使页面有其他滚动，地图仍然可见。
