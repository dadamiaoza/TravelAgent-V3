# AI 旅行规划助手 TravelAgent-V3

一个基于 **LangGraph 多 Agent 编排** 的 AI 旅行规划助手。

用户输入目的地、日期、人数后，系统自动生成 Day-by-Day 行程，支持高德地图真实路线展示、节点编辑、同天排序和时效风险校验。

> 这是一个面向求职面试展示的项目：代码结构、工程决策、部署链路、测试与复盘文档均完整保留。

---

## ✨ 功能亮点

- **多 Agent 编排**
  - Supervisor 统一调度
  - guide_parser：攻略解析
  - itinerary_gen：行程生成
  - route_optimizer：路线优化
  - fact_checker：时效校验
- **真实地图路线**
  - 高德 JS API 地图展示
  - 后端返回真实道路坐标
  - 交通方式图标与颜色区分
  - 无真实路线时自动回退直线
- **行程编辑**
  - 编辑节点名称 / 时间 / 备注
  - 同一天内上移 / 下移排序
  - 不强制重新请求高德路线
- **Fact Check 时效校验**
  - JSON 规则引擎：周一闭馆、节假日调整
  - 天气与开放时间工具
  - 统一风险汇总结构
  - `fact_checks` 持久化
- **生产部署**
  - Railway + 托管 PostgreSQL
  - Docker 多阶段构建
  - Nginx 同源代理 `/api`
  - 启动前自动执行 Alembic migration

---

## 🧱 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 + FastAPI |
| Agent 编排 | LangGraph + langgraph-supervisor |
| LLM | MiniMax M2.7（OpenAI 兼容接口） |
| 数据库 | PostgreSQL 16 |
| ORM / 迁移 | SQLAlchemy + Alembic |
| 前端 | React 18 + Vite + TypeScript |
| 状态/请求 | TanStack Query + React Router |
| 地图 | 高德 JS API v2 |
| 部署 | Docker + Nginx + Railway |

---

## 🏗️ 项目结构

```text
TravelAgent-V3/
├── docs/
│   ├── README.md                     # 文档索引
│   ├── plans/                        # 方案、设计与规划
│   │   ├── next-phase-design.md
│   │   ├── ai-chat-collaboration-design.md
│   │   └── decisions.md
│   ├── retrospectives/               # 开发复盘
│   │   ├── development-notes.md
│   │   ├── factcheck-retrospective.md
│   │   └── scenic-routes-retrospective.md
│   ├── adr/                          # 架构决策
│   └── agents/                       # Agent 协作约定
├── src/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── agents/               # 多 Agent 与工具
│   │   │   ├── api/v1/               # REST 端点
│   │   │   ├── core/                 # 配置
│   │   │   ├── db/                   # 数据库会话
│   │   │   ├── mcp/                  # MCP 客户端封装
│   │   │   ├── models/               # SQLAlchemy 模型
│   │   │   ├── schemas/              # Pydantic 模型
│   │   │   └── services/             # 业务逻辑
│   │   ├── alembic/                  # 数据库迁移
│   │   ├── tests/                    # pytest
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   ├── frontend/
│   │   ├── src/
│   │   │   ├── components/           # UI 组件
│   │   │   ├── hooks/                # React Query hooks
│   │   │   ├── lib/                  # API/类型/工具
│   │   │   └── pages/                # 页面
│   │   ├── Dockerfile
│   │   └── nginx.conf.template
│   └── docker-compose.yml
└── README.md
```

---

## 📡 API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/health` | 健康检查 |
| POST | `/api/v1/trips` | 创建并生成行程 |
| GET | `/api/v1/trips` | 行程列表 |
| GET | `/api/v1/trips/{trip_id}` | 行程详情 |
| PATCH | `/api/v1/trips/{trip_id}/items/{item_id}` | 编辑节点 |
| POST | `/api/v1/trips/{trip_id}/days/{day_id}/reorder` | 同天排序 |
| POST | `/api/v1/sources/parse` | 攻略解析 |
| POST | `/api/v1/sources/merge` | 多源合并去重 |
| POST | `/api/v1/facts/check` | 时效风险校验 |
| POST | `/api/v1/chat` | Supervisor 统一聊天入口 |

---

## 🚀 本地开发

### 1. 启动 PostgreSQL

```bash
cd src
docker compose up -d
```

### 2. 启动后端

```bash
cd src/backend
cp .env.example .env
# 填入 LLM_API_KEY 等环境变量

python -m venv .venv
.venv\Scripts\python -m pip install -e .

.venv\Scripts\alembic upgrade head
.venv\Scripts\python run_server.py
```

### 3. 启动前端

```bash
cd src/frontend
npm install
npm run dev
```

访问：

```text
http://localhost:5173
```

---

## 🔧 环境变量

后端变量：

```text
DATABASE_URL
LLM_PROVIDER
LLM_MODEL
LLM_API_KEY
LLM_BASE_URL
AMAP_API_KEY
QWEATHER_PROJECT_ID
QWEATHER_KEY_ID
QWEATHER_PRIVATE_KEY
QWEATHER_API_HOST
TAVILY_API_KEY
FIRECRAWL_API_KEY
FIRECRAWL_MCP_URL
```

前端构建变量：

```text
VITE_AMAP_KEY
VITE_AMAP_SECURITY_CODE
```

---

## 🧪 测试

后端：

```bash
cd src/backend
.venv\Scripts\python -m pytest -q
```

前端：

```bash
cd src/frontend
npm run lint
npm run build
```

当前测试覆盖：

- 行程生成与路线优化
- 闭馆规则引擎
- 开放时间日期感知
- facts 统一风险输出与持久化
- Agent 工具调用

---

## ☁️ 部署（Railway）

项目已支持 Railway 部署：

- 后端：Python + Uvicorn，启动前自动执行 `alembic upgrade head`
- 前端：Node 构建 + Nginx 托管，Nginx 代理 `/api` 到后端内部服务
- 数据库：Railway 托管 PostgreSQL
- 端口：统一使用 Railway 注入的 `PORT`

前端 `BACKEND_URL` 示例：

```text
http://backend:8080
```

---

## 🧠 设计要点

1. **多 Agent Supervisor 编排**
2. **确定性规则与 LLM 分层**
   - 规则引擎负责确定性强的事
   - LLM 负责汇总与解释
3. **外部 API 快速失败 + 降级兜底**
   - 高德超时自动降级到估算
4. **同源代理**
   - Nginx 反向代理 `/api`，避免 CORS
5. **可追溯**
   - fact_checks 持久化
   - 每个风险结果包含来源和建议确认

---

## 🗺️ 后续路线

- [ ] 动态公告搜索：Tavily + Firecrawl 接入 fact_checker
- [ ] 跨天拖拽编辑
- [ ] 版本快照与回滚
- [ ] 异步行程生成 + 进度条
- [ ] `facts/checks` 查询接口
- [ ] 清理 `useAgents.ts` 死代码

---

## 📄 文档

- [文档索引](docs/README.md)
- [下一阶段产品与技术架构](docs/plans/next-phase-design.md)
- [常驻AI对话与地图联动方案](docs/plans/ai-chat-collaboration-design.md)
- [开发问题与解决方案](docs/retrospectives/development-notes.md)
- [Fact Check 模块复盘](docs/retrospectives/factcheck-retrospective.md)
- [城市/景区双模式路线规划复盘](docs/retrospectives/scenic-routes-retrospective.md)

---

## 📦 Demo

```text
https://travel-40d77.up.railway.app
```
