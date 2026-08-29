# 行程协作交互改造：地图联动 + 常驻 AI 对话 + 记忆管理

> 本文档是基于当前项目实际情况对产品方案的校验、技术设计与开发计划。
> 目标：在不推翻现有 React Query / FastAPI / LangGraph 架构的前提下，分阶段实现“地图-列表联动、编辑实时同步、常驻 AI 对话、长短期记忆”。

---

## 开发进度（实时更新）

| 阶段 | 状态 | 说明 |
|---|---|---|
| A：点位编号 + 列表/地图双向聚焦 | 🚧 核心代码已完成 | 分支 `feat/map-list-focus`，等待 TS 验证和人工验收 |
| B：Zustand 统一数据源 + 编辑/排序实时联动 | 🚧 核心代码已完成 | 分支 `feat/phase-b-trip-store`，后端增删/geocode/reoptimize + 前端 store/交互基础已落地，待联调验证 |
| C1：常驻对话面板 + 建议卡片 | ⬜ 未开始 | 依赖 B 的数据流 |
| C2：SSE 流式回复 | ⬜ 未开始 | |
| D：长短期记忆 + 上下文摘要 | ⬜ 未开始 | |

---

## 1. 当前项目实际情况校验

### 1.1 已经具备的能力

| 能力 | 当前状态 |
|---|---|
| 行程详情页 | ✅ 顶部地图 + 下方 Day 卡片列表 |
| Day 切换 | ✅ 已按 Day 切换并重绘地图 |
| 卡片排序 | ✅ 有 ↑↓ 按钮，支持同天排序 |
| 节点编辑 | ✅ 已经是 inline 展开编辑，不是弹窗 |
| 编辑后地图刷新 | ✅ 依赖 `invalidateQueries` 重新拉取行程并重绘 |
| AI 对话后端 | ✅ 已有 `POST /api/v1/chat`，走 Supervisor |
| 短期对话记忆 | ✅ 已有 PostgresSaver，`thread_id` 可延续 |
| 攻略导入 | ✅ 顶部“导入攻略”链接 + 底部“导入攻略并追加地点”面板 |
| 景区/城市双模式 | ✅ 已支持 `route_type` 和景区内部交通建议 |

### 1.2 尚未具备 / 需要改造

| 缺口 | 说明 |
|---|---|
| 地图点位编号 | 当前使用高德默认图钉，无序号 |
| 列表点击聚焦地图 | 无 |
| 地图 Marker 点击反向定位列表 | 无 |
| 真正的本地实时数据源 | 当前依赖 React Query 服务端状态，缺少统一的客户端行程 store |
| 编辑地点名称后重新地理编码 | 后端 `PATCH item` 只改名称，不重新 geocode |
| 排序后重算交通时间 | 当前 reorder 只改 seq，不重算 `travel_minutes` / `route_polyline` |
| 常驻 AI 对话面板 | 前端无，聊天入口未集成到行程页 |
| AI 结构化修改建议 | 当前 `/chat` 只返回纯文本，没有“建议卡片/采纳/忽略” |
| 行程节点增删 API | 当前只有 update / reorder / import，没有单点 add / delete |
| 流式回复 | 当前是同步 POST，无 SSE / WebSocket |
| 长短期记忆体系 | 只有短期会话记忆，没有用户偏好/历史摘要等长期层 |

### 1.3 对产品方案的修正

1. **“编辑后地图不重绘”不准确**
   - 现状：编辑保存后会 redraw，因为 React Query 重新拉取行程。
   - 真正的痛点：没有乐观更新、没有名称变更后的坐标重算、没有“定位中”状态。
   - 方案应改为“统一数据源 + 乐观更新 + 坐标重算”，而不是从零重绘。

2. **“编辑改为 inline”已经实现**
   - `ItineraryItemCard` 已经是 inline 展开表单，不需要再改交互形态。
   - 需要增强的是保存后地图聚焦/高亮，以及可选的拖拽排序。

3. **右侧常驻对话面板可以分阶段**
   - 不必第一版就做 SSE / WebSocket / 上传 PDF。
   - 第一阶段可以做：桌面右栏 + 移动端悬浮入口 + 同步 POST + 结构化建议卡片。
   - 第二阶段再升级 SSE 流式。

4. **Zustand 已有依赖**
   - `src/frontend/package.json` 已包含 `zustand`，可以直接作为客户端统一状态层。

---

## 2. 总体架构设计

### 2.1 前端数据流

```text
                    ┌──────────────────────┐
                    │  React Query (server) │
                    │  useTrip / mutations   │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Zustand TripStore     │
                    │  - days/items          │
                    │  - selectedDay/Item    │
                    │  - focusItemId         │
                    │  - chatContext        │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
       ┌────────────┐   ┌────────────┐   ┌────────────┐
       │ TripMap    │   │ DayCard    │   │ ChatPanel  │
       │ 地图/路线   │   │ 卡片/编辑   │   │ 建议/确认   │
       └────────────┘   └────────────┘   └────────────┘
```

- React Query 继续负责服务端数据获取和缓存。
- Zustand 负责客户端交互态、乐观更新、聚焦状态、聊天上下文。
- 地图、列表、对话面板都订阅同一个 store，解决“多处不同步”。

### 2.2 核心约定

1. 用户手动编辑 = 高优先级事实
2. AI 建议 = 低优先级建议，必须经过“采纳”才写入
3. 所有行程变更走统一 mutation / delta
4. 地图和列表不是各自维护状态，而是同一个 store 的视图

---

## 3. Phase A：点位编号 + 地图/列表双向聚焦

> 纯前端，改动小，先提升可感知交互。

### 3.1 功能点

- 自定义高德 Marker：
  - 圆形 div，内部显示当日序号
  - 例如 Day1-1、Day1-2，或直接 1、2、3
- 列表卡片左侧增加序号圆点：
  - `① 武功山景区游客中心`
- 点击列表卡片：
  - 地图 `setCenter` + `setZoom(16)` 或 `setFitView([marker])`
  - 对应 Marker 高亮，短暂放大 / 加阴影
  - 其他 Marker 半透明
- 点击地图 Marker：
  - 高亮列表对应卡片
  - `scrollIntoView({ behavior: "smooth", block: "center" })`
- Day 切换时地图 `setFitView` 只聚焦当天点位和路线。

### 3.2 涉及文件

```text
src/frontend/src/components/TripMap.tsx
src/frontend/src/components/ItineraryDayCard.tsx
src/frontend/src/components/ItineraryItemCard.tsx
src/frontend/src/components/TripDetail.tsx
src/frontend/src/lib/amap.ts
src/frontend/src/lib/types.ts
```

### 3.3 验收标准

- 每个地图点位有编号，和列表序号一致
- 点击列表能聚焦地图并高亮
- 点击地图 Marker 能滚动定位列表
- Day 切换后地图只显示当天内容

---

## 4. Phase B：统一数据源 + 编辑/排序实时联动

> 这是后续所有功能的地基。

### 4.1 引入 Zustand TripStore

```ts
interface TripStore {
  trip: Trip | null;
  setTrip: (trip: Trip) => void;
  selectedDayIndex: number;
  setSelectedDayIndex: (index: number) => void;
  focusItemId: string | null;
  setFocusItem: (itemId: string | null) => void;
  chatContext: { dayIndex?: number; itemId?: string };
  setChatContext: (ctx: { dayIndex?: number; itemId?: string }) => void;
  optimisticUpdateItem: (itemId: string, patch: Partial<ItineraryItem>) => void;
  applyDelta: (delta: ItineraryDelta) => void;
}
```

### 4.2 后端需要补齐

#### 新增 / 修改接口

| 接口 | 用途 |
|---|---|
| `POST /trips/{id}/items` | AI / 手动新增单个行程节点 |
| `DELETE /trips/{id}/items/{item_id}` | 删除单个节点 |
| `PATCH /trips/{id}/items/{item_id}` | 已存在；扩展：`poi_name` 变化时自动 geocode |
| `POST /trips/{id}/days/{day_id}/reoptimize` | 重排后重算交通时间/路线 |
| `POST /trips/{id}/chat` | 带行程上下文的 AI 对话（后续） |

#### 编辑地点名称时自动地理编码

- 当前 `PATCH` 只更新字段。
- 改为：如果 `poi_name` 有变化，后端调用现有 `geocode_poi` / `_geocode_with_fallback` 重新解析：
  - 更新 `lat / lng / amap_poi_id / poi_address / poi_type`
  - 返回更新后的完整 Item
- 前端在等待期间显示“定位中…”。

### 4.3 排序后重算路线

- 当前 `reorder` 只调整 seq。
- 新增 `reoptimize`：
  - 读取该 Day 所有 items
  - 调用 `route_optimizer.optimize_itinerary` 或复用工具函数
  - 更新 `travel_minutes_from_prev / transport_mode / route_polyline / route_verified / travel_advice`
- 前端先乐观排序，再异步调 `reoptimize`，期间交通时间显示“重新计算中…”。

### 4.4 验收标准

- 编辑名称后经纬度自动更新，地图点位移动
- 排序后序号、连线、交通时间同步刷新
- 用户手动修改和 AI 修改都会进入同一份 store，列表和地图始终一致

### 4.5 服务层收敛（防膨胀）

- 行程节点的新增/删除/更新/排序/重算路线集中到 `app/services/trip_editor.py`。
- `trips.py` 只保留 HTTP 入口。
- `recalculate_day_schedule` 统一负责时间重算，避免每个页面/接口各算一套。

### 4.6 依赖倒置落地（Ports & Adapters）

- `app/domain/interfaces.py`：
  - `RouteReplanner`
  - `TimeScheduler`
  - `Geocoder`
- `app/infrastructure/`：
  - `AmapRouteReplanner`
  - `ItineraryTimeScheduler`
  - `AmapGeocoder`
- `trip_editor.py` 不再直接 import Agent/Tool 内部函数，改为依赖 Port。
- 后续命令模式/事件溯源可在同一 Service 层切换实现，不改业务逻辑。

---

## 5. Phase C：常驻 AI 对话面板

### 5.1 布局

- 桌面端：
  ```text
  ┌──────────────────────────┬──────────────┐
  │ 行程详情（地图 + 列表）     │  常驻对话面板   │
  │ 左侧 60-65%               │  右侧 35-40%   │
  └──────────────────────────┴──────────────┘
  ```
- 移动端：
  - 右下角悬浮球
  - 点击展开底部抽屉
  - 收起后仍保留一个迷你输入框或悬浮球

### 5.2 对话能力

1. 常规消息气泡
2. 结构化建议卡片：
   - “新增：XX瀑布 09:00-10:00 [插入到 Day1 第3位]”
   - “采纳” / “忽略”
3. 导入攻略合并到对话面板
   - 粘贴文本 / 链接
   - 可选后续支持截图 / PDF
4. 上下文感知：
   - 前端把 `dayIndex` / `itemId` 随聊天请求传给后端
   - 例如用户正在编辑“金顶”，AI 可自然接话

### 5.3 后端接口设计

#### 现有接口扩展

```ts
// POST /api/v1/trips/{trip_id}/chat
{
  message: string;
  thread_id?: string;
  context?: {
    day_index?: number;
    item_id?: string;
    transport_mode?: string;
  };
}
```

#### 返回结构（第一版同步）

```ts
{
  reply: string;
  thread_id: string;
  suggestions?: ItineraryDelta[];
}

interface ItineraryDelta {
  action: "add" | "update" | "delete" | "move" | "reorder";
  target?: {
    day_index?: number;
    item_id?: string;
    seq?: number;
  };
  payload?: {
    poi_name?: string;
    start_time?: string;
    end_time?: string;
    duration_h?: number;
    notes?: string;
    lat?: number;
    lng?: number;
  };
}
```

#### 流式升级（第二阶段）

- 使用 FastAPI `StreamingResponse` + SSE
- 前端 `fetch` + `ReadableStream` 逐步展示
- 建议卡片可以在流结束前先出现

### 5.4 AI 修改落地

- AI 不直接改数据库
- 返回 `suggestions`
- 用户点击“采纳”后：
  ```text
  前端调用对应 REST mutation
  后端写库
  React Query invalidate / store 更新
  地图和列表自动刷新
  ```

### 5.5 验收标准

- 行程页始终有可用的 AI 对话入口
- 对话能感知当前 Day / Item
- AI 建议以“可采纳卡片”呈现
- 采纳后地图、列表、时间线即时更新
- 导入攻略入口统一到对话面板

---

## 6. Phase D：长短期记忆与上下文管理

### 6.1 短期记忆

- 现有 PostgresSaver 继续作为短期对话记忆
- 行程相关对话统一使用：
  ```text
  thread_id = trip-{trip_id}
  ```
- 保留最近 N 轮原始消息 + 自动摘要

### 6.2 长期记忆

| 数据 | 来源 | 用途 |
|---|---|---|
| 用户偏好 | `trip.user_prompt` / `must_visit` / 历史对话 | 下一次规划参考 |
| 历史行程 | `trips` + `itinerary_items` | 跨 trip 推荐、避免重复 |
| 已选 POI | `source_entities` / 导入记录 | 攻略候选去重 |
| 时效信息 | `fact_checks` | 开放时间/天气风险记忆 |
| 用户编辑 | `itinerary_items` 的 notes/时间/顺序 | 作为高优先级事实 |

### 6.3 上下文压缩策略

1. 消息数超过阈值后，生成“对话摘要”
2. 摘要写入 `thread_id` 对应旁路存储或 `memory_summaries` 表
3. 新请求 = 摘要 + 最近 M 条消息 + 当前行程结构化数据 + 当前焦点上下文
4. 不把完整 `route_polyline` 塞给 LLM，只传必要坐标摘要

### 6.4 记忆优先级

```text
用户手动编辑 > 用户确认的 AI 修改 > AI 生成建议 > 默认模板
```

将来可在 item 上增加：

```text
source: "user" | "ai_accepted" | "ai_suggested" | "generated"
```

---

## 7. 开发排期建议

| 阶段 | 内容 | 预计工作量 | 可独立上线 |
|---|---|---|---|
| A | 点位编号 + 列表/地图双向聚焦 | 1-2 天 | ✅ |
| B | Zustand 统一数据源 + 编辑重排实时联动 + 后端增删/geocode/reoptimize | 3-5 天 | ✅ |
| C1 | 常驻对话布局 + 同步聊天 + 建议卡片 + 采纳落地 | 4-6 天 | ✅（无流式） |
| C2 | SSE 流式回复 | 2-3 天 | ✅ |
| D | 长短期记忆 + 上下文摘要 | 3-5 天 | ✅（可增量） |

### 建议落地顺序

```text
Phase A
  ↓
Phase B
  ↓
Phase C1
  ↓
Phase C2
  ↓
Phase D
```

- Phase A 先解决“看得懂”
- Phase B 解决“改得动且一致”
- Phase C 解决“聊得起来并真的能改行程”
- Phase D 解决“越用越懂用户”

---

## 8. 风险与取舍

1. **地图 API 高亮/动画效果**
   - 高德 JS API 的 Marker 自定义 DOM 样式可控
   - 但动画效果要避免过度复杂，保持 2-3 秒内恢复

2. **编辑名称后 geocode 可能失败**
   - 失败时保留旧坐标，前端提示“定位失败，可手动调整”
   - 不能因为 geocode 失败阻断用户保存

3. **AI 直接改库风险**
   - 第一版必须“建议-采纳”分离，不允许 AI 自动落库
   - 后续即使放开，也要保存 delta 记录和快照

4. **对话上下文体积**
   - 不要把整份行程 JSON 无脑塞进 prompt
   - 需要结构化裁剪：当天 items、当前焦点、最近修改

5. **SSE / 长连接成本**
   - 当前 Railway 部署为同步请求，第一版可先不做流式
   - 流式作为 C2 单独验证，避免和核心交互混在一起

---

## 9. 测试策略

- Phase A：
  - 前端单元/交互测试：编号渲染、focus 状态、scrollIntoView
- Phase B：
  - 后端：item add/delete、name geocode、day reoptimize
  - 前端：store 乐观更新、地图重绘次数
- Phase C：
  - 后端：chat + trip context、delta 校验
  - 前端：建议卡片、采纳后刷新
- Phase D：
  - 上下文压缩、记忆优先级、摘要持久化