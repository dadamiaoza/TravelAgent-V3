# 2026-05-18 复盘：Step 5 route_optimizer 链式 Agent 调用 — 设计讨论

开发内容：用 grill-with-docs 对 Step 5（route_optimizer）做了完整的架构设计讨论。核心学习点是**链式 Agent 调用**（A Agent 输出 → B Agent 输入）。

---

## 问题速查表

| # | 决策项 | 结论 |
|---|--------|------|
| 1 | 触发时机：自动还是手动？ | 自动触发（generate 末尾），MVP 用户不需要感知优化步骤 |
| 2 | 实现方式：Agent 还是纯函数？ | Agent + Tool 模式，学习链式调用的核心模式 |
| 3 | Tool 粒度：细还是粗？ | 粗粒度 `optimize_itinerary`，排序算法确定性，不应交给 LLM |
| 4 | 高德 MCP：现在还是以后？ | Step 7 再引入，不叠加复杂度 |
| 5 | 调用链位置：服务层还是 Agent 层？ | 服务层串联，两个 Agent 互不知晓 |
| 6 | lat/lng 回填：顺带还是以后？ | 顺带填充，接口稳定，Step 7 只换内部实现 |
| 7 | 多天处理：逐天还是一起？ | 一次性传入所有天，Tool 内部遍历 |
| 8 | 排序算法：现在做还是以后？ | 保持原序，Step 7 接入高德路径规划时再做真实排序 |
| 9 | Checkpointer：要加吗？ | 不加，一次性优化场景不需要多轮记忆 |

---

## 核心概念：链式 Agent 调用

### 什么是链式调用

服务层串联两个独立 Agent，第一个的输出作为第二个的输入。两个 Agent **互不知晓**，各自有独立的 prompt 和 Tool 列表。

```
Service 层（胶水代码）
  │
  ├─→ Agent A（itinerary_gen）    生成行程 JSON
  │     │
  │     └─→ Agent B（route_optimizer）  优化行程 JSON
  │           │
  │           └─→ 写入 DB
```

### 链式调用 vs Agent 编排

| | 链式调用（Step 5） | Agent 编排（Step 6 Supervisor） |
|---|---|---|
| Agent 关系 | 互不知晓 | Agent 互相感知 |
| 控制权 | 服务层代码控制顺序 | Supervisor Agent 决策 |
| 数据传递 | 服务层传 JSON | Agent 消息协议 |
| 适用场景 | 管道式处理 | 分支/并行/回退 |
| 复杂度 | 低 | 高 |

**为什么先学链式再学编排？** 链式调用让你理解 Agent 作为"独立处理单元"的概念——每个 Agent 像一个黑盒服务，输入输出清晰。编排模式在此基础上叠加了"Agent 间通信"的维度。

---

## Tool 设计哲学：粗粒度 vs 细粒度

**决定因素：该逻辑是否适合让 LLM 决策？**

```
确定性算法（排序、计算）→ 粗粒度 Tool，内部封装
不确定性决策（搜索条件、校验标准）→ 细粒度 Tool，LLM 编排
```

| Tool | 粒度 | 原因 |
|------|------|------|
| `search_attractions(destination, preference)` | 细 | LLM 决定搜什么偏好 |
| `get_weather(poi, date)` | 细 | LLM 决定何时需要查天气 |
| `optimize_itinerary(itinerary_json)` | 粗 | 算法决定排序，LLM 只负责调用 |

将路径排序逻辑封装在 Tool 内部（粗粒度），Agent 不需要"懂算法"——只需要知道"这个 Tool 能优化路线"。

---

## 什么时候加 Checkpointer？

| 特征 | 加 | 不加 |
|------|:--:|:----:|
| 多轮对话（分步规划） | ✓ | |
| 跨重启记忆 | ✓ | |
| 需要记住用户偏好 | ✓ | |
| 一次性处理、无后续交互 | | ✓ |
| 输入完整、输出确定 | | ✓ |

- **itinerary_gen**：需要 Memory（多轮规划不重复 POI → PostgresSaver）
- **route_optimizer**：不需要 Memory（一次性优化，输入完整）

---

## 可扩展性设计

Step 5 → Step 7 的升级路径：

```
Step 5（现在）
  optimize_itinerary Tool:
    mock geocode_poi → 保持原序 → 返回带 lat/lng 的 JSON

Step 7（将来）
  optimize_itinerary Tool:
    高德地理编码 → 高德路径规划 → 最近邻排序 → 返回带 lat/lng 的 JSON

接口不变 → 服务层和 Agent prompt 都不需要改动
```

**原则**：设计 Tool 时保证接口稳定，把变化收敛在 Tool 内部实现。改动面最小化。

---

## 关键洞察

> 链式 Agent 调用的本质是"用服务层做胶水，Agent 做黑盒处理单元"。每个 Agent 独立负责一个明确的任务，服务层控制数据流。这和 Step 6 的 Supervisor 模式不同——一个是管道式处理，一个是对话式编排。先掌握管道，再理解编排。
