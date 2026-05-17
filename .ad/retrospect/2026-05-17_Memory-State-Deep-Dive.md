# 2026-05-17 复盘：Step 4 Memory/State 深度学习

开发内容：对 Memory（Checkpointer）和 State 的 grill-with-docs 深度讨论，澄清了三个容易混淆的概念对。

---

## 问题速查表

| # | 问题 | 结论 |
|---|------|------|
| 1 | 版本快照 = Agent 状态？ | 否。快照存行程数据（产出物），Checkpointer 存对话过程（生产过程） |
| 2 | Memory 和 State 是同一个东西？ | 否。State 是"此刻有什么"，Memory 是"如何存下来给下次用" |
| 3 | 对话记忆粒度怎么选？ | 按行程隔离（`trip-{trip_id}`），避免跨行程上下文污染 |

---

## 澄清一：版本快照 ≠ Agent 状态

| | 版本快照 (Snapshot) | Agent 状态 (Checkpointer) |
|---|---|---|
| 存什么 | 行程数据（**产出物**） | 对话过程（**生产过程**） |
| 内容 | POI 列表、时间、坐标 | 聊天记录、Tool 调用、中间推理 |
| 类比 | 一张"成品照片" | 一段"操作录像" |
| 用途 | 回滚到某个版本的行程 | 继续之前没说完的对话 |

```
Snapshot  ← 数据备份
Agent 状态 ← 思维备份
```

---

## 澄清二：Memory ≠ State

| 概念 | 层级 | 定义 | LangGraph 里叫什么 |
|------|------|------|-------------------|
| "全量历史" | 数据 | 所有对话轮次的 messages，有噪音 | `messages` 字段 |
| "精简摘要" | 数据 | 自定义字段（如 planned_pois、current_day），干净可决策 | 自定义 State schema 字段 |
| State | 数据集合 | messages + 自定义字段，是"此刻有什么" | `TypedDict`（StateGraph） |
| Memory | 持久化机制 | 把 State 序列化存储，下次 invoke 恢复 | `Checkpointer` |

用户原本的理解模型完全正确，只是需要换个名字：
- 用户心中的 "Memory" → `messages` 字段（全量历史）
- 用户心中的 "State" → 自定义 State 字段（精简摘要）
- LangGraph 的 "Memory" → 把上面两样都存下来的机制

### 从概念到代码

```python
# State — Agent 此时此刻的数据
result = agent.invoke({"messages": [...]})
result["messages"]  # 全量历史

# Memory — 把 State 持久化，下次能恢复
agent.invoke(
    {"messages": [{"role": "user", "content": "规划 Day2"}]},
    config={"configurable": {"thread_id": "trip-123"}}  # ← Memory 靠 thread_id 寻址
)
```

### Levels of Memory（LangGraph 文档概念）

```
Level 0: 无 Memory          ← Step 1-3（fact_checker, guide_parser）
Level 1: Memory = 消息列表   ← Step 4 当前（itinerary_gen 用 MemorySaver）
Level 2: Memory = 摘要字段   ← 未来（自定义 State schema 字段）
Level 3: Memory = 外部存储   ← 未来（向量数据库、知识图谱）
```

---

## 本日架构决策（已写入 CONTEXT.md）

1. **两种记忆并存**：对话记忆（LangGraph PostgresSaver）+ 版本快照（DB Snapshot 表）
2. **Checkpointer 选型**：PostgresSaver（跨重启持久化，复用现有 PG）
3. **上下文隔离粒度**：`thread_id = trip-{trip_id}`（按行程隔离）
4. **建表管理**：Alembic migration 管理 checkpointer 表（统一入口）
5. **实现顺序**：先 PostgresSaver，后 Snapshot

---

## 当前 LEVEL of Memory

```
Level 0  □  fact_checker / guide_parser（无状态，每次 invoke 独立）
Level 1  ■  itinerary_gen（MemorySaver → 即将升级 PostgresSaver）
Level 2  □  自定义 State schema 字段
Level 3  □  外部向量存储
```

---

## 关键洞察

> 在概念设计上可以超前（想清楚 Memory/State/Snapshot 的区别和分工），
> 在工程实现上必须渐进（先 MemorySaver，再 PostgresSaver，最后 Snapshot）。
> 两者的节奏不必同步——概念清晰是工程安全的前提。
