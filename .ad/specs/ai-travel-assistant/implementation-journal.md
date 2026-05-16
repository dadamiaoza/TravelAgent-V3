# AI 旅行规划助手：需求分析、方案设计与开发实录（新手版）

> 文档目的：把“为什么这么做、做了什么、怎么验证、下一步做什么”写清楚，保证你第一次做也能跟上。

## 1. 你当前可用的 Skills（会话内）

### 1.1 全部可用 Skills（按名称）

`caveman`、`code-documentation`、`context7-mcp`、`create-pr`、`diagnose`、`find-skills`、`git-guardrails-claude-code`、`grill-me`、`grill-with-docs`、`handoff`、`improve-codebase-architecture`、`migrate-to-shoehorn`、`planning-with-files`、`prototype`、`scaffold-exercises`、`setup-pre-commit`、`tdd`、`to-issues`、`to-prd`、`triage`、`ui-ux-pro-max`、`writing-skills`、`bootstrap-project`、`agent-customization`、`get-search-view-results`、`install-vscode-extension`、`troubleshoot`

### 1.2 本次已实际使用的 Skills

1. `planning-with-files`：用于复杂任务的阶段化推进与过程管理。  
2. `code-documentation`：用于把设计与开发结果沉淀成新手友好的文档。
3. `bootstrap-project`：用于校验当前文档结构和阶段产物是否完整。
4. `mattpocock`：已按你的要求尝试调用，但当前环境不存在同名 skill（已记录）。

---

## 2. 需求分析结论（基于 PRD/调研/澄清）

### 2.1 产品要解决的核心问题

用户在小红书等平台“抄作业”时，信息分散、整理成本高、AI 结果不稳定。  
MVP 的核心是：**快速得到可执行、可编辑、尽量时效准确的行程方案**。

### 2.2 MVP 目标用户

先聚焦年轻自由行用户（学生/朋友/情侣），不做老年人和多人协作复杂场景。

### 2.3 MVP 做与不做

**本期做：**

1. 手动输入旅行约束（时间、地点、时段、人数）。
2. 生成“天-时段-地点”的结构化行程。
3. 在页面展示结构化结果。

**本期不做：**

1. 多人协作。
2. 订票下单。
3. 社区/UGC。
4. 复杂多 Agent 架构。

---

## 3. 方案设计（为什么这么设计）

### 3.1 技术选型（MVP 友好）

| 层 | 选择 | 为什么 |
|---|---|---|
| 前端 | React (Vite) + TypeScript | 纯 SPA，无 SSR 心智负担；Vite 构建快；与独立 FastAPI 后端天然分离 |
| 后端 | FastAPI + Pydantic | Python 生态，接口定义清晰，开发快 |
| 数据库 | PostgreSQL（Docker） | 关系模型清晰，迁移工具成熟 |
| 迁移 | Alembic | 结构变更可追踪，可回滚 |
| 测试 | pytest + 前端 lint/build | 先保证基础可运行与可构建 |

### 3.2 架构策略

先做“单体 + 清晰分层”，不提前拆微服务。  
原因：你是新手，MVP 阶段最大风险不是性能，而是“闭环跑不通”。

### 3.3 分层设计（当前代码）

1. `api`：只负责 HTTP 输入输出。  
2. `services`：封装业务逻辑（例如行程生成）。  
3. `models/schemas`：数据库模型与接口数据模型分离。  
4. `alembic`：数据库结构版本管理。

---

## 4. 开发阶段拆解（含依赖与并行）

| 阶段 | 目标 | 依赖 | 是否可独立验证 | 当前状态 |
|---|---|---|---|---|
| S0 | 项目基线（前后端脚手架、健康检查、迁移、测试框架） | 无 | 可以 | ✅ 已完成 |
| S1 | 最小闭环（手动输入 -> 生成行程 -> 展示） | S0 | 可以 | ✅ 已完成 |
| S2 | 节点可编辑 + 保存 + 版本快照 | S1 | 可以 | ✅ 已完成 |
| S3 | 攻略导入解析（文本/链接优先） | S2 | 可以 | ✅ 已完成 |
| S4 | 路线优化 + 地图导览 | S3 | 可以 | ✅ 已完成 |
| S5 | 时效与风险提示 | S4 | 可以 | ✅ 已完成 |
| S6 | 稳定化、回归、演示发布 | S5 | 可以 | ✅ 已完成 |

---

## 5. 当前已经完成的功能（代码已落地）

## 5.1 S0 已完成

1. 前端 React (Vite) 项目初始化。  
2. 后端 FastAPI 项目初始化。  
3. 健康检查接口：`GET /api/v1/health`。  
4. Docker Postgres 本地开发环境。  
5. Alembic 迁移基线（`0001_baseline`）。

## 5.2 S1 已完成

1. 新增 Trip 相关数据表迁移（`0002_trip_itinerary_tables`）。  
2. 新增接口：
   - `POST /api/v1/trips`（创建行程）
   - `POST /api/v1/trips/{trip_id}/generate`（生成行程）
   - `GET /api/v1/trips/{trip_id}`（查询行程）
3. 新增最小行程生成服务（规则模板版）。  
4. 前端首页改为可提交表单并展示结构化 Day 列表。  
5. 提交记录：`a0ab930`（S0 + S1）。

## 5.3 S2 已完成

1. 新增快照表迁移（`0003_trip_snapshots_and_item_edit`）。  
2. 新增接口：
   - `PATCH /api/v1/trips/itinerary-items/{item_id}`（编辑节点并保存）
   - `GET /api/v1/trips/{trip_id}/snapshots`（查看版本快照）
3. 行程生成后自动创建快照（`reason=generated`）。  
4. 行程节点编辑后自动创建新快照（`reason=item_updated:<id>`）。  
5. 前端支持“编辑节点 -> 保存 -> 页面刷新显示最新版本与快照列表”。

## 5.4 S3 已完成

1. 新增攻略来源与解析实体数据表迁移（`0004_source_import_and_entities`）。  
2. 新增接口：
   - `POST /api/v1/trips/{trip_id}/sources`（导入文本/链接攻略）
   - `POST /api/v1/trips/{trip_id}/parse`（解析攻略为候选地点）
   - `POST /api/v1/trips/{trip_id}/apply-entities`（勾选结果写入行程）
3. 新增解析服务：文本按行/分隔符提取地点，链接按域名/路径分词提取候选。  
4. 前端新增“攻略导入解析（S3）”区域，支持导入、勾选、写入行程。  
5. 写入行程后自动创建新快照，保证可追踪。

## 5.5 S4 已完成

1. 新增行程节点坐标字段迁移（`0005_route_fields_and_optimization`）。  
2. 新增接口：`POST /api/v1/trips/{trip_id}/reoptimize`（路线重排与距离对比）。  
3. 新增路线优化服务：按最近邻策略重排行程节点，输出优化前后距离。  
4. 路线优化后自动生成快照（`reason=route_optimized`）。  
5. 前端新增“一键路线优化”按钮与优化指标展示（优化前/后公里数）。  
6. 前端新增日维度简易地图导览（SVG 路线示意图，含路径与节点序号）。

## 5.6 S5 已完成

1. 新增事实校验数据表迁移（`0006_fact_checks`）。  
2. 新增接口：`POST /api/v1/trips/{trip_id}/fact-check`（刷新时效信息）。  
3. 新增时效服务：按行程节点生成校验记录（来源、校验时间、过期时间、风险等级）。  
4. 前端新增“刷新时效信息”操作与风险标签展示（low/medium/high）。  
5. 行程详情可直接查看每条时效记录，包含来源与时间字段。

## 5.7 S6 已完成

1. 新增项目级新手指南：`scr/README.md`（环境安装、启动、测试、验收、报错排查）。  
2. 新增端到端冒烟脚本：`scr/scripts/smoke-test.ps1`。  
3. 冒烟验证覆盖：健康检查、创建/生成、节点编辑、攻略解析写入、路线优化、时效刷新。  
4. 完成一次“服务启动 + 数据迁移 + 冒烟脚本”全链路验证。  
5. 文档已与代码同步到 S6 状态。

---

## 6. 测试结果（最新一次）

> 测试时间：2026-05-13

### 6.1 后端

执行命令：

```powershell
cd "f:\My_Code\Travel Agent-V2\scr\backend"
python -m pytest -q
```

结果：`3 passed`（包含迁移验证、健康检查、S5 时效刷新流程）。

### 6.2 前端

执行命令：

```powershell
cd "f:\My_Code\Travel Agent-V2\scr\frontend"
npm run lint
npm run build
```

结果：均通过（lint 通过，build 成功产出静态页面）。

### 6.3 端到端冒烟

执行命令：

```powershell
cd "f:\My_Code\Travel Agent-V2\scr"
pwsh -ExecutionPolicy Bypass -File .\scripts\smoke-test.ps1
```

结果：通过（输出 `Smoke test passed.`）。

---

## 7. 未完成项与后续计划

### 7.1 未完成（按优先级）

1. S2：版本快照回滚（restore）能力。  
2. S3：图片攻略解析（当前仅文本/链接）。  
3. 生产级地图接入（当前为简化 SVG 导览，不含真实地图服务）。  
4. 生产级时效数据源接入（当前为 mock-live-provider）。

### 7.2 近期下一步（下一阶段）

后续进入“增强迭代阶段”：优先补齐版本回滚和图片攻略解析。

---

## 8. 为什么当前还没有“AI 智能生成”

当前 S1 使用的是“规则模板生成”，不是最终 AI 版本。  
这是故意的，原因是：

1. 先保证链路稳定（输入、存储、展示、测试）。  
2. 新手阶段先把工程骨架搭稳，再接入 LLM，排障更容易。  
3. 避免把“模型效果问题”和“工程问题”混在一起，导致定位困难。

---

## 9. 文档同步规则（强制执行）

后续每次代码变更，都要同步更新本文件，至少更新这 5 个位置：

1. **第 5 节**：当前已完成功能。  
2. **第 6 节**：最新测试命令与结果。  
3. **第 7 节**：未完成项和下一步。  
4. **第 10 节**：变更记录（新增一行）。  
5. 若有架构调整：同步更新 `technical-solution.md` 对应章节。

执行顺序（固定）：

1. 代码改动完成。  
2. 跑测试并确认结果。  
3. 更新本文档。  
4. 再提交代码。

---

## 10. 变更记录（保持与代码一致）

| 日期 | 阶段 | 变更摘要 | 测试结果 | 提交 |
|---|---|---|---|---|
| 2026-05-13 | S0 + S1 | 完成基线与最小闭环（创建/生成/查询行程 + 前端表单展示） | backend: 3 passed；frontend: lint/build passed | `a0ab930` |
| 2026-05-13 | S2 | 完成节点可编辑与自动版本快照（后端接口 + 前端编辑 UI） | backend: 3 passed；frontend: lint/build passed | `2f4f820` |
| 2026-05-13 | S3 | 完成文本/链接攻略导入解析与勾选写入行程（含后端接口与前端交互） | backend: 3 passed；frontend: lint/build passed | `d3a5555` |
| 2026-05-13 | S4 | 完成路线优化与地图导览（后端重排 + 前端可视化） | backend: 3 passed；frontend: lint/build passed | `490e5b4` |
| 2026-05-13 | S5 | 完成时效刷新与风险提示（后端 fact-check + 前端风险标签） | backend: 3 passed；frontend: lint/build passed | `f7c464c` |
| 2026-05-13 | S6 | 完成稳定化与交付（新手 README + 冒烟脚本 + 全链路验证） | backend: 3 passed；frontend: lint/build passed；smoke: passed | 待提交 |

---

## 11. 文件生命周期矩阵（逐文件）

> 目标：让你随时知道“这个文件什么时候创建、什么时候更新、什么时候冻结或归档”。

| 文件 | 当前阶段 | 生命周期状态 | 创建时机 | 必须更新时机 | 冻结/归档规则 |
|---|---|---|---|---|---|
| `requirements.md` | Discovery + PRD | Active | Phase 1 首次需求澄清时创建 | 用户故事、MVP 范围、Out of Scope 变化时 | 不删除；MVP 完成后转为历史基线（Frozen） |
| `research.md` | Research | Active | Phase 2 竞品调研时创建 | 竞品信息明显过期或市场发生重大变化时 | MVP 发布后可归档（Archive），保留引用 |
| `technical-solution.md` | Design | Active | Phase 4 技术方案确认时创建 | 架构、数据模型、接口契约、阶段顺序调整时 | 不删除；进入稳定期后仅增量修订 |
| `implementation-journal.md` | Implement/Verify | Active | 开始实施阶段时创建 | 每次代码变更后（功能、测试、遗留项、变更记录） | 全程保留；作为项目执行日志 |
| `design.md` | Design（标准位） | Planned | 若需要按 bootstrap 标准分离设计文档时创建 | 当 `technical-solution.md` 不再承载全部设计内容时同步维护 | 若继续使用 `technical-solution.md` 可不单独启用 |
| `tasks.md` | Breakdown（标准位） | Planned | 若进入严格任务拆解清单流时创建 | 每个任务开始/完成、依赖变化、验收标准变化时 | 全任务完成后可冻结并归档 |

### 11.1 生命周期状态定义

1. **Planned**：标准结构中的预留文件，尚未启用。  
2. **Active**：当前在维护，任何关键变更都必须同步。  
3. **Frozen**：不再日常编辑，仅在重大变更时解冻。  
4. **Archive**：完成历史使命，保留只读参考。

