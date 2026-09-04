# AI 旅行规划助手 V3：技术开发路线

> 日期：2026-09-04  
> 配套：[requirements-v3.md](requirements-v3.md)  
> 原则：LLM 做选择，代码做计算与状态；页面已分流的功能不用主管再选一遍。

与 ADR-0001（同步 + 异步 + SSE）一致：生成走 Job；协作走行程内聊天。与 CONTEXT 里「`POST /api/v1/chat` 收归主管」**冲突**——该入口降为学习遗留，产品聊天为 `POST /trips/{id}/chat`。

---

## 1. 现行架构（以代码为准）

```
React
  ├ 首页 suggest + POST /trips + Job SSE（fill / route / verify）
  ├ 攻略 存文本 → parse → 勾选 → 带 selected_entities 创建 Job（不再从零套娃）
  └ 行程 编辑 / reoptimize 函数 / chat 一次 LLM 出 Delta

FastAPI
  ├ Worker: fill（候选 JSON 或 itinerary_gen）→ optimize_itinerary() → verify
  ├ trip_editor.apply_delta（写库唯一入口之一）
  ├ guide_parser / fact_checker / supervisor 文件存在
  └ POST /api/v1/chat 前端未接
```

生成路径已是任务图。协作路径仍是「一 LLM 出 Delta」。P2 再做成行程协作图。

---

## 2. 目标架构

```
              ┌──────────── 生成 Job（固定任务图）────────────┐
入口 A 勾选 ─►│ fill：候选 JSON 或 itinerary_gen              │
入口 B 表单 ─►│ route：optimize_itinerary()                   │
              │ verify：规则 + weather/opening_hours          │
              └──────────── persist + stages ─────────────────┘
                                      │
                                      ▼
              ┌──────────── 行程协作图（动态，P2）─────────────┐
入口 侧栏对话 ►│ Agent 自选工具（可 0/1/多个）                  │
              │ propose/apply_delta · check_facts · parse_guide │
              │ 写库只经 apply_delta；模式：只提议 / 授权后自动采纳 │
              └───────────────────────────────────────────────┘
```

两种编排不要合成一个 Supervisor：生成依赖固定用 Job 图；协作用带工具的行程协作图，由模型选工具。

---

## 3. 阶段与工期（按一人兼职）

| 阶段 | 目标 | 大约 | 状态 |
|------|------|------|------|
| P0 | 一次规划 + 可靠 Job + Delta 聊天 | — | **已完成** |
| P1 | 抄作业环合格：候选 fill + 解开套娃 + Job.verify | 3–5 天 | **已完成** |
| P2 | 行程协作图：工具自选 + 提议/自动采纳模式 | 4–6 天 | 下一步 |
| P3 | 源归属、行程乐观锁 409、文档/简历对齐 | 2–3 天 | 可与 P2 后半并行 |
| P4 | 搜索确认填候选（V2 入口 C） | 另开 | 非本窗口必须 |

每阶段：测试 → 浏览器走验收脚本 → 停下来确认再进入下一阶段。

---

## 4. P1 技术要点

**Job 输入增加候选。** `TripCreate` 或 Job payload：`selected_entities: [{poi_name, day_index, seq, lat, lng, ...}]`。有列表则 fill 跳过 `itinerary_gen`。

**攻略页 `handleCreateAndImport`。** 带候选创建 Job，去掉「先 `POST /trips` 再 `waitForGenerationJob` 再 import」。导入已有行程仍可只写节点 + `reoptimize_day`。

**Worker 顺序。** `fill` → `route` → `verify`。verify 抽 `facts.py` 的规则 + Agent/工具为 Service 函数，避免 HTTP 自调用。校验异常：记 warning stage，Job 仍可 succeeded（带风险）。

**stages。** `fill` / `route` / `verify` / `done`。从零时 fill 文案为规划；有候选时为「正在按勾选排行程」。

**测试。** 有候选则 mock 证明 `create_itinerary_gen` 未被调用；无候选则仍调用。双 Worker / token fencing 回归。

**不做。** LangGraph 重写 Worker；接 Supervisor；Redis。

---

## 5. P2 技术要点

**形态：行程协作图**（LangGraph），与生成 Job 任务图分开。不要先做「分类器硬路由到单一专家」——协作 Agent **自己决定用哪些工具**，一轮可以 1 个或多个（也可以 0 个只回复）。

改 `_run_trip_chat`。前端仍以 `reply` + `suggestions` + SSE 为主；自动采纳时增加 `applied` 类事件，刷新 Trip。

**记忆。** Checkpointer thread 前缀 `trip-chat-{id}`，与生成 `trip-{id}` 隔离。每轮从 DB 重新加载行程 JSON（行程真源是库，不是对话记忆）。

**工具（实现为 Service，Agent 只负责选）。**

| 工具 | 作用 |
|------|------|
| `propose_delta` | 只提议，不写库（默认模式） |
| `apply_delta` | 调用现有 `trip_editor.apply_delta`；仅「授权后自动采纳」模式可调 |
| `check_facts` | 复用规则引擎 + weather/opening_hours（或 `create_fact_checker`），风险写成 reply，可选附 Delta |
| `parse_guide` | 复用 `guide_parser`，实体转 add Delta |

**写库策略（对话旁模式切换，类似 Claude Code）：**

- **只提议**（默认，现状）：Agent 不得调 `apply_delta`；用户点采纳。  
- **授权后自动采纳**：用户打开该模式后，本会话允许 Agent 调 `apply_delta`，前端立刻刷新列表/地图。

模式存在前端并随聊天请求传给后端。不要做成永远自动写。

**禁令。** 不调用 `itinerary_gen`、`create_route_optimizer`、无行程 `create_supervisor_agent`。不把 `POST /api/v1/chat` 接到行程页。排路仍在 add/reorder 之后走 `reoptimize_day`。

先上编辑+核验工具（能演示「问天气」和「删掉某点」），parse 工具第二天。

---

## 6. P3 技术要点

- `ItineraryItem.source_id` / `source_name`（V2 B5）。  
- `trip.version` + `expected_version` → 409（V1 并发口径，仍不做 Redis 锁）。  
- README：生成任务图、协作路由、`/api/v1/chat` 为遗留。  
- `CONTEXT.md` 关系节与 ADR 冲突处加 2026-09 修正（本文已声明）。

---

## 7. 模块职责（防再包装）

| 层 | 允许 | 不允许 |
|----|------|--------|
| Agent | 选点、抽文本、选查哪些时效工具、出 Delta | 写库、算路时、领 Job |
| Service / Worker | 任务图、事务、apply_delta、调 `optimize_itinerary` | 让 LLM 决定「要不要排路」 |
| Tool | 高德/天气闭环与降级 | 把整个排路再包成 Agent |
| API | HTTP、SSE、schema | 在路由里 invoke 四个专家 |

---

## 8. 风险

| 风险 | 缓解 |
|------|------|
| verify 拖慢生成 | 超时短、失败降级；阶段仍要推进到 done |
| 协作误用工具 | 默认只提议，不把 apply_delta 交给该模式；提示用户可改口 |
| 解析 Delta 插错天 | 必须带 day_index；采纳前摘要给用户看 |
| Checkpointer 串台 | 生成与协作 thread 前缀分开 |

---

## 9. 进入 P1 前的冻结项

开始写 P1 代码前确认：

1. 候选 fill 用 Job payload，不先做搜索入口 C。  
2. verify 失败不阻止 succeeded。  
3. P2 不把通用 Supervisor 接到行程页。  

P1 冻结项已确认并完成。进入 P2 前已确认：行程协作图、工具由 Agent 自选、写库分「只提议 / 授权后自动采纳」两模式。按 P2 → P3 开发；每阶段结束用需求文档 §7 演示脚本验收。
