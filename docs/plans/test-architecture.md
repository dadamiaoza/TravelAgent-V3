# 测试架构治理方案

> 目标：测试“短平快、分层清晰、新增功能不膨胀”。
> 当前已落地：test markers、unit 目录、fakes/factories、默认排除 agent 测试。

---

## 1. 当前测试分层

```text
tests/
├── conftest.py                  # markers + DB/client fixture
├── fakes.py                     # 共享测试替身
├── factories.py                 # Trip/Day/Item 工厂
├── unit/                        # 纯逻辑，无 DB/LLM
│   ├── test_schedule.py
│   └── test_generator_adapter.py
├── test_*.py                    # 存量测试（后续逐步迁移）
```

## 2. Marker 约定

| marker | 含义 | 默认 |
|---|---|---|
| `unit` | 纯逻辑，无 DB / LLM | ✅ 运行 |
| `integration` | 真实数据库 | ✅ 运行 |
| `agent` | 真实 LLM / 外部服务 | ❌ 默认排除 |
| `slow` | 预留慢测试标记 | ❌ 可选 |

默认命令：

```bash
pytest -m "not agent"
```

需要跑 Agent 测试：

```bash
RUN_AGENT_TESTS=1 pytest -m agent
```

## 3. 已经完成

- [x] `pyproject.toml` 增加 marker 和默认排除 agent
- [x] `conftest.py` 自动标记 Agent 测试
- [x] `tests/unit/` 纯单测
- [x] `tests/fakes.py`
- [x] `tests/factories.py`
- [x] 非 Agent 测试 51 个全部通过，Agent 23 个默认排除
- [x] unit 5 个纯单测（schedule / generator adapter / trip_editor orchestration）
- [ ] Unit of Work / 事务回滚 DB fixture（下一步）
- [ ] 存量测试拆分到 `integration/` 和 `agents/`
- [ ] 前端测试（Vitest / Testing Library）

## 4. 后续迁移顺序

1. `conftest.py` 引入事务回滚，避免污染真实数据
2. 拆分 `tests/integration/`：
   - trips API
   - items API
   - reoptimize API
3. 拆分 `tests/agents/`：
   - itinerary_gen
   - supervisor
   - guide_parser
   - fact_checker
4. 新增 `tests/unit/test_trip_editor.py`，用 Fake Ports 单测服务层
5. 前端测试从地图联动开始补