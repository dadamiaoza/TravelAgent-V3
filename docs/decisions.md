# V3 架构决策日志

> 所有决策通过 `/grill-me` 和 `/grill-with-docs` 面试产生。每个决策对应一个 ADR 或一次讨论。

| # | 决策 | 结果 | 记录 |
|---|------|------|------|
| 1 | services/ vs agents/ 分工 | 方案 A：Agent 替代 Service 层，`services/` 只留纯工具函数 | 本文档 |
| 2 | DB 操作放在哪里 | 方案 C：Agent 内部直接操作 DB，外部 API（天气/地图）走 Tool | 本文档 |
| 3 | Agent 架构模式 | 方案 C：渐进式，Step 1-4 单 Agent → Step 5 Supervisor | 本文档 |
| 4 | LLM Provider | MiniMax M2.7，走 OpenAI 兼容接口 `ChatOpenAI(base_url=...)` | 本文档 |
| 5 | 领域术语拆分 | 源材料（Source）→ 候选列表（Candidate List）→ 行程（Itinerary） | [CONTEXT.md](../CONTEXT.md) |
| 6 | Agent-API 集成模式 | 同步 + 异步 + SSE 混合 | [ADR-0001](adr/0001-agent-api-integration.md) |
| 7 | 数据库迁移策略 | 按 Agent 阶段增量建表，不一把建完 | 本文档 |
| 8 | Agent 记忆策略 | 方案 C：手动注入上下文（S0-S3），后续切 PostgresSaver | 本文档 |
| 9 | 开发学习模式 | 模式 B：方案理解 → AI 写码 → 手动验证 → 复盘提问 | 本文档 |
| 10 | 下一步方向 | 方向 C：先建 DB 脚手架（trips 表 + Alembic） | 本文档 |

## 相关文档

- `CONTEXT.md` — 领域语言词汇表（9 个术语）
- `docs/adr/0001-agent-api-integration.md` — Agent-API 集成决策
- `CLAUDE.md` — Agent 项目配置入口
- `docs/agents/` — Issue 追踪器、标签、领域文档规则
