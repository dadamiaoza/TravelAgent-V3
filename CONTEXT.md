# AI 旅行规划助手

面向年轻自由行用户的"抄作业型 AI 行程编辑器"——导入攻略、解析、生成可执行行程、节点级编辑、时效校验。

## 语言

### 输入与解析

**源材料** (Source):
用户导入的原始链接、图片或文本内容。
_Avoid_: 攻略原文、原始攻略、导入内容

**候选列表** (Candidate List):
从源材料中提取的结构化 POI、时间、偏好，待用户勾选确认。
_Avoid_: 解析结果、抽取内容

**源材料实体** (Source Entity):
候选列表中的单条结构化信息（如一个景点、一个时间段、一个预算区间）。
_Avoid_: 候选点、解析条目

### 行程

**行程** (Itinerary):
系统生成的、按"天-时段-地点"组织的完整旅行计划。由若干行程节点组成。
_Avoid_: 攻略、计划、方案

**行程节点** (Itinerary Item):
行程中的单个原子项——一个 POI 在特定日期的特定时段（如"Day1 09:00-11:00 故宫"）。
_Avoid_: 打卡点、行程条目、行程项

**约束** (Constraints):
影响行程生成的用户偏好——时间、地点、人数、预算范围、必去/避开地点等。
_Avoid_: 条件、限制、参数

### Agent 状态

**状态** (State):
Agent 在单次 `invoke` 内部持有的数据集合（LangGraph StateGraph）。包含 `messages` 字段（全量对话历史）和自定义字段（如已规划 POI 集合、当前天数等策略性摘要）。State 是"此刻有什么"。
_Avoid_: 上下文、session、运行时数据

**记忆** (Memory):
将 State 跨轮次持久化的机制（LangGraph Checkpointer）。把 State 内容（messages + 自定义字段）序列化存入 PostgreSQL。同一 `thread_id` 下后续 `invoke` 恢复上次的 State，Agent 得以"记住"之前的决策。Memory 是"如何把此刻存下来给下次用"。
_Avoid_: 对话记忆、聊天记录、缓存

**Checkpointer** (检查点存储器):
LangGraph 中实现 Memory 的具体组件。内置三种：`MemorySaver`（内存，开发用）、`SqliteSaver`（本地文件）、`PostgresSaver`（PG，本项目选择）。
_Avoid_: 持久化层、存储后端

**上下文隔离** (Context Isolation):
每个行程拥有独立的 State 线程（`thread_id = trip-{trip_id}`），一个行程的规划决策不会污染另一个行程。
_Avoid_: 会话隔离、线程、对话隔离

### 可信与优化

**时效校验** (Fact Check):
对关键信息的更新时间与过期风险进行评估（天气、开放时间、交通状况），输出风险等级。
_Avoid_: 准确性检查、信息验证

**路线优化** (Route Optimization):
基于地理坐标减少行程折返与不合理通勤的节点重排。由 route_optimizer Agent 自动执行。
_Avoid_: 路径规划、路线规划

**链式 Agent 调用** (Chained Agent Invocation):
一种 Agent 编排模式：上游 Agent 的输出作为下游 Agent 的输入，在服务层按顺序串联调用。与 Supervisor 模式（Agent 互相感知）不同，链式调用中各 Agent 互不知晓。
_Avoid_: Agent 串联、流水线、Pipeline

**版本快照** (Snapshot):
每次行程修改或重算后自动保存的完整行程副本，支持对比与回滚。与**对话记忆**不同——对话记忆存 Agent 状态，版本快照存行程数据结果。
_Avoid_: 历史记录、备份

## 关系

- 一个**行程**包含若干**行程节点**
- 一份**源材料**经过解析产生若干**源材料实体**
- 用户勾选**源材料实体**后写入**行程节点**
- 每次修改**行程节点**后自动生成新的**版本快照**
- **时效校验**作用于**行程节点**，产出风险评估
- **路线优化**作用于**行程节点**，产出重排后的节点序列并回填地理坐标
- itinerary_gen Agent 输出 → route_optimizer Agent 输入，构成**链式 Agent 调用**
- 每个**行程**拥有独立的**对话记忆**（`thread_id = trip-{trip_id}`），Agent 状态不跨行程泄露
- **对话记忆**和**版本快照**是两种不同的记忆——前者存 Agent 对话状态，后者存行程数据副本

## 示例对话

> **Dev:** "用户导入了一篇小红书帖子，这叫什么？"
> **领域专家:** "一份**源材料**。系统解析后会产出**候选列表**——若干**源材料实体**，用户勾选后写入**行程**成为**行程节点**。"
>
> **Dev:** "如果用户修改了一个节点的时间，会触发什么？"
> **领域专家:** "修改**行程节点**后自动生成新的**版本快照**，同时触发**时效校验**——因为时间变了，天气和开放时间可能需要重新确认。"

## 已标记的歧义

- "攻略" 曾被用于指代源材料、候选列表和行程三个不同概念 —— 已拆分。

## 架构决策

### 记忆系统设计

- **两种记忆并存**：对话记忆（LangGraph PostgresSaver）+ 版本快照（DB Snapshot 表）
- **Checkpointer 选型**：PostgresSaver（跨重启持久化，复用现有 PostgreSQL）
- **上下文隔离粒度**：`thread_id = trip-{trip_id}`（按行程隔离，避免跨行程上下文污染）
- **建表管理**：Alembic migration 管理 checkpointer 表（统一入口，避免隐式初始化）
- **实现顺序**：先 PostgresSaver（Agent 记忆持久化），后 Snapshot（数据快照）

### Step 5 路线优化设计

- **触发方式**：自动触发（generate_itinerary 末尾串联调用）
- **实现模式**：Agent + Tool（route_optimizer Agent + optimize_itinerary Tool）
- **编排方式**：服务层串联（itinerary_gen → route_optimizer 顺序调用）
- **Tool 粒度**：粗粒度单 Tool（一次性处理所有天，Agent 只调一次）
- **坐标策略**：optimize_itinerary 顺带 geocode + 回填 lat/lng，Step 5 保持原序不排序
- **高德 MCP**：延后至 Step 7，与真实路径规划统一接入
- **Memory**：不加 Checkpointer（一次性优化，无多轮需求）
