# 2026-05-16 复盘：方向C — DB 脚手架

开发内容：创建数据库迁移、ORM 模型、Pydantic schema、API 端点（trips CRUD），完成端到端验证。

---

## 问题速查表

| # | 类别 | 问题 | 解法 | 行号 |
|---|------|------|------|------|
| 1 | Python 打包 | pyproject.toml flat-layout 报错 | 添加 `[tool.setuptools.packages.find]` | L20 |
| 2 | PowerShell | `$pid` 赋值报错（只读变量） | 改用 `$serverPid` 等变量名 | L48 |
| 3 | 进程管理 | 旧代码仍在运行，新代码不生效 | `Get-NetTCPConnection` + `Stop-Process` | L62 |
| 4 | Python 环境 | 系统 Python 没有 psycopg2 | 激活 `.venv` 或用 `.venv\Scripts\python.exe` | L94 |
| 5 | 进程管理 | subprocess stderr 管道导致服务卡死 | 用 `Start-Process`，不重定向输出 | L114 |
| 6 | SQLAlchemy | POST 请求超时 500 | 加 `server_default=text("now()")` | L134 |
| 7 | PowerShell | 内联 Python 转义混乱 | 超过一行就写 .py 脚本文件 | L160 |
| — | 概念 | `.venv` 和 `uv` 的区别 | `.venv`=隔离房间，`uv`=更快的管家 | L240 |
| — | 项目结构 | 为什么 `.venv` 在 backend/ 下 | 和 `pyproject.toml` 同级，前端用 `node_modules` | L246

## 错误清单

### 1. pyproject.toml flat-layout 打包错误

**现象**：
```
error: Multiple top-level packages discovered in a flat-layout: ['app', 'alembic']
```

**原因**：项目的 `pyproject.toml` 缺少打包元数据，setuptools 无法区分哪些是 Python 包。

**解决**：在 `pyproject.toml` 中添加：

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[tool.setuptools.packages.find]
include = ["app*"]
```

**教训**：只要项目用了 `pip install -e .`，就必须配置 `[tool.setuptools.packages.find]`，明确告诉 setuptools 哪些目录是 Python 包。

---

### 2. PowerShell `$pid` 是只读变量

**现象**：
```powershell
$pid = 12345   # 报错：Cannot overwrite variable PID
```

**原因**：PowerShell 内置 `$pid` 自动变量存储当前进程 ID，不可覆盖。

**解决**：使用其他变量名，如 `$serverPid`、`$procId`。

**教训**：Windows 下不要用 `$pid` 作为自定义变量名。`$PID`、`$pid`、`$Pid` 都是同一个内置变量（大小写不敏感）。

---

### 3. 服务进程管理混乱（旧代码 vs 新代码）

**现象**：修改代码后重启服务，API 仍返回旧字段名错误（`travel_period` 422），仿佛修改没生效。

**原因**：
- 之前的 uvicorn 进程没有被正确杀掉，旧进程仍占用端口
- 新进程启动失败（静默失败），旧进程继续提供服务
- `uvicorn --reload` 只在文件变更时重载，但如果启动时就失败了，用户感知不到

**排查方法**：
```powershell
# 查看谁占用了目标端口
Get-NetTCPConnection -LocalPort 8001 | Select-Object LocalAddress, LocalPort, OwningProcess, State

# 强制杀掉占用进程
Get-NetTCPConnection -LocalPort 8001 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

**解决**：
1. 强制杀掉所有占用端口的进程
2. 使用 `Start-Process` 启动服务（不阻塞终端），而不是 subprocess+piping
3. 启动后用 `Start-Sleep 3` 等待，再验证

**教训**：
- 修改代码后务必确认旧进程已死，端口已释放
- `--reload` 不是万能的——如果导入阶段就挂了，reload 根本帮不上忙
- Windows 上没有 `lsof -i :8001`，替代品是 `Get-NetTCPConnection`

---

### 4. 系统 Python vs 虚拟环境 Python

**现象**：
```
ModuleNotFoundError: No module named 'psycopg2'
```

**原因**：运行 `python -m uvicorn ...` 用的是**系统 Python**（`D:\anaconda3\`），而依赖包装在项目 `.venv/` 里。

**解决**：使用 venv 中的绝对路径：
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app ...
```

**教训**：
- 始终用 venv 内的 python，或先激活 venv：`.\.venv\Scripts\Activate.ps1`
- 用 `(Get-Command python).Source` 可以确认当前用的是哪个 Python
- 系统装了多个 Python（Anaconda + 独立安装）时特别容易踩坑

---

### 5. subprocess stderr 管道导致服务卡死

**现象**：用 `subprocess.Popen(stderr=PIPE)` 启动 uvicorn 后，POST 请求超时。

**原因**：stderr 管道缓冲区满了后，uvicorn 的写操作被阻塞，整个事件循环卡死。

**解决**：改用 PowerShell `Start-Process` 启动服务，不重定向输出：
```powershell
Start-Process -FilePath ".\.venv\Scripts\python.exe" `
  -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8001" `
  -WindowStyle Hidden
```

**教训**：
- 如果不需要捕获进程输出，不要用 `PIPE`
- 如果必须捕获，用 `Popen(stderr=PIPE)` 的同时要**开线程消费管道**，否则管道满了就卡死
- Windows 上 subprocess 和 PowerShell 混用时，推荐直接用 PowerShell Start-Process

---

### 6. ORM 模型缺少 server_default 导致 500

**现象**：POST 请求超时 / 返回 500。

**原因**：SQLAlchemy 模型中有 `created_at` 和 `updated_at` 字段，但没有设置数据库默认值。当 session flush 时，数据库期望这些列有值却收到 NULL（或行为未定义）。

**原始代码**：
```python
created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

**修复后**：
```python
from sqlalchemy import text

created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
```

**教训**：
- 有时间戳字段的 ORM 模型，必须指定 `server_default` 或 `default`
- `server_default=text("now()")` 是在**数据库侧**生成默认值，不依赖 Python
- 为了让 `from sqlalchemy import text` 生效，记得 import

---

### 7. PowerShell 内联 Python 的转义地狱

**现象**：在 PowerShell 中执行 `python -c "..."` 时，Python 的 f-string 花括号 `{}` 与 PowerShell 的变量插值冲突。

**尝试失败的命令**：
```powershell
python -c "exec('a')"   # 永远不对劲
```

**解决**：不要用 `-c` 内联执行复杂 Python，**直接写 .py 文件再运行**。
```powershell
# 坏做法
python -c "from app.models.trip import ...; print(...)"

# 好做法
New-Item test_xxx.py
# 写入代码...
python test_xxx.py
```

**教训**：
- PowerShell 的 `$`、`{}`、`"`、换行符都可能与 Python 语法冲突
- 简单一句可以用 `-c`，超过一行请写脚本文件
- 这里是 Windows 开发特有的痛点

---

## 用户提问记录（无知时刻 → 答案）

### Q1: "怎么自己运行脚本？"

**当时状态**：用户不知道如何在终端操作 Python 项目。

**答案**：
1. `cd F:\My_Code\TravelAgent-V3\src\backend` — 进入项目目录
2. `.\.venv\Scripts\Activate.ps1` — 激活虚拟环境（如报执行策略错误需先 `Set-ExecutionPolicy`）
3. `python test_db.py` — 运行脚本

PS 激活后命令提示符前面会出现 `(.venv)`，说明已进入虚拟环境。

---

### Q2: "Docker 中的数据库数据怎么查看？"

**当时状态**：用户知道数据库跑在 Docker 里，但不知道怎么连接查询。

**答案**：三种方法——

| 方法 | 命令 | 适用场景 |
|------|------|----------|
| 进入容器交互 | `docker exec -it travel-agent-db psql -U travel -d travel_agent` | 临时查看、探索 |
| 单条 SQL | `docker exec -it travel-agent-db psql -U travel -d travel_agent -c "SQL"` | 快速查询 |
| Python 脚本 | `python -c "from app.db.session import SessionLocal; ..."` | 批量/复杂查询 |

psql 交互界面的基本命令：
- `\dt` — 列出所有表
- `\d 表名` — 查看表结构
- `SELECT ...;` — 执行查询（注意**必须加分号 `;`**）
- `\q` — 退出

---

### Q3: "为什么 psql 报语法错误？"

**现象**：
```
travel_agent=# SELECT id, destination FROM trips
travel_agent-# SELECT id, destination FROM trips;
ERROR:  syntax error at or near "SELECT"
```

用户连续输入了两条 SELECT，第一条没加分号所以 psql 认为语句没结束（`-#` 是续行提示符），然后又输入了第二条 SELECT，于是 psql 把两条拼在一起解析，当然报语法错误。

**答案**：psql 中**每条 SQL 必须以分号 `;` 结尾**才会执行。没有分号就换行，psql 认为你还在写同一条语句。

---

### Q4: "`WHERE trip_id = '你的trip_id'` 为什么报错？"

**现象**：用户直接复制了示例中的占位符 `'你的trip_id'`。

**答案**：那是占位符，需要替换为真实 UUID。先用 `SELECT id FROM trips;` 查到真实 ID，再把那一长串 UUID 复制进 WHERE 条件。

---

### Q5: "`.venv` 和 `uv` 有什么区别？"

**当时状态**：用户看到很多 Python 教程提到 `uv`，不清楚和 `.venv` 的关系。

**答案**：

| | `.venv` | `uv` |
|---|---|---|
| 是什么 | 虚拟环境**目录** | Python 包管理**工具** |
| 作用 | 隔离依赖 | 替代 pip + venv + pip-tools |
| 类比 | 一个隔离的"房间" | 管理房间的"管家" |
| 速度 | —（只是目录） | 比 pip 快 10-100 倍（Rust 实现） |

```
# 传统方式（pip）
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install fastapi uvicorn sqlalchemy

# uv 方式（一条命令替代上面三步）
uv venv
uv pip install fastapi uvicorn sqlalchemy
```

**当前项目用的是 `.venv` + pip**，没有用 uv。`.venv` 是"隔离的房间"，pip 是往里面装包的工具，这是完全正常的组合。

---

### Q6: "为什么 `.venv` 在 `backend/` 下，不在项目根目录？"

**当时状态**：用户发现很多简单项目 `.venv` 在根目录，但本项目不是。

**答案**：因为这是 **monorepo（多子项目仓库）**：

```
TravelAgent-V3/           ← 仓库根
├── src/
│   ├── backend/          ← Python 项目 → 需要 .venv/
│   │   ├── pyproject.toml
│   │   └── .venv/
│   └── frontend/         ← Node.js 项目 → 需要 node_modules/
│       ├── package.json
│       └── node_modules/
```

**核心原则**：`.venv` 和 `pyproject.toml` 应该在**同一级目录**。这和 `node_modules` 不放根目录是同一个道理——根目录没有 `pyproject.toml`，前端也不需要 Python。

---

## 本日技术收获

1. **SQLAlchemy 2.0 Mapped[] 语法**：`Mapped[类型] = mapped_column(参数)` 是声明式 ORM 的标准写法
2. **Alembic 迁移流程**：`alembic revision --autogenerate -m "描述"` → `alembic upgrade head`
3. **FastAPI API 三层结构**：Router（IO 层）→ Service（业务逻辑）→ Model（ORM）
4. **Pydantic v2 schema**：用 `model_config = {"from_attributes": True}` 支持 ORM 对象序列化
5. **Docker exec 访问 PostgreSQL**：无需安装本地 psql 客户端，直接用容器内的
6. **Windows Python 开发的独特痛点**：多版本 Python 共存、PowerShell 转义、进程管理麻烦

---

## 项目当前状态

| 项目 | 状态 |
|------|------|
| MiniMax Agent 工具调用 | ✅ Step 1 完成（test_agent.py 通过） |
| DB 脚手架 | ✅ 方向C 完成（4 张表，4 个 API 端点） |
| 正式 pytest 用例 | ⬜ 待做（Step 2-B） |
| fact_checker 第二个 Tool | ⬜ 待做（Step 2-A） |
