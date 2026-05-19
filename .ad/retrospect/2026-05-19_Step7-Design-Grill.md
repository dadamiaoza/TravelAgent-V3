# Step 7：工具升级 — Mock → 真实 API（设计讨论）

## 概述

**日期**：2026-05-19
**阶段**：需求分析 + 方案设计（编码尚未开始）
**学习目标**：在 Agent 架构不变的前提下，把 mock 工具替换为真实 API，让项目从"学习演示"变成"可用的应用"

---

## 背景：项目当前状态

### 5 个 Mock 工具

| 工具 | 文件 | Mock 实现 | 问题 |
|------|------|-----------|------|
| `geocode_poi` | `tools/geo.py` | 20 个硬编码 POI + hash fallback | 只覆盖 3 个城市的主要景点 |
| `search_attractions` | `tools/attractions.py` | 3 城市 × 10 POI 字典 | 数据不全，无法应对新城市 |
| `get_travel_time` | `tools/attractions.py` | hash 随机数 10-50 分钟 | 和真实路网无关 |
| `get_opening_hours` | `tools/opening_hours.py` | 永远返回同一句话 | 忽略名称和日期参数 |
| `get_weather` | `tools/weather.py` | 永远返回"晴转多云 15-25°C" | 忽略城市和日期参数 |

### 约束：接口不变

Tool 的输入/输出签名保持不变，只改内部实现。Agent 层和 Service 层零改动。

**为什么这是最重要的设计约束**：你在 Step 1-6 中学到的架构分层正是为了这一刻——底层 Tool 可以整体替换，而上层 Agent 毫无感知。这是好架构的价值。

---

## 设计讨论：逐一决策

### 决策 1：实现顺序

**选择**：geocode → travel_time → attractions → opening_hours → weather

**为什么这个顺序**：
- `geocode_poi` 最基础——`get_travel_time` 和 `route_optimizer` 都依赖它
- `get_travel_time` 排在第二——它需要 geocode + 路径规划，验证两个 API 的协同
- `search_attractions` 最复杂——POI 搜索 + 结果解析 + 结构化输出
- `get_opening_hours` 独立，放后面
- `get_weather` 用不同的供应商（和风天气），独立配置，放最后

### 决策 2：API 选型

**高德地图 API**（地理编码、路径规划、POI 搜索）：
- Key 已配置：`d38a38c06b59257140575ae9c51e3c65`
- 免费额度充足（地理编码 30 万次/天）
- 覆盖所有需要的地理能力

**和风天气 API**（天气查询）：
- 使用 JWT 认证（Ed25519 签名）
- 凭据已配置：
  - Key ID：`KEWGFFVW2K`
  - Project ID：`39KVCAMC2Y`
  - API Host：`mw3mdafdep.re.qweatherapi.com`
- 已授权 API：GeoAPI、分钟降水、空气质量、时光机、天气预报、天气预警、天气指数、天文
- MVP 只接天气预报（`/v7/weather/7d`），其余留到后续增强

### 决策 3：降级策略

**选择**：无 Key 或 API 调用失败 → 自动退回 mock + `logging.warning`

**为什么不是抛异常**：API 超时会直接导致 Agent 崩溃，用户拿不到任何结果

**为什么不是返回错误字符串**：LLM 收到"查询失败"后可能会**幻觉**——自己编一个数字。你不知道结果是真实数据还是 AI 编的。

**为什么是降级 mock**：
- Tool 对 Agent 的承诺是"调用我，我给你结果"。降级保证了承诺永远不破。
- Agent 全程无感知，不需要判断"这是真实数据还是估算"——它只管用。
- 开发者通过 `logging.warning` 知道降级发生了，可以排查问题。

```
get_travel_time("故宫", "长城")
  ├── 有 Key + API 正常 → 高德路径规划 → 返回真实分钟数
  ├── 没有 Key           → mock hash 估算 → logging.warning("无 Key，使用 mock")
  └── API 超时           → mock hash 估算 → logging.warning("API 失败，降级 mock")
```

### 决策 4：geocode_poi 签名变更

**当前签名**：`geocode_poi(name: str) -> dict`
**新签名**：`geocode_poi(name: str, city: str = "") -> dict`

**为什么加 `city` 参数**：
- 高德地理编码 API 支持 `city` 参数，传了更精确（同名的"故宫"在多个城市都有）
- `city` 默认空字符串 → 向后兼容，不传也能用

### 决策 5：get_travel_time — Tool 内部闭环

**选择**：保持当前签名 `get_travel_time(from_poi, to_poi, mode)`，Tool 内部自己做 geocode + 路径规划。

**为什么不拆成两步让 Agent 调**：
- "先 geocode 拿到坐标，再用坐标算路径"是确定性流程，没有 AI 判断的必要
- 让 LLM 编排这些步骤 = 浪费 LLM 调用次数 + 增加失败面

**设计原则**：能确定做的事情，就不要让 LLM 来做。确定性逻辑留在代码，AI 只做不确定性判断。

### 决策 6：search_attractions — 先 A 后 B

**A 方案**（MVP 采用）：`preference` 参数透传给高德 `keywords`
```
preference="自然风光" → keywords="自然风光"
```

**B 方案**（效果不好时升级）：`preference` 映射为高德 `types` 分类码
```
preference="自然风光" → types="110000|140000"
```

**为什么先用 A**：简单方案能验证流程，效果不好再升级。不要一开始就引入复杂度。

**设计原则**：先简单，再迭代。复杂方案需要明确的触发条件。

### 决策 7：天气 API — 和风天气 7d 预报

**MVP 范围**：只接 `GET /v7/weather/7d`，根据 `date` 参数找到对应日期的天气预报。

**实现要点**：
- 使用 JWT 认证（需要 Python 生成 Ed25519 签名的 JWT）
- 依赖：`PyJWT` + `cryptography`
- JWT 有有效期，需要缓存 + 过期自动刷新

**其余 API**（分钟降水、空气质量等）作为后续增强，不在 Step 7 范围内。

---

## 当前已完成功能（截至 Step 6）

### API 端点

| 端点 | 方法 | Agent | 状态 |
|------|------|-------|------|
| `/api/v1/health` | GET | - | ✅ |
| `/api/v1/trips` | POST | itinerary_gen → route_optimizer | ✅ |
| `/api/v1/trips` | GET | - | ✅ |
| `/api/v1/trips/{id}` | GET | - | ✅ |
| `/api/v1/sources/parse` | POST | guide_parser | ✅ |
| `/api/v1/facts/check` | POST | fact_checker | ✅ |
| `/api/v1/chat` | POST | Supervisor → 4 个子 Agent | ✅ |

### Agent 编排模式

| 模式 | 实现位置 | 说明 |
|------|---------|------|
| 链式调用 | `services/itinerary.py` | itinerary_gen → route_optimizer 硬编码顺序 |
| Supervisor | `agents/supervisor.py` | LLM 动态路由到子 Agent |

---

## 未完成和后续计划

### Step 7：工具升级（本次）

| 阶段 | 工具 | API | 状态 |
|------|------|-----|------|
| 7.1 | `geocode_poi` | 高德地理编码 | 待实现 |
| 7.2 | `get_travel_time` | 高德路径规划 | 待实现 |
| 7.3 | `search_attractions` | 高德 POI 搜索 | 待实现 |
| 7.4 | `get_opening_hours` | 高德 POI 详情 | 待实现 |
| 7.5 | `get_weather` | 和风天气 7d 预报 | 待实现 |
| 7.6 | `optimize_itinerary` | 升级为真实路径排序 | 待实现（Step 5 顺延） |

### Step 8+：增强功能

- 向量数据库 POI 语义搜索
- 版本快照（DB Snapshot 表）
- 分钟降水、空气质量 API 接入
- 前端 React Vite 应用
- 用户认证

---

## 新增概念

| 概念 | 解释 |
|------|------|
| **降级兜底** (Graceful Degradation) | API 不可用时自动切换到备用方案，而不是让系统崩溃 |
| **Tool 内部闭环** | 确定性流程（如"查坐标→算距离"）封装在 Tool 内部，不让 LLM 参与编排 |

## 新增设计原则

1. **能确定做的事情，就不要让 LLM 来做** — 确定性逻辑留在代码，AI 只做不确定性判断
2. **先简单，再迭代** — 优先选最简单方案，验证可行后按需升级。复杂方案需要明确的触发条件
3. **接口不变，底层可换** — Tool 签名是 Agent 间的"合同"，内部实现从 mock 换到高德，上下游不动
