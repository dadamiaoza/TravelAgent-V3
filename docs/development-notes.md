# 开发问题与解决方案记录

> 本文档用于复盘实际开发中遇到的问题、定位过程与最终方案，方便后续继续开发时快速回忆上下文。

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
