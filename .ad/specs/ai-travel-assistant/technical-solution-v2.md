# AI 旅行规划助手 V2：技术实现方案

> 基于 `requirements-v2.md`，定义 V2 增强迭代的技术架构、模块设计、开发步骤。

---

## 0. 设计决策摘要（来自 grill-with-docs）

| # | 决策 | 结果 |
|---|------|------|
| 1 | MCP 工具挂载 | 方案 B：子 Agent 各自挂载（guide_parser + fact_checker），非 Supervisor 包办 |
| 2 | MCP 连接策略 | 方案 B1：每 Agent 独立 MCP session |
| 3 | MCP 技术接入 | 方案 A：`langchain_mcp_adapters` + 薄封装层 |
| 4 | MCP 封装层 | 懒加载单例 + 创建/缓存/异常/测试替身四个入口 |
| 5 | 开发顺序 | S11 → S9 → S10 → S13 → S12 → S8 → S14 |
| 6 | 状态注入 | system_prompt（规则） + DB 读取（状态） |
| 7 | guide_parser 新字段 | `suggested_duration_h`、`best_time`、`cost_estimate`（谨慎） |
| 8 | 多源合并策略 | 归一化 + 别名/模糊 + 同城匹配；geocode/LLM 为增强层 |
| 9 | 上下文修剪范围 | 先只做 itinerary_gen，不碰 Supervisor |
| 10 | 修剪策略 | DB 结构化状态 + 最近 10 条窗口 + 旧消息 LLM 摘要；阈值 25 条或 token 估算超限 |

---

## 1. V2 架构变更

```
V1 架构：
  guide_parser ── geocode_poi
  itinerary_gen ── search_attractions, get_travel_time
  route_optimizer ── optimize_itinerary
  fact_checker ── get_weather, get_opening_hours
  Supervisor ── 路由 + PostgresSaver

V2 架构（变更标 ★）：
  guide_parser ── geocode_poi + ★Tavily MCP + ★Firecrawl MCP
  itinerary_gen ── search_attractions, get_travel_time + ★结构化状态注入 + ★上下文修剪
  route_optimizer ── optimize_itinerary（不变）
  fact_checker ── get_weather, get_opening_hours + ★Tavily MCP + ★Firecrawl MCP
  Supervisor ── 路由 + PostgresSaver（不变）
```

---

## 2. 新增模块

### 2.1 MCP 封装层：`app/mcp/`

```
app/mcp/
  __init__.py
  client.py        # MCPClientWrapper — 懒加载单例，封装 langchain_mcp_adapters
  config.py        # Tavily/Firecrawl MCP server 配置
```

**`MCPClientWrapper` 接口**：

```python
class MCPClientWrapper:
    """薄封装层：创建/缓存/异常/测试替身四个入口"""

    def __init__(self, server_name: str, server_config: dict):
        ...

    def get_tools(self) -> list:
        """懒加载：首次调用时建立 MCP session，缓存 Tool 列表"""
        ...

    def invalidate(self):
        """连接异常时清除缓存，下次调用重建"""
        ...

    def set_test_double(self, tools: list):
        """测试替身入口"""
        ...
```

设计要点：
- `langchain_mcp_adapters` 把 MCP tool schema → LangChain Tool，Agent 直接使用
- 懒加载：模块导入时不建连接，首次 `get_tools()` 时才建
- 异常处理：MCP 连接失败 → 返回空 Tool 列表（优雅降级，Agent 仍可用已有 Tool）
- 测试替身：`set_test_double()` 允许注入 mock Tool，不依赖真实 MCP Server

### 2.2 上下文修剪中间件：`app/agents/middleware.py`

```python
def trim_context(messages: list, max_recent: int = 10, max_total: int = 25) -> list:
    """超过 max_total 条消息时：旧消息 LLM 摘要 + 保留最近 max_recent 条"""
    ...

class StructuredState:
    """从 DB 读取的结构化任务状态"""
    planned_pois: list[str]
    remaining_days: int
    budget_range: tuple
    last_action: str
```

---

## 3. 修改模块

### 3.1 `guide_parser.py`（S9 + S11）

**S9 变更**：system_prompt 增加字段提取要求

```
输出格式新增字段：
- suggested_duration_h: float | null  # "建议游玩3-4小时" → 3.5
- best_time: str | null               # "一定要早上去" → "morning"
- cost_estimate: str | null           # 仅原文明确时输出，格式："门票60元"
```

**S11 变更**：注册 MCP 工具

```python
from app.mcp.client import MCPClientWrapper

_tavily = MCPClientWrapper("tavily", {...})
_firecrawl = MCPClientWrapper("firecrawl", {...})

def create_guide_parser():
    return create_agent(
        model=...,
        tools=[geocode_poi, *_tavily.get_tools(), *_firecrawl.get_tools()],
        system_prompt=...  # 增加搜索/抓取使用指引
    )
```

### 3.2 `fact_checker.py`（S12）

同 guide_parser，注册 Tavily + Firecrawl MCP 工具。system_prompt 增加"可用搜索核实官网信息"指引。

### 3.3 `itinerary_gen.py`（S8）

两项变更：

**变更 1：system_prompt 增加结构化状态注入**

```python
def _build_system_prompt(trip: Trip, db: Session) -> str:
    planned = _get_planned_pois(db, trip.id)
    state = (
        f"\n\n[当前任务状态]\n"
        f"已规划景点：{', '.join(planned) or '暂无'}（请勿重复选择）\n"
        f"总共{trip.total_days}天，已完成{len(planned_days)}天，"
        f"剩余{trip.total_days - len(planned_days)}天\n"
    )
    return BASE_SYSTEM_PROMPT + state
```

**变更 2：Agent 调用前检查消息数量 → 触发修剪**

```python
def generate_itinerary(db, trip):
    agent = create_itinerary_gen()
    messages = _load_or_init_messages(trip)
    
    # 修剪中间件
    if len(messages) > TRIMMING_THRESHOLD:
        messages = trim_context(messages)
    
    result = agent.invoke({"messages": messages}, ...)
```

### 3.4 `services/itinerary.py`（S8）

`generate_itinerary()` 调用前：从 DB 读取结构化状态 → 拼入 prompt。调用后：检查消息数量 → 必要时触发修剪。

### 3.5 多源合并：`app/services/merge.py`（S10）

```python
def merge_candidates(sources: list[list[dict]]) -> list[dict]:
    """
    输入：多个攻略各自解析的候选列表
    处理：归一化名称 → 别名匹配 → 同城模糊匹配
    输出：合并去重后的候选列表（含 mention_count, source_names）
    """
```

---

## 4. 数据库变更

### S13：`itinerary_items` 表新增字段

```sql
ALTER TABLE itinerary_items ADD COLUMN source_id INTEGER REFERENCES source_documents(id);
ALTER TABLE itinerary_items ADD COLUMN source_name VARCHAR;  -- 去范式化，便于展示
```

### S8：无需新表

结构化状态从现有 `itinerary_items` + `itinerary_days` + `trips` 表读取，不新增持久化结构。

### 迁移文件

| 迁移 | 内容 |
|------|------|
| `0007` | itinerary_items 加 source_id / source_name |
| （S14 远期）| user_profile 表 |

---

## 5. 开发步骤（V2）

```
里程碑 A（S11）
  │
  ├── S11: Tavily + Firecrawl MCP 接入 guide_parser
  │        ├── app/mcp/ 封装层
  │        ├── guide_parser 注册 MCP 工具 + system_prompt 更新
  │        └── 验证：搜索 → 链接确认 → 抓取 → 解析
  │
  ▼
里程碑 B（S9 → S10 → S13）
  │
  ├── S9: guide_parser 输出增强
  │        ├── system_prompt 增加 duration/best_time/cost 字段
  │        └── 验证：粘贴攻略 → 解析结果含新字段
  │
  ├── S10: 多源合并去重
  │        ├── app/services/merge.py
  │        └── 验证：3 篇攻略 → 合并去重结果
  │
  ├── S13: 源归属追踪
  │        ├── DB migration 0007
  │        ├── ItineraryItem 模型 + schema 更新
  │        └── 验证：行程节点展示来源攻略
  │
  ▼
里程碑 C（S12）
  │
  ├── S12: Tavily + Firecrawl MCP 接入 fact_checker
  │        ├── fact_checker 注册 MCP 工具 + system_prompt 更新
  │        └── 验证：fact_checker 能搜索核实官网信息
  │
  ▼
里程碑 D（S8）
  │
  ├── S8: 记忆系统升级
  │        ├── 结构化状态注入（services/itinerary.py）
  │        ├── 上下文修剪中间件（app/agents/middleware.py）
  │        └── 验证：多轮规划不重复选景点 + 长对话不降质
  │
  ▼
里程碑 E（S14，远期）
  │
  └── S14: 用户画像
```

| 步骤 | 内容 | 依赖 | 改动面 |
|------|------|------|--------|
| **S11** | Tavily + Firecrawl MCP 接入 guide_parser | 无 | 新增 `app/mcp/`，改 `guide_parser.py` |
| **S9** | guide_parser 输出增强 | 无（可与 S11 独立） | `guide_parser.py` prompt |
| **S10** | 多源合并去重 | S9 | 新增 `merge.py` |
| **S13** | 源归属追踪 | S9 | DB migration + 模型/schema |
| **S12** | MCP 接入 fact_checker | S11（复用 mcp 封装层） | `fact_checker.py` |
| **S8** | 记忆系统升级 | 无（可独立） | `itinerary_gen.py` + `middleware.py` + `services/itinerary.py` |
| **S14** | 用户画像（远期） | S8 | 新表 + user 模块 |

---

## 6. 验证策略

| 步骤 | 验证方式 | 关键验证点 |
|------|---------|-----------|
| S11 | 集成测试 + 手动 | MCP 连接、搜索返回链接、抓取返回 Markdown、guide_parser 能处理抓取结果 |
| S9 | 单元测试 | 模拟 LLM 输出含新字段 → 解析正确 |
| S10 | 单元测试 | 同名变体正确合并、提及次数准确 |
| S13 | 集成测试 | source_id 正确写入、API 返回 source 字段 |
| S12 | 集成测试 + 手动 | fact_checker 能搜索核实、失败降级不崩溃 |
| S8 | 集成测试 | 多轮规划不重复 POI、修剪后消息数 ≤ 阈值、V1 回归 |

### 回归要求

每个步骤完成后，必须跑 V1 的 20 个 `test_route_optimizer.py` 测试 + 冒烟脚本，确保已有功能不受影响。

---

## 7. 关键风险与缓解

| 风险 | 缓解 |
|------|------|
| `langchain_mcp_adapters` 对 Tavily/Firecrawl schema 转换不完整 | S11 早期先验证 schema 转换，发现缺失立即评估 B 方案 |
| MCP 连接不稳定 | 薄封装层包含异常处理 + 连接重建；MCP 失败 → 返回空 Tool 列表，Agent 降级 |
| guide_parser 新字段提取不稳定 | 字段均为 nullable，不强制输出；先跑一批样例看提取率 |
| 上下文修剪引入额外 LLM 调用 | 摘要 LLM 调用只在触发修剪时发生（>25 条消息），频率低 |
