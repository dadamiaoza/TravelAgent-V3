# 2026-09-03 复盘：可靠异步生成（任务绝不能无声失败）

开发内容：把行程生成从「后台跑一跑、前端轮询一下」收成可证明的 Job 契约。五态状态机、`FOR UPDATE SKIP LOCKED` 领取、`run_token` fencing、有限重试、心跳超时恢复、Job GET + 进度 SSE。

对照：四周主线第 1 周「任务绝不无声失败」。代码在 `generation_jobs.py`、`job_worker.py`。

---

## 问题速查表

| # | 类别 | 问题 | 解法 |
|---|------|------|------|
| 1 | 产品误判 | 生成卡住，先怀疑代理 / 模型慢 | 先画调用链：任务落库了，但 Worker 一崩就挂死 |
| 2 | 状态机 | `pending/running/succeeded` 字符串乱写，失败立刻改回 pending | 五态 + `validate_job_transition`；耗尽失败必须带 reason |
| 3 | 并发领取 | 多 Worker 可能领同一条 Job | `FOR UPDATE SKIP LOCKED`，单实例也能测互斥 |
| 4 | 覆盖写入 | 旧 attempt 心跳 / 完成后台写回来 | 每次领取发 `run_token`，阶段和 finalize 都校验 token |
| 5 | 卡死 | `running` 进程崩溃后任务永不结束 | 心跳 + stale recovery；重试有上限和指数退避 |
| 6 | 数据 | 行程被删，Job 还在跑 | 缺 Trip → 终端失败 `TRIP_NOT_FOUND`，不卡在 running |
| 7 | 前端 | 只有 `trip.id`，刷新丢进度；SSE 曾经只用于聊天 | `GET /jobs/{id}` 为真源；生成进度 SSE 只做通知 |
| 8 | 运维 | Alembic `0014` 卡住，像迁移写坏了 | Postgres `ACCESS EXCLUSIVE` 等不到，根因是 idle-in-transaction 的旧 Worker |
| 9 | 测试 | 名字里带 `generate_itinerary` 的单测被 `-m 'not agent'` 跳过 | `conftest` 按测试名自动标 agent；改名或显式 mark |

---

## 错误清单

### 1. 先怪模型和代理，其实是任务生命周期没设计

**现象**：生成页面停很久，或刷新后不知道成功还是失败。ADR 写过「异步 + SSE」，实现一度只有轮询，Worker 挂了任务就挂死。

**误判**：网络 / MiniMax / 没开 TUN。

**真因**：长任务没有「被谁领、能不能重试、谁有权写终态」。内存里的希望不是契约。

**解法**：Job 表是真源。合法转换显式列出；非法转换拒绝。前端断线用 HTTP 回查，不把 SSE 当状态机。

**教训**：Agent 项目里最像「模型问题」的，经常是任务问题。面试先讲误判，再讲真因。

---

### 2. 状态机必须可测试，不能靠约定

**五态**：`pending` → `running` → `succeeded` / `failed`；`running` → `retry_wait` → `running`。

**坑**：生产路径曾经绕过统一转换函数；耗尽重试时出现单测判非法的 `pending|retry_wait → failed`。审查口径：不能 APPROVE。

**解法**：所有状态写入走 `validate_job_transition` / `apply_job_transition`。耗尽失败用带 `reason` 的终端转换，不直接写字符串。

**教训**：状态机写在注释里等于没有。面试官要的是「非法转换会炸掉哪条测试」。

---

### 3. 抢占用 Postgres，不上 Redis

**现象**：两个 Worker 都查 `pending`，可能领同一条。

**解法**：短事务 `SELECT … FOR UPDATE SKIP LOCKED`。eligible = `pending`，或 `retry_wait` 且 `next_run_at <= now`。

**为什么不是 Redis 锁**：真源已经在 PostgreSQL。单实例就能写双 Worker 测试。为了面经加 Redis 是假复杂度。这和 5 月「不要为语义问题写规则管线」是同一类错误：用错工具装专业。

---

### 4. fencing：旧 Worker 必须写不进去

**现象**：超时回收后新 attempt 已开始，旧进程还在 `optimize` 或写进度。

**解法**：领取时发新 UUID `run_token`。`append_job_stage`、心跳、`finalize_job_success` 全部带 token。对不上就丢弃。

**面试一句话**：锁解决「谁先领」，token 解决「领完之后谁还算数」。

---

### 5. Alembic 卡住不是迁移写错了

**现象**：`alembic upgrade head`（`0014` 给 Job 加 `stages`）挂住，版本停在 `0013`。

**真因**：`ACCESS EXCLUSIVE` 等行锁。旧 uvicorn + 卡死的 generation job 占着 `idle in transaction`。

**解法**：查出阻塞会话并结束；不要先改 migration 内容。

**教训**：迁移工具的「卡住」优先查锁，再怀疑 SQL。和 5 月「旧 uvicorn 还占着端口」是同一类：先确认谁活着。

---

### 6. 测试名字也会说谎

**现象**：规划管线单测写好了，`pytest -m 'not agent'` 跑不到。

**真因**：`conftest.py` 测试名包含 `generate_itinerary` 就自动标 `agent`。

**解法**：改名为 `test_draft_calls_optimize_itinerary_directly`。

**教训**：测试基础设施是产品行为的一部分。跳过不等于通过。

---

## 本日技术收获

1. 长任务三件套：**状态机、抢占、fencing**。缺一都会在面试追问里露馅。
2. SSE 是通知通道，Job 行才是状态。刷新、重连、多标签页都以 GET 为准。
3. 错误要分类：可重试（模型 JSON 坏了）vs 不可重试（Trip 不存在）。用户看到的文案不能带堆栈。
4. 不为面经引入 Redis / Celery / Kafka。Postgres 已经能把故事讲完。

---

## 面试钩子（本篇只留三句）

- 现象：「生成到一半刷新，页面不知道该转圈还是该报错。」
- 误判：「我以为要上 Redis 队列才算异步。」
- 开门：「如果你问多 Worker 抢同一条任务，我可以讲 SKIP LOCKED 和 run_token 为什么要拆开。」

完整引导顺序见 [interview-steering.md](interview-steering.md)。

---

## 与已有知识的串联

- [knowledge-map.md §5](knowledge-map.md#5-命令行-vs-web谁控制主循环) — Web 没有 while；后台 Worker 才是生成的主循环
- [knowledge-map.md §7](knowledge-map.md#7-工程分层schemas--services--agents--tools) — Job 生命周期在 Service，不在 Agent
- [knowledge-map.md §14](knowledge-map.md#14-可靠异步生成job-才是真源) — 概念收口
- [2026-05-16 DB 脚手架](2026-05-16_DB-Scaffolding-Pitfalls.md) #3 — 旧进程占资源，同一排查习惯
