# 2026-09-04 复盘：一次规划 + 确定性路线（生成变快）

开发内容：首页从零生成不再让 Agent 工具循环查路时，也不再为调用 `optimize_itinerary` 单独开一个 Agent。规划一次出 JSON，Python 补坐标和通勤。Job 增加可展开的 `stages`。本机实测明显变快。

分支：`feature/one-shot-generation`。

---

## 问题速查表

| # | 类别 | 问题 | 解法 |
|---|------|------|------|
| 1 | 延迟 | 三天行程进度长期停在约 30% | 不是 TUN。规划 Agent 在循环调 `get_travel_time` |
| 2 | 多余 Agent | `route_optimizer` Agent 只为调用已经写好的函数 | `generate_itinerary_draft` 直调 `optimize_itinerary()` |
| 3 | 失败路径 | 地理编码弱匹配再打 MiniMax 消歧义 | 删 `_disambiguate_with_llm`，按名称匹配，失败降级 |
| 4 | 产品 | 把「搜 2–3 篇攻略」当成从零生成的内部步骤 | 入口 A / 入口 B 汇入同一候选池，不是套娃 |
| 5 | 文档过时 | 知识地图仍写 itinerary_gen 调 `get_travel_time` | 生成主路径工具只留 `search_attractions` |
| 6 | 可见性 | 只有百分比，用户不知道卡在规划还是排路 | `stages`：prepare → plan → route → done |

---

## 错误清单

### 1. 慢的是 Agent 循环，不是模型智商

**现象**：进度条停在「正在规划景点」（约 30%）很久。

**误判**：MiniMax 慢、没开代理、要上 Redis。

**真因**：`itinerary_gen` 拿了 `get_travel_time`。N 个景点两两查路时 = 很多次模型 round-trip。Worker 在进规划时就把阶段打到 30%，工具循环期间阶段不前进。

**解法**：

```
ITINERARY_GEN_TOOLS = [search_attractions]
travel_minutes_from_prev 一律填 0
路时由 optimize_itinerary 回填
```

**和 5 月原则的关系**：5 月已经写了「确定性计算留给 Tool」「Agent 不要内部循环调 Tool」。生成路径当时为了「学习链式 Agent」，把 `get_travel_time` 留给了规划 Agent，又把粗粒度 Tool 再包成 Agent。学习目标达成后，这个形状变成了线上延迟。**原则没变，用错了层。**

---

### 2. 为调用函数再开一个 Agent，是付「决定调用」的税

**5 月设计**（见 Step 5）：`itinerary_gen` Agent → 服务层 → `route_optimizer` Agent → 调一次 `optimize_itinerary`。目的是学会链式调用。

**9 月现实**：生成是固定管道「规划 JSON → 补路」。第二个 Agent 的唯一工作是决定调用一个本来就会调用的函数。多一次 MiniMax round-trip，零决策收益。

**解法**：生成主路径服务层直调函数。`route_optimizer` Agent 文件仍可留给聊天 / Supervisor 按需 handoff。面试时说「生成路径不再经过这个 Agent」，不要说「仓库里没有这个角色」。

---

### 3. 弱匹配不要再变成一次生成

地理编码不准时再问 LLM「这是哪个点」，失败路径变成又一次生成，而且不稳定。

**解法**：名称匹配；匹配不上走原有 mock / 降级。消歧义不是生成主路径该付的模型税。

对比 S10：POI「是不是同一个」是语义判断，给 LLM；「这个名字在高德里的坐标」是查找，给 API 和缓存。同一棵决策树，叶子不同。

---

### 4. 入口 A 不是入口 B 的中间步骤

**误判**：从零生成应该先替用户搜 2–3 篇攻略，再勾选，再排路。圆周旅迹「抄作业」被理解成生成管道的内嵌阶段。

**纠正**：

| 入口 | 用户带来什么 | 贵在哪 |
|------|--------------|--------|
| A 贴攻略 | 链接 / 文本 | 抽取 + 勾选 |
| B 从零生成 | 目的地和日期 | 一次规划选点 |
| 代搜攻略 | 系统去搜 | 搜索确认（第三种填候选） |

A 和 B 汇入同一份候选 POI，再进同一个 `optimize_itinerary`。A 替换的是 B 里最贵的「让模型选点」，不是把 B 嵌套进 A。

当前首页默认是 B 的一次规划。A 有页面，但不是这条生成 Job 的内部步骤。

---

## 关键洞察

> 5 月学「链式 Agent」时，第二个 Agent 是教学支架。9 月发现生成管道是确定性的：第二个 Agent 应该拆掉，Tool 留下。  
> 「多智能体」不是性能故事。这次变快，是因为少用 Agent。

决策树补一条：

```
这段逻辑每次都必须发生，且没有意图分支？
  ├── 是 → Service 直调函数 / 粗粒度 Tool
  └── 否，要按用户话决定做不做 → 才配得上一个 Agent 或 Handoff
```

---

## 本日技术收获

1. 延迟优化先数 **LLM round-trip**，再谈 GPU 和代理。
2. `stages` 必须 fencing：过期 token 不能追加阶段，且成功写入要 bump `status_version` 才能推 SSE。
3. pytest 默认排除 agent 测试；命名会误伤纯单测。
4. 不报未经测量的秒数。口述只用「本机实测快了很多」。

---

## 面试钩子

- 现象：「进度条停在 30%，用户以为挂了。」
- 误判：「我以为是模型慢。」
- 原则：「路时是计算，不是生成。」
- 开门：「如果你问我为什么还留着 route_optimizer Agent 文件……」

不要用「上了多智能体所以更快」解释这个改动。

---

## 与已有知识的串联

- [§10 反模式：Agent 内部循环调 Tool](knowledge-map.md#10-agent-设计原则定位粒度与边界) — 本次是这条反模式的生产案例
- [§11 路线优化](knowledge-map.md#11-路线优化从-mock-到真实-api-路径排序) — `optimize_itinerary` 内部闭环仍然成立，变的是谁来调用它
- [§13 决策树](knowledge-map.md#13-llm-优势边界与设计决策树) — 路时 = 确定性计算
- [S9-S10 设计转向](2026-05-21_S9-S10-Design-Pivot.md) — 同类：用错工具装专业
- [可靠 Job](2026-09-03_Reliable-Generation-Jobs.md) — 先保证任务不丢，再保证任务不空转
