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

**外部搜索** (External Search):
通过 MCP 协议接入外部搜索引擎，让 LLM 自行决定何时搜索、搜什么关键词。与 Tool 函数不同——Tool 是代码控制调用，MCP 是 LLM 自主发现和调用。用于"搜杭州攻略"这类开放性搜索场景。
_Avoid_: 联网搜索、网页搜索

**外部抓取** (External Scrape):
通过 MCP 协议接入网页抓取工具，将 URL 指向的网页转换为结构化文本供后续解析。通常与**外部搜索**配合——搜到链接 → 抓取内容 → 传给 guide_parser 解析。
_Avoid_: 网页抓取、内容提取、爬虫

**搜索确认** (Search Confirmation):
搜索与抓取之间的中间步骤：搜索结果以链接列表呈现给用户，用户勾选确认后再抓取。避免无效抓取，给用户控制权。
_Avoid_: 搜索结果展示、链接选择

**多源合并去重** (Multi-Source Merge & Dedup):
将多篇攻略各自解析的候选列表合并为一份，同名 POI 去重并按提及次数排序。合并策略分三层：归一化 + 别名/精确匹配 + 同城模糊匹配（基础层），geocode 匹配和 LLM 语义匹配为可按需开启的增强层。
_Avoid_: 结果合并、去重、聚合

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

**源归属** (Source Attribution):
追踪每个行程节点来自哪篇攻略，通过 `ItineraryItem` 的 `source_id` / `source_name` 字段记录。方便用户回溯原文确认细节。与**多源合并去重**配合——合并时保留来源信息，写入行程时标注出处。
_Avoid_: 来源标注、出处追踪

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

**上下文修剪** (Context Trimming):
防止 Agent 消息历史无限膨胀的策略。默认阈值：消息超过 25 条或 token 估算超限时触发。触发后保留最近 10 条原始消息，旧消息用 LLM 摘要替换为一条 `[历史摘要]` 消息。先只做 itinerary_gen，Supervisor 后续单独处理。与**结构化任务摘要**配合——修剪保证上下文不爆，摘要保证关键信息不丢。
_Avoid_: 上下文压缩、消息裁剪

**结构化任务摘要** (Structured Task State):
从 DB 读取的、独立于消息列表的结构化当前任务信息（已规划的 POI 集合、剩余天数、预算范围），以纯文本注入 system_prompt。数据源以 DB 为准（非从消息解析）。规则放 system_prompt，状态放结构化上下文。与**记忆**互补：记忆存"过程"（消息历史），摘要存"结论"（当前局面）。
_Avoid_: 任务状态、当前进度、上下文概要

### MCP 集成

**MCP 封装层** (MCP Client Wrapper):
对 `langchain_mcp_adapters` 的薄封装层，提供懒加载单例 MCP session。四个核心入口：创建（首次连接）、缓存（复用 session）、异常处理（连接失败 → 空 Tool 列表，Agent 降级）、测试替身（注入 mock Tool）。隔离业务代码与 adapter 实现细节，方便未来切换到方案 B。
_Avoid_: MCP 客户端、适配器封装

**MCP 懒加载** (MCP Lazy Connection):
MCP session 在模块导入时不建立连接，首次调用 `get_tools()` 时才创建。减少启动开销，MCP Server 不可用时不影响 Agent 启动（后续调用时优雅降级）。
_Avoid_: 延迟连接、按需连接

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

**主管 Agent** (Supervisor):
一种多 Agent 编排模式：一个"主管"Agent 管理多个"专家"子 Agent，通过 Tool Calling 机制动态决定将用户请求路由给哪个专家。Supervisor 本身就是一个 Agent，其 Tool 是其他 Agent。
_Avoid_: 调度器、编排器、Orchestrator

**移交 Tool** (Handoff Tool):
Supervisor 模式下自动生成的 Tool，每个子 Agent 对应一个。当 Supervisor 调用该 Tool 时，控制权连同对话消息一起转移给子 Agent。子 Agent 完成后，控制权返回 Supervisor。
_Avoid_: 切换工具、委托工具、路由 Tool

**降级兜底** (Graceful Degradation):
API 不可用（无 Key、超时、限流）时自动切换到备用方案（mock 数据），保证系统不崩溃。对 Agent 透明——Agent 不需要知道"这是真实数据还是估算"。
_Avoid_: 回退、兜底、fallback

**Tool 内部闭环** (Tool Internal Closure):
将确定性多步骤流程（如"地理编码 → 路径规划"）封装在单个 Tool 函数内部，对外只暴露一个 Tool 签名。Agent 看到的是一个原子操作，不需要参与编排中间步骤。与**降级兜底**配合——闭环内的每一步失败都能统一兜底。
_Avoid_: Tool 封装、内部调用

**同名歧义** (Name Ambiguity):
同一个 POI 名称在不同城市可能指向不同地点（如全国有多个"西湖"）。地理编码时传 `city` 参数可消除歧义，否则 API 可能返回错误城市的结果。
_Avoid_: 重名、名称冲突

**贪心最近邻** (Greedy Nearest-Neighbor):
一种路线排序算法：从起点开始，每次都去"下一个最近的未访问 POI"，直到遍历完所有 POI。不保证全局最优（TSP），但对每个日程 3-5 个 POI 的场景影响可忽略。起点固定为 Agent 选定的第一个 POI。
_Avoid_: 贪心算法、最近邻、NN

**Haversine 球面距离** (Haversine Distance):
用经纬度计算地球表面两点间的大圆距离（米）。在路线优化中用于两处：① API 调用前估算距离来决定用步行还是公交；② API 不可用时作为降级估算旅行时间。
_Avoid_: 直线距离、坐标距离

**混合交通方式** (Mixed Transport Mode):
同一日程内 POI 间的通勤方式按距离自动选择——Haversine 距离 < 1.5km 用步行，≥ 1.5km 用公交。比全步行更符合实际，比全公交更精细。
_Avoid_: 多模式、混合路线

**有向旅行时间矩阵** (Directed Travel Time Matrix):
N 个 POI 两两之间的旅行时间构成的 N×(N-1) 矩阵，key 为 `(from_index, to_index)` 原始索引。构建时任一 API 调用失败 → 该日整体降级（避免真实数据与估算数据混合）。
_Avoid_: 距离矩阵、OD 矩阵

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
- `POST /api/v1/chat` 入口收归到**主管 Agent**，主管通过**移交 Tool** 动态调度子 Agent
- `get_travel_time` Tool 内部调用 `geocode_poi` + 高德路径规划 API，构成 **Tool 内部闭环**——Agent 只看到一次 Tool 调用
- 同名 POI（如"西湖"）可出现在多个城市，传 `city` 参数可消除**同名歧义**
- `optimize_itinerary` 用 **Haversine 球面距离** 判断每对 POI 的距离，按阈值自动选择**混合交通方式**（< 1.5km → 步行，≥ 1.5km → 公交）
- 同一日程内 POI 两两之间的旅行时间构成**有向旅行时间矩阵**，任一 API 调用失败 → 该日整体降级
- **贪心最近邻**算法对每日 POI 做排序——固定第一个 POI（Agent 选定的起点），依次找最近的未访问 POI
- **上下文修剪**与**结构化任务摘要**配合——前者控制上下文长度，后者保证关键信息不丢失
- **MCP 封装层**包裹 `langchain_mcp_adapters`，提供**MCP 懒加载**——首次调用 `get_tools()` 时建立连接，失败则优雅降级（空 Tool 列表）
- guide_parser 和 fact_checker 通过**MCP 封装层**各自挂载 Tavily + Firecrawl 工具，互不共享 session（方案 B1）
- **外部搜索**返回链接列表 → **搜索确认**（用户勾选）→ **外部抓取**逐条抓取 → 汇入**源材料**池
- **源材料**池同时接收手动粘贴文本和 MCP 抓取结果，guide_parser 统一处理
- 多篇攻略解析后的候选列表经**多源合并去重**归一为单一候选列表，按提及次数排序
- 用户勾选候选实体写入**行程节点**时，标注**源归属**（`source_id` / `source_name`）
- **结构化任务摘要**的数据源为 DB（`itinerary_items` + `itinerary_days` + `trips` 表），不从消息历史解析

## 示例对话

> **Dev:** "用户导入了一篇小红书帖子，这叫什么？"
> **领域专家:** "一份**源材料**。系统解析后会产出**候选列表**——若干**源材料实体**，用户勾选后写入**行程**成为**行程节点**。"
>
> **Dev:** "如果用户修改了一个节点的时间，会触发什么？"
> **领域专家:** "修改**行程节点**后自动生成新的**版本快照**，同时触发**时效校验**——因为时间变了，天气和开放时间可能需要重新确认。"
>
> **Dev:** "用户说'帮我搜杭州攻略'，流程是怎样的？"
> **领域专家:** "Supervisor 判断意图 → Handoff 到 guide_parser → guide_parser 通过 **MCP 封装层**调 Tavily **外部搜索** → 返回链接列表给用户 **搜索确认** → 用户勾选后调 Firecrawl **外部抓取** → 抓取的 Markdown 汇入**源材料**池 → guide_parser 解析为**候选列表**。如果用户同时粘贴了另一篇攻略文本，两份源材料一起解析，经**多源合并去重**后按提及次数排序展示。"

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

### Step 6 多 Agent 编排设计

- **编排框架**：`langgraph-supervisor`（官方扩展，自动生成 Handoff Tool）
- **编排方式**：Supervisor 模式（LLM 动态决策）替代硬编码链式调用
- **子 Agent**：全部 4 个（guide_parser、itinerary_gen、route_optimizer、fact_checker）
- **Supervisor Memory**：PostgresSaver（聊天本身就是多轮对话，需记忆）
- **入口**：新增 `POST /api/v1/chat` 统一入口，原有独立端点保留
- **服务层下沉**：编排决策上移至 Supervisor，服务层退为"执行者"（JSON 解析、ORM 映射、DB 读写）
