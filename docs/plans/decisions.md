# V3 架构决策日志

> 所有决策通过 `/grill-me` 和 `/grill-with-docs` 面试产生。每个决策对应一个 ADR 或一次讨论。

| # | 决策 | 结果 | 记录 |
|---|------|------|------|
| 1 | services/ vs agents/ 分工 | 方案 A：Agent 替代 Service 层，`services/` 只留纯工具函数 | 本文档 |
| 2 | DB 操作放在哪里 | 方案 C：Agent 内部直接操作 DB，外部 API（天气/地图）走 Tool | 本文档 |
| 3 | Agent 架构模式 | 方案 C：渐进式，Step 1-4 单 Agent → Step 5 Supervisor | 本文档 |
| 4 | LLM Provider | MiniMax M2.7，走 OpenAI 兼容接口 `ChatOpenAI(base_url=...)` | 本文档 |
| 5 | 领域术语拆分 | 源材料（Source）→ 候选列表（Candidate List）→ 行程（Itinerary） | [CONTEXT.md](../../CONTEXT.md) |
| 6 | Agent-API 集成模式 | 同步 + 异步 + SSE 混合 | [ADR-0001](../adr/0001-agent-api-integration.md) |
| 7 | 数据库迁移策略 | 按 Agent 阶段增量建表，不一把建完 | 本文档 |
| 8 | Agent 记忆策略 | 方案 C：手动注入上下文（S0-S3），后续切 PostgresSaver | 本文档 |
| 9 | 开发学习模式 | 模式 B：方案理解 → AI 写码 → 手动验证 → 复盘提问 | 本文档 |
| 10 | 下一步方向 | 方向 C：先建 DB 脚手架（trips 表 + Alembic） | 本文档 |
| 11 | 路径排序：贪心 vs LLM | 方案 A：贪心最近邻（代码），LLM 只做起点选择 | [knowledge-map.md](../../.ad/retrospect/knowledge-map.md#贪心最近邻greedy-nearest-neighbor) |
| 12 | 交通方式选择 | 方案 C：按 Haversine 距离自动选（<1.5km walking，≥1.5km transit） | [knowledge-map.md](../../.ad/retrospect/knowledge-map.md#按距离自动选择交通方式) |
| 13 | API 矩阵构建策略 | 方案 B：完整 N×(N-1) 有向矩阵 + all-or-nothing 降级 | [knowledge-map.md](../../.ad/retrospect/knowledge-map.md#有向旅行时间矩阵) |
| 14 | 记忆与状态分离 | 双通道架构：消息修剪 + 结构化任务摘要注入 system_prompt | [knowledge-map.md](../../.ad/retrospect/knowledge-map.md#12-mvp-后规划记忆架构与外部集成) |
| 15 | 外部搜索/抓取集成 | MCP 用于开放性搜索（LLM 自主决策），直接 API 用于确定性调用 | [knowledge-map.md](../../.ad/retrospect/knowledge-map.md#外部集成mcp-搜索--抓取) |

## 相关文档

- `CONTEXT.md` — 领域语言词汇表（15+ 术语）
- `docs/adr/0001-agent-api-integration.md` — Agent-API 集成决策
- `CLAUDE.md` — Agent 项目配置入口
- `docs/agents/` — Issue 追踪器、标签、领域文档规则
