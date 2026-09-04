# 2026-09-04 复盘：Agent 过度包装 vs 一条 Workflow

**感觉**：vibe coding 时把能写死的步骤包成 Agent，系统变慢、变难测、自己也讲不清「现在到底怎么跑」。

**对照**：当前真实调用链写在 [knowledge-map.md §0](knowledge-map.md#0-先看这个项目现在实际怎么跑)。本节只留问题表和判断标准。

---

## 问题速查表

| # | 包装 | 实际 | 该不该是 Agent |
|---|------|------|----------------|
| 1 | `route_optimizer` Agent | 生成 / 重算都直调 `optimize_itinerary()` | 否。壳还在，主路径已绕开 |
| 2 | `supervisor` + `POST /api/v1/chat` | 前端聊天走 `POST /trips/{id}/chat/stream` | 否。教学入口，UI 不用 |
| 3 | 规划后再 handoff 路线 Agent | 生成是固定「JSON → 函数」 | 否。这就是进度条卡 30% 的形状 |
| 4 | `guide_parser` 挂 MCP 搜+抓 | 攻略页只贴文本再 parse | 半。粘贴路径用一次 LLM 抽 JSON 就够 |
| 5 | 「根据攻略创建」先 `POST /trips` | 会先跑从零生成，再 import 勾选 POI | 否。产品套娃，A 被塞进 B |
| 6 | `itinerary_gen` Agent | 选点、分天事先不知道 | **是**。工具只留搜景点之后，厚度才合理 |
| 7 | 行程聊天做成 Supervisor | 一次 LLM 出 Delta，用户点采纳 | 否。已经是 Workflow，别再加厚 |
| 8 | Job / SSE / Checkpointer | 任务生死、进度、多轮记忆 | 不是 Agent。不要和编排混为一谈 |

---

## 判断标准（可背）

```
顺序固定、每次都发生  →  Workflow（函数 / Worker）
工具次数事先不知道    →  单 Agent
连「走哪条产品功能」都不知道，且没有分页面  →  Supervisor
```

第三条在本项目不成立：首页、攻略页、行程页已经把功能切开了。再做一个万能 `/chat` Supervisor，是给不存在的入口做编排。

---

## 和 5 月笔记的关系

5 月 §8/§9 没有写错「链式 / Supervisor 是什么」。写错的是**把它们当成产品默认形状**。

学习顺序可以是：先 Agent 壳，再发现壳是空的。生产顺序应该反过来：先 Workflow，只有出现真正的不确定步骤再加 Agent。

S10 规则管线、9 月路线 Agent 壳，是同一类错：用更重的抽象装专业。

---

## 面试一句话

> 仓库里有五个 Agent 文件，但用户真正走的生成路径只有一个 Agent 在选点。排路、任务状态、行程聊天都是写死的 workflow。多智能体编排的入口前端没用。

下一问：「那为什么还留着 Supervisor？」→ 学习遗留，prompt 已经和生成主路径矛盾，拆之前要承认这一点。
