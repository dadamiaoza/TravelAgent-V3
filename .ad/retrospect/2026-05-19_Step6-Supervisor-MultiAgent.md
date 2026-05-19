# Step 6：Supervisor 多 Agent 编排

## 概述

**日期**：2026-05-19
**学习目标**：掌握 Supervisor 模式——用一个"主管 Agent"动态调度多个"专家 Agent"
**新增包**：`langgraph-supervisor` v0.0.31

---

## 需求分析

### 问题：Step 5 的局限

Step 5 结束时，系统有 4 个 Agent（guide_parser、itinerary_gen、route_optimizer、fact_checker），但每个 Agent 绑定一个 API 端点。用户必须知道"什么需求该调哪个端点"——这不符合 AI 助手的体验。

### 目标

用 **Supervisor 模式** 替代**硬编码端点路由**：

| | Step 5（端点路由） | Step 6（Supervisor） |
|---|---|---|
| 谁决定调哪个 Agent | 开发者写死在代码里 | Supervisor 的 LLM 自己判断 |
| 用户交互方式 | 调不同的 `/api/v1/*` 端点 | 一个 `POST /api/v1/chat`，自然语言 |
| Agent 之间 | 互不知晓 | Supervisor 知道所有子 Agent 的能力 |
| 调用顺序 | 固定（先 itinerary_gen 后 route_optimizer） | 动态，Supervisor 按需决定 |

---

## 核心概念：Supervisor 是什么

### 一句话理解

> **Supervisor 就是一个 Agent，它的 Tool 是其他 Agent。**

### 和已有知识的关系

回顾 Step 3，fact_checker Agent 有两个 Tool：

```
fact_checker Agent
  ├── get_weather Tool        ← LLM 判断用户问天气时调用
  └── get_opening_hours Tool  ← LLM 判断用户问开放时间时调用
```

Supervisor 的原理完全一样，只是把 Tool 换成了子 Agent：

```
Supervisor Agent
  ├── guide_parser (handoff tool)    ← LLM 判断"要解析攻略"时 handoff
  ├── itinerary_gen (handoff tool)   ← LLM 判断"要规划行程"时 handoff
  ├── route_optimizer (handoff tool) ← LLM 判断"要优化路线"时 handoff
  └── fact_checker (handoff tool)    ← LLM 判断"要检查天气"时 handoff
```

### 关键技术：Handoff Tool

`langgraph-supervisor` 的 `create_supervisor` 函数为每个子 Agent 自动生成一个 **handoff tool**（转移控制权的工具）。当 Supervisor 的 LLM 决定"这件事应该交给 guide_parser"时，它调用 `transfer_to_guide_parser` tool，LangGraph 就会把消息传递给 guide_parser 执行。

---

## 方案设计

### 设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 编排框架 | `langgraph-supervisor` | LangChain 官方扩展，自动生成 handoff tools，无需手动写路由 |
| 子 Agent 数量 | 全部 4 个 | 展示 Supervisor 管理多种专家的能力 |
| Memory | Supervisor 加 PostgresSaver | 聊天本身就是多轮对话，需要记忆（"先规划行程"→"再查天气"） |
| 端点设计 | 新增 `POST /api/v1/chat` | 原有端点保留，chat 是统一入口 |
| route_optimizer 的定位 | 独立子 Agent | 让 Supervisor 可以按需调用（不一定总跟在 itinerary_gen 后面） |

### architecture 对比

```
Step 5 架构（硬编码路由）：            Step 6 架构（Supervisor）：
                                       POST /api/v1/chat
POST /api/v1/trips                          │
  └── itinerary_gen ──→ route_optimizer     └── Supervisor (PostgresSaver)
                                               ├── guide_parser
POST /api/v1/sources/parse                     ├── itinerary_gen (PostgresSaver)
  └── guide_parser                             ├── route_optimizer
                                               └── fact_checker
POST /api/v1/facts/check
  └── fact_checker
```

### 服务层的角色变化

Step 6 之后，服务层**不会消失**，只是职责分层：

| 层 | 职责 | 由谁做 |
|----|------|--------|
| 编排决策 | "先调谁、后调谁" | Supervisor（AI） |
| 业务逻辑 | JSON → ORM、时间计算、DB 读写 | 服务层（代码） |

编排决策上移到 AI，服务层退后为"纯粹的执行者"。

---

## 开发步骤

### 第 1 步：安装依赖

```powershell
.venv/Scripts/pip install langgraph-supervisor
```

### 第 2 步：创建 Supervisor Agent

文件：`app/agents/supervisor.py`

```python
from langgraph_supervisor import create_supervisor

def create_supervisor_agent():
    # 1. 创建子 Agent，每个设置唯一的 name
    guide_parser = create_guide_parser()
    guide_parser.name = "guide_parser"  # Supervisor 按名字识别

    # 2. 用 create_supervisor 生成编排 workflow
    workflow = create_supervisor(
        agents=[guide_parser, itinerary_gen, route_optimizer, fact_checker],
        model=model,
        prompt="你是旅行规划团队的主管..."  # 中文 prompt 描述每个 Agent 的能力
    )

    # 3. 编译时加上 Checkpointer（Supervisor 也需要对话记忆）
    return workflow.compile(checkpointer=PostgresSaver(conn))
```

**要点**：
- `create_supervisor` 自动为每个子 Agent 生成 handoff tool
- 子 Agent 必须有唯一的 `.name`（否则 Supervisor 无法区分）
- Supervisor 的 prompt 是关键——它告诉 LLM 什么时候该调谁

### 第 3 步：创建统一聊天端点

文件：`app/api/v1/chat.py`

```python
@router.post("", response_model=ChatOut)
def chat(body: ChatRequest):
    supervisor = create_supervisor_agent()
    thread_id = body.thread_id or f"chat-{uuid.uuid4().hex[:8]}"
    result = supervisor.invoke(
        {"messages": [{"role": "user", "content": body.message}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return ChatOut(reply=_extract_reply(result["messages"]), thread_id=thread_id)
```

**要点**：
- 自动生成 `thread_id`（`chat-` 前缀，区别于 itinerary 的 `trip-` 前缀）
- 用户可传 `thread_id` 来延续之前的对话

### 第 4 步：新增 Schema

在 `schemas/trip.py` 末尾新增：

```python
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: str | None = None  # 可选，传了就延续对话

class ChatOut(BaseModel):
    reply: str
    thread_id: str
```

### 第 5 步：注册路由

`main.py` 中新增一行：
```python
app.include_router(chat_router, prefix="/api/v1")
```

---

## 测试结果

### 新增测试（3 个）

| 测试 | 验证内容 |
|------|---------|
| `test_supervisor_compile` | Supervisor 能成功编译成 LangGraph workflow |
| `test_supervisor_routes_to_guide_parser` | "帮我解析攻略" → 自动调用 guide_parser |
| `test_supervisor_routes_to_fact_checker` | "查天气和开放时间" → 自动调用 fact_checker |

### 全量测试

```
22 passed in 995.16s (0:16:35)
```

覆盖范围：
- 3 个 fact_checker Agent 测试
- 3 个 guide_parser Agent 测试
- 1 个 health 端点测试
- 4 个 itinerary_gen Agent 测试（含 Memory/Checkpointer）
- 3 个 route_optimizer 测试（Tool + Agent）
- 3 个 Supervisor 测试（新增）
- 5 个 trip_flow 集成测试（DB + API）

---

## 当前已完成功能

### API 端点一览

| 端点 | 方法 | Agent | 状态 |
|------|------|-------|------|
| `/api/v1/health` | GET | - | ✅ |
| `/api/v1/trips` | POST | itinerary_gen → route_optimizer | ✅ |
| `/api/v1/trips` | GET | - | ✅ |
| `/api/v1/trips/{id}` | GET | - | ✅ |
| `/api/v1/sources/parse` | POST | guide_parser | ✅ |
| `/api/v1/facts/check` | POST | fact_checker | ✅ |
| `/api/v1/chat` | POST | Supervisor → 4 个子 Agent | ✅ |

###Agent 一览

| Agent | 工具 | Memory | 定位 |
|-------|------|--------|------|
| guide_parser | geocode_poi | 无 | 攻略解析 |
| itinerary_gen | search_attractions, get_travel_time | PostgresSaver | 行程生成 |
| route_optimizer | optimize_itinerary | 无 | 坐标回填 |
| fact_checker | get_weather, get_opening_hours | 无 | 时效校验 |
| **Supervisor** | 以上 4 个 Agent（作为 handoff tools） | PostgresSaver | **多 Agent 编排** |

---

## 未完成和后续计划

### Step 7：工具升级 — Mock → 真实 API

当前所有 Tool 都是 mock 数据（硬编码的景点列表、假天气、假开放时间）。Step 7 将统一替换为真实 API：

| 当前（Mock） | 将来（真实 API） |
|--------------|-----------------|
| `geocode_poi`（20 个硬编码 POI） | 高德地理编码 API |
| `calculate_distance`（Euclidean 直线距离） | 高德路径规划 API |
| `search_attractions`（3 个城市硬编码） | 高德 POI 搜索 API |
| `get_weather`（随机天气） | 和风天气 / OpenWeather API |
| `get_opening_hours`（硬编码时间） | 高德景点详情 / 网络抓取 |

**为什么延后**：先把 Agent 编排模式学完（Step 1-6），再统一替换工具实现。高德 MCP 的集成不影响 Agent 的架构设计——Tool 接口不变，只是内部实现从 mock 换成 API 调用。

### Step 8：版本快照（Snapshot）

DB 中新增 `snapshots` 表，每次修改行程自动保存完整副本，支持对比和回滚。

### 后续可能

- 前端 React Vite 应用（Step 9+）
- 用户认证（Step 10+）
- 真实 MCP 整合（高德、天气）

---

## 学习总结

### 新概念

| 概念 | 解释 |
|------|------|
| **Supervisor** | 管理多个子 Agent 的"主管 Agent"，通过 Tool Calling 动态调度 |
| **Handoff Tool** | `create_supervisor` 自动生成的 Tool，调用它会把控制权转移给子 Agent |
| **链式调用 vs Supervisor** | 链式调用是服务层硬编码顺序（Step 5），Supervisor 是 LLM 动态决策（Step 6） |
| **服务层下沉** | Agent 编排能力增强 → 服务层从"指挥官"变成"执行者" |

### 核心理念

Supervisor 不是一个全新概念——它是你已经学过的 Tool Calling 机制的延伸。区别只在于：

- 普通 Agent：Tool 是 Python 函数
- Supervisor Agent：Tool 是其他 Agent

理解了这个，你就理解了多 Agent 编排的本质。
