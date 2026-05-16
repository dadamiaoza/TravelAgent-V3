# AI 旅行规划助手 — 开发指南

## 环境要求

- Python >= 3.12
- Node.js >= 20
- Docker Desktop（运行 PostgreSQL）

## 项目结构

```
src/
├── backend/          FastAPI 后端 (Python)
│   ├── app/
│   │   ├── api/      REST 路由层
│   │   ├── services/  业务逻辑层
│   │   ├── agents/    LangChain Agent 层 ★
│   │   ├── models/    ORM 模型
│   │   └── schemas/   Pydantic 模型
│   ├── alembic/      数据库迁移
│   └── tests/
├── frontend/         React (Vite) 前端 (TypeScript)
│   └── src/
│       ├── pages/    页面组件
│       ├── components/ 通用组件
│       ├── lib/      工具库
│       └── hooks/    自定义 Hooks
├── scripts/          工具脚本
└── docker-compose.yml
```

## 快速启动

### 1. 启动数据库
```bash
cd src
docker compose up -d
```

### 2. 启动后端
```bash
cd src/backend
cp .env.example .env
# 编辑 .env 填入你的 LLM API Key

pip install -e .        # 或者: uv sync
python run_server.py    # http://localhost:8000
```

### 3. 启动前端
```bash
cd src/frontend
npm install
npm run dev             # http://localhost:5173
```

### 4. 验证健康检查
```bash
curl http://localhost:8000/api/v1/health   # → {"status":"ok"}
curl http://localhost:5173                  # → HTML page
```

## 数据库迁移

```bash
cd src/backend
alembic upgrade head        # 执行所有迁移
alembic revision --autogenerate -m "description"  # 生成新迁移
alembic downgrade -1        # 回滚一个版本
```

## 运行测试

```bash
# 后端
cd src/backend && python -m pytest -q

# 前端
cd src/frontend && npm run lint && npm run build

# 端到端冒烟
cd src && pwsh -ExecutionPolicy Bypass -File .\scripts\smoke-test.ps1
```

## Agent 学习路径

详见 `backend/app/agents/__init__.py` 中的注释，从 `tools/` 开始逐步学习。
