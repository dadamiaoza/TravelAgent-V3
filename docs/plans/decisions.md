# V3 架构决策日志

> 所有决策通过 `/grill-me` 和 `/grill-with-docs` 面试产生。每个决策对应一个 ADR 或一次讨论。

| # | 决策 | 结果 | 记录 |
|---|------|------|------|
| 1 | services/ vs agents/ 分工 | 方案 A：Agent 替代 Service 层，`services/` 只留纯工具函数 | 本文档 |
| 2 | DB 操作放在哪里 | 方案 C：Agent 内部直接操作 DB，外部 API（天气/地图）走 Tool | 本文档 |
| 3 | Agent 架构模式 | 方案 C：渐进式，Step 1-4 单 Agent → Step 5 Supervisor | 本文档 |
| 4 | LLM Provider | MiniMax M3（原 M2.7），走 OpenAI 兼容接口 `chat_model()` → `ChatOpenAI(base_url=...)` | 本文档；升级见 [2026-09-11 复盘](../../.ad/retrospect/2026-09-11_Suggest-500-and-M3.md) |
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
| 16 | 行程编辑服务层分层 | Controller -> Service -> Ports/Adapters；后续演进 Command/Event Sourcing | [ai-chat-collaboration-design.md](./ai-chat-collaboration-design.md) |
| 17 | LLM HTTP 客户端 | 统一 `app.core.llm.chat_model()`；禁用 brotli（`Accept-Encoding: gzip, deflate`），避开 openai 3 + httpx2 + brotli 1.0.9 解压崩溃 | [2026-09-11 复盘](../../.ad/retrospect/2026-09-11_Suggest-500-and-M3.md) |
| 18 | MiniMax M3 思考链格式 | 不全局开 `reasoning_split`，继续在 content 里用 `<think>` 清洗；避免 LangChain 多轮 tool 丢掉 `reasoning_details` | [2026-09-11 复盘](../../.ad/retrospect/2026-09-11_Suggest-500-and-M3.md) |
| 19 | 照片上传表单 | 不用 `File`+`Form(UUID)` 混校验；`request.form()` 自取文件，空 `item_id` 当未指定 | [2026-09-12 复盘](../../.ad/retrospect/2026-09-12_Photo-Upload-422-and-Huangxing-Geocode.md) |
| 21 | 计划 vs 实际到访 | 行程 Tab = 计划（`itinerary_items`）；回忆 Tab = 实际足迹；计划外须确认后写 `visit_stops`，不覆盖计划、不做第二份可编辑行程 | [拆分方案 v2.0](../../.ad/specs/行程详情页与地图页%20-%20页面拆分方案.md)、[执行计划](../../.ad/specs/计划与回忆-执行计划.md) |

## 相关文档

- `CONTEXT.md` — 领域语言词汇表（15+ 术语）
- `docs/adr/0001-agent-api-integration.md` — Agent-API 集成决策
- `CLAUDE.md` — Agent 项目配置入口
- `docs/agents/` — Issue 追踪器、标签、领域文档规则
