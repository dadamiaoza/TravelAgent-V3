# Fact Check 模块复盘记录

> 本文档只记录 fact_checker 增强过程中的真实问题、权衡和面试可讲的设计决策。
> 不与其他开发文档混合。

## 任务 A-1: 闭馆规则引擎数据结构与原型

### 做了什么
- 设计了规则引擎的数据结构，采用 **JSON 配置文件**，而不是硬编码 Python 或数据库表。
- 新增：
  - `src/backend/app/services/closure_rules.json`
  - `src/backend/app/services/closure_rules.py`
  - `src/backend/tests/test_closure_rules.py`
- 规则引擎支持：
  - `contains` 字符串匹配 POI
  - 周固定闭馆：`closed_weekdays`
  - 节假日特殊调整：`holiday_override` / `holiday_closure`
  - 优先级覆盖：`priority` 越大越优先，节假日覆盖 > 周闭馆
- 示例规则：
  - 博物馆周一闭馆
  - 纪念馆周一闭馆
  - 博物馆国庆假期正常开放（覆盖周一闭馆）
  - 景区国庆假期可能限流/调整

### 遇到的问题 / 权衡取舍
1. **Python weekday 0 表示周一，不是 1**
   - 一开始把 `closed_weekdays` 写成 `[1]`，导致周一不命中、周二命中。
   - 通过测试发现并修正为 `[0]`。
   - 教训：规则配置里的“星期”必须和 Python API 的约定对齐，最好在配置注释里写清楚。

2. **为什么选 JSON 而不是硬编码或数据库**
   - 硬编码：快，但规则和代码耦合，后续改规则要改代码。
   - 数据库：生产级，但本轮只是 3-5 条原型规则，引入迁移和管理成本过高。
   - JSON：规则数据与引擎代码分离，方便后续迁移到数据库，当前投入也最小。

3. **优先级和“节假日覆盖”怎么建模**
   - 没有采用“每条规则单独判断后合并”的复杂模型。
   - 采用“找出所有适用规则 → 按 priority 排序 → 取最高优先级规则决定结果”的简单模型。
   - 好处：行为可预测；坏处：如果真实规则很复杂，后续需要引入规则冲突检测。

### 面试可以怎么讲
- “我把规则数据从代码中抽离成 JSON，是因为规则会持续变化，应该让数据可配置，而不是每次改代码。”
- “规则引擎不追求覆盖全国所有景区，而是先用少量示例规则验证数据结构和判断逻辑，后续再接入真实数据源。”
- “产品原则：输出风险提示和来源，不承诺 100% 准确；规则引擎只负责确定性强的那一层。”

### 已识别但本次不做的延伸点
- 动态公告搜索（Tavily + Firecrawl）可以补充临时闭园、天气闭园，本次明确不做。
- 规则冲突检测、规则生效时间、规则来源分级，以后如果规则变多需要再设计。
- 目前 `date_range` 是固定日期范围；后续可升级成“每年重复的节假日规则”或维护独立节假日日历。


## 任务 A-2: get_opening_hours 日期感知增强

### 做了什么
- 先做现状分析，确认：
  - `get_weather(city, date)` 已经真正支持指定日期，无需改造。
  - `get_opening_hours(name, date)` 签名支持日期，但之前只把日期当作展示文本，没有用来判断规则。
- 采用方案 1：保持工具签名和字符串返回，在 `get_opening_hours` 内部接入 A-1 规则引擎。
- 新增 `_append_rule_hint`：
  - 命中闭馆规则：输出“时效提示 + 原因 + 来源 + 建议出行前再确认”。
  - 命中节假日调整：同样输出时效提示。
  - 未命中规则：输出“未命中固定闭馆规则；建议出行前以官方公告为准”。
- 新增 `tests/test_opening_hours.py`。

### 遇到的问题 / 权衡取舍
1. **为什么不改工具签名为结构化 JSON**
   - 虽然 JSON 更结构化，但会改变 agent 对工具返回的解析方式，影响面更大。
   - 本轮目标是“先让工具具备日期感知”，保持字符串返回是最小改动。
   - A-3 汇总层再负责把信息整合成统一 JSON。

2. **规则提示放在工具层还是汇总层**
   - 放在工具层：单个工具被调用时也能给出风险提示。
   - 放在汇总层：只有最终 Agent 能看到。
   - 选择放在工具层，因为这样工具本身更完整，后续其他调用方也能复用。

3. **产品原则如何落地**
   - 无论是否命中，都输出“建议出行前再确认/以官方公告为准”。
   - 避免给用户一种“系统已经绝对确认”的错觉。

### 面试可以怎么讲
- “我没有为了‘看起来更结构化’去改工具返回协议，而是先保持向后兼容，用最小改动让现有工具具备日期感知。”
- “规则引擎是确定性层，工具层负责把规则结果拼进开放时间结果，LLM 汇总层负责最终风险判断，每一层职责单一。”
- “即使没有命中规则，也会提示用户以官方公告为准，因为时效信息不可能 100% 准确。”

### 已识别但本次不做的延伸点
- 动态公告搜索（Tavily + Firecrawl）仍未接入。
- `get_weather` 暂时未增加“天气可能导致闭园”的规则联动，这部分需要动态信息才能做好。


## 任务 A-3: fact_checker 统一风险汇总输出

### 做了什么
- 设计并实现统一风险汇总 JSON：
  - `poi_name / date / risk / risk_type / reason / source / weather / opening_hours / needs_manual_confirmation / advice / checked_at`
- 修改 `FactCheckResult` schema，增加 `risk_type / reason / source / needs_manual_confirmation / advice / checked_at`。
- 修改 `POST /facts/check`：
  - 后端先调用规则引擎（第 1 层），把结果注入 prompt。
  - 再让 fact_checker Agent 调 `get_weather / get_opening_hours`。
  - 最后由 LLM 汇总成统一 JSON 数组。
  - `checked_at` 由后端生成，避免 LLM 编造时间。
- 修改 fact_checker Agent system prompt，要求输出统一 JSON 数组。
- 新增 `tests/test_facts_api.py`。
- 全部测试通过：
  - 规则、工具、接口相关 11 个测试通过
  - 原有 agent 测试 3 个通过

### 遇到的问题 / 权衡取舍
1. **规则引擎结果如何交给 LLM**
   - 选项 A：做成 Agent Tool，让 LLM 决定是否调用。
   - 选项 B：后端预计算后注入 prompt。
   - 选择 B，因为规则是确定性逻辑，不依赖 LLM 的“意愿”；同时减少一次 tool call，结果更稳定。

2. **`checked_at` 由谁生成**
   - 如果让 LLM 输出时间，可能编造一个看起来合理但错误的时间。
   - 所以由 FastAPI 层在返回前统一生成，保证可追溯、可信。

3. **是否保留旧字段**
   - 保留了 `weather`、`opening_hours`、`risk` 等旧字段，同时新增字段。
   - 这样对现有调用方更友好，前端后续可以直接消费新结构。

### 面试可以怎么讲
- “确定性规则由后端预计算，确定性逻辑不交给 LLM 决定；LLM 只负责汇总和解释。”
- “所有输出都带 `source` 和 `needs_manual_confirmation`，体现‘风险提示而不是绝对保证’的产品原则。”
- “`checked_at` 由系统生成，保证审计时间可信。”

### 已识别但本次不做的延伸点
- 动态公告搜索（Tavily + Firecrawl）仍未接入，用于临时闭园/天气闭园。
- `fact_checks` 持久化（A-4）尚未做。

## 任务 A-4: fact_checks 持久化

### 做了什么
- 新增 `FactCheckRecord` ORM 模型，表名 `fact_checks`。
- 新增 Alembic migration `0003_fact_checks.py`，并已在本机执行 `alembic upgrade head` 成功。
- 扩展 `FactCheckRequest` / `FactCheckItem`：
  - 请求级可选 `trip_id`
  - 单项可选 `itinerary_item_id`
  - 不传仍兼容，传了可追溯。
- 修改 `/facts/check`：
  - 增加 `db` 依赖。
  - 每次校验结果写入 `fact_checks`。
  - 保存关联、风险字段、来源、建议和 `checked_at`。
- 更新测试，新增“持久化并保留 trip/item 关联”的测试。
- 测试结果：
  - 相关接口/规则/工具测试 12 个通过
  - 原有 fact_checker Agent 测试 3 个通过

### 遇到的问题 / 权衡取舍
1. **关联字段是可选的**
   - 当前调用方不一定传 `trip_id` / `itinerary_item_id`。
   - 如果强制必填，会破坏现有 API 兼容性。
   - 所以采用“可选 + NULL”，既能立即落库，又能支持未来前端传关联。

2. **为什么用单表而不是批次表/JSONB**
   - 当前查询以“某个行程/某个 POI 的风险”为主。
   - 单表结构最直接，不需要 join。
   - 以后如果一次请求要完整审计，可以再增加批次 ID，不推翻主表。

3. **落库时 LLM 返回结果和请求项的对应关系**
   - 不能假设 LLM 一定按顺序返回。
   - 使用 `(poi_name, date)` 作为 key 找回原始请求项，从而正确保存 `itinerary_item_id`。

### 面试可以怎么讲
- “持久化采用可选关联，优先保证向后兼容，同时为后续追溯留好字段。”
- “校验结果不只返回给前端，还落库，这样风险历史可以查询和复盘。”
- “Alembic 管理数据库结构，代码和迁移同步提交，部署时可以直接升级。”

### 已识别但本次不做的延伸点
- 目前还没有查询 `fact_checks` 的 REST 端点，后续可以加 `GET /facts/checks?trip_id=...`。
- 动态公告搜索（Tavily + Firecrawl）仍未接入。

