# Step 7：工具升级 — Mock → 真实 API

## 概述

**日期**：2026-05-20
**阶段**：全部完成（7.1-7.6 ✅）
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
| 7.1 | `geocode_poi` | 高德地理编码 | ✅ 已完成 |
| 7.2 | `get_travel_time` | 高德路径规划 | ✅ 已完成 |
| 7.3 | `search_attractions` | 高德 POI 搜索 | ✅ 已完成 |
| 7.4 | `get_opening_hours` | 高德 POI 搜索 biz_ext | ✅ 已完成 |
| 7.5 | `get_weather` | 和风天气 7d 预报 | ✅ 已完成 |
| 7.6 | `optimize_itinerary` | 升级为真实路径排序 | ✅ 已完成 |

### Step 8+：增强功能

- 向量数据库 POI 语义搜索
- 版本快照（DB Snapshot 表）
- 分钟降水、空气质量 API 接入
- 前端 React Vite 应用
- 用户认证

---

## 7.1 geocode_poi → 高德地理编码 API（✅ 已完成）

### 实现

```python
def geocode_poi(name: str, city: str = "") -> dict:
    if settings.amap_api_key:
        try:
            result = _geocode_amap(name, city)   # 真实 API
            if result:
                return result
        except Exception:
            logger.warning("高德地理编码失败，降级到 mock", exc_info=True)
    return _geocode_mock(name)                    # 降级兜底
```

**API 端点**：`GET https://restapi.amap.com/v3/geocode/geo`
**关键细节**：高德返回 `"location": "lng,lat"`（经度在前），需 `.split(",")` 后对调。
**city 参数的必要性**：不传 city → "西湖"可能返回南昌西湖而非杭州西湖。传了 city 结果精确。

### 验证方式

```powershell
cd src/backend
.venv/Scripts/python -c "from app.agents.tools.geo import geocode_poi; print(geocode_poi('故宫','北京'))"
# → {'name': '故宫', 'lat': 39.917839, 'lng': 116.397029}  ✅

print(geocode_poi('西湖','杭州'))
# → {'name': '西湖', 'lat': 30.259242, 'lng': 120.130396}  ✅

print(geocode_poi('火星基地'))
# → 自动降级 mock（hash 估算坐标）
```

### 测试策略

开发阶段只跑最小验证（当前工具 + 直接依赖的测试），不等全量：

```powershell
.venv/Scripts/python -m pytest tests/test_route_optimizer.py tests/test_guide_parser.py -v
```

全量测试留在整个 Step 7 完成后再跑。

---

## 7.2 get_travel_time → 高德路径规划 API（✅ 已完成）

### 设计要点

**Tool 内部闭环**：`get_travel_time` 内部自己做 geocode（调 `geocode_poi`）→ 路径规划（调高德 Direction API），Agent 只看到一个 Tool 调用。这是**决策 5**的落地——"能确定做的事情，就不要让 LLM 来做"。

**签名变更**：`get_travel_time(from_poi, to_poi, mode)` → `get_travel_time(from_poi, to_poi, mode, city="")`

加 `city` 参数的原因：
- 公交 API 强制要求 `city` 参数
- 内部 geocode 传 city 结果更精确（同名歧义问题）
- 默认空字符串，向后兼容

### 交通方式 → API 端点映射

| mode | 高德端点 | 说明 |
|------|---------|------|
| `walking` | `/v3/direction/walking` | 步行路径 |
| `taxi` | `/v3/direction/driving` | 打车走机动车道，等同于驾车 |
| `transit` | `/v3/direction/transit/integrated` | 公交/地铁换乘方案，**必须传 city** |

### 实现

```python
def get_travel_time(from_poi: str, to_poi: str, mode: str = "walking", city: str = "") -> int:
    if settings.amap_api_key:
        try:
            result = _travel_time_amap(from_poi, to_poi, mode, city)
            if result is not None:
                return result
        except Exception:
            logger.warning("高德路径规划失败，降级到 mock", exc_info=True)
    return _travel_time_mock(from_poi, to_poi, mode)


def _travel_time_amap(from_poi, to_poi, mode, city) -> int | None:
    # 第一步：地理编码两个 POI
    origin = geocode_poi(from_poi, city)
    dest = geocode_poi(to_poi, city)
    origin_str = f"{origin['lng']},{origin['lat']}"    # 高德格式：lng,lat
    dest_str = f"{dest['lng']},{dest['lat']}"

    # 第二步：选择端点 + 发请求
    url = _MODE_TO_AMAP_URL.get(mode) or AMAP_WALKING_URL
    params = {"key": ..., "origin": origin_str, "destination": dest_str}
    if mode == "transit":
        params["city"] = city or "北京"

    # 第三步：提取耗时（秒 → 分钟，向上取整）
    duration_sec = int(_extract_duration(data, mode))
    return math.ceil(duration_sec / 60)
```

### 踩坑：高德返回的 duration 是字符串

高德 API 返回的 `duration` 字段是**字符串**类型（如 `"900"` 表示 900 秒），不是整数。需要显式 `int()` 转换，否则 `<= 0` 比较会报 `TypeError`。

**原因**：高德 API 的 JSON 响应中，数字字段可能以字符串形式返回（这是很多中文 API 的常见做法）。

**教训**：对接新 API 时，不要假设字段类型——总是做显式转换。

### 验证方式

```powershell
cd src/backend
.venv/Scripts/python -c "from app.agents.tools.attractions import get_travel_time; print(get_travel_time('灵隐寺','西湖','walking','杭州'))"
# → 64 min  ✅（真实步行距离约 3.8km）

print(get_travel_time('天安门','故宫','walking','北京'))
# → 15 min  ✅（真实步行距离约 1km）

print(get_travel_time('外滩','迪士尼','taxi','上海'))
# → 44 min  ✅（真实驾车约 40-50 分钟）

print(get_travel_time('灵隐寺','西湖','transit','杭州'))
# → 42 min  ✅（公交+步行换乘）

print(get_travel_time('火星基地','月球站'))
# → 15 min  ✅（自动降级 mock）
```

### 对比：Mock vs 真实 API

| POI 对 | Mock 估算 | 真实 API | 差异 |
|--------|----------|---------|------|
| 天安门→故宫 | 10 min | 15 min | +50% |
| 外滩→迪士尼 taxi | 19 min | 44 min | +132% |

Mock 数据严重低估了实际通勤时间（如从外滩到迪士尼），真实 API 数据基于路网距离和交通状况，更可靠。

---

## 7.3 search_attractions → 高德 POI 搜索 API（✅ 已完成）

### 设计要点

**A 方案落地**（决策 6）：`preference` 直接透传给高德 `keywords` 参数。不引入 `types` 分类码映射。

```
preference="自然风光" → keywords="自然风光"
preference=""        → keywords="景点"
destination="杭州"   → city="杭州"
```

**为什么先 A**：简单方案能验证流程。如果后续发现 keywords 匹配不精准（如搜"自然风光"返回了"自然风光摄影店"），再升级为 B 方案（preference → types 码）。

### API 映射

| 工具参数 | 高德 API 参数 | 说明 |
|---------|-------------|------|
| `destination` | `city` | 城市名，限定搜索范围 |
| `preference` | `keywords` | 搜索关键词，空时默认搜"景点" |
| - | `offset=20` | 每页 20 条（最大 25） |
| - | `extensions=all` | 返回扩展信息（评分、照片等） |

### 输出格式变化

由于高德 API 不提供游玩时长（`duration_h`），真实 API 输出中时长统一标注为 `建议2h`：

```
# Mock 输出（旧）
1. 西湖 | 自然风光 | 建议3h | 评分4.9

# 真实 API 输出（新）
1. 西湖风景名胜区-断桥残雪 | 风景名胜 | 建议2h | 暂无评分
```

**注意**：评分字段在有数据时正常显示（如 `评分4.5`），但部分 POI 高德未返回评分时显示"暂无评分"。

### 实现

```python
def search_attractions(destination: str, preference: str = "") -> str:
    if settings.amap_api_key:
        try:
            result = _search_attractions_amap(destination, preference)
            if result:
                return result
        except Exception:
            logger.warning("高德 POI 搜索失败，降级到 mock", exc_info=True)
    return _search_attractions_mock(destination, preference)
```

### 关键收益

**新城市立即可用**：Mock 只覆盖 3 个城市（杭州/北京/上海），真实 API 覆盖全国任何城市。搜"成都"、"西安"、"三亚"都能立刻返回结果。

---

## 7.4 get_opening_hours → 高德 POI 搜索 biz_ext（✅ 已完成）

### 设计要点

**关键发现**：高德免费 API 的"POI 详情/ID 查询"接口**不返回营业时间**。但 POI 关键字搜索配合 `extensions=all`，会在 `biz_ext` 深度信息中返回 `opentime2`（详细开放时间）。

```
get_opening_hours("故宫", "2026-06-01")
  ├── geocode_poi("故宫") → 获取城市上下文
  ├── 高德 /v3/place/text?keywords=故宫&extensions=all&city=北京
  ├── 名称匹配校验（best_match_poi，防止误匹配）
  ├── 提取 biz_ext.opentime2 + biz_ext.rating
  └── 格式化为："故宫博物院；开放时间：04/01-10/31 周二-周日 08:30-17:00...；评分：4.9；查询日期：2026-06-01"
```

### API 数据来源

| 字段 | 高德字段路径 | 说明 |
|------|------------|------|
| 开放时间 | `pois[0].biz_ext.opentime2` | 包含淡旺季、周末/工作日、特殊日期的完整规则 |
| 评分 | `pois[0].biz_ext.rating` | 如 `"4.9"`，可能为空 |
| 票价 | `pois[0].biz_ext.cost` | 如 `"60"`，格式因 POI 类型而异 |

### 名称匹配防误匹配

不加校验时，"火星基地"会被匹配到某个含"星"字的真实 POI。

**解决方案**：双向子串匹配——查询名和结果名必须有包含关系（score≥2），单字重叠不算。

```python
def _name_match_score(query: str, result: str) -> int:
    # 2=包含关系（"故宫" ⊂ "故宫博物院"）
    # 1=单字重叠（"火星基地" ∩ "星乐园" = {"星"}）
    # 0=完全不匹配
```

阈值设为 `score >= 2`，"火星基地"→降级 mock ✅，"故宫"→真实数据 ✅。

### 验证方式

```powershell
.venv/Scripts/python -c "from app.agents.tools.opening_hours import get_opening_hours; print(get_opening_hours('故宫','2026-06-01'))"
# → 故宫博物院；开放时间：04/01-10/31 周二-周日 08:30-17:00... 11/01-03/31 ... 周一全天不开放...；评分：4.9 ✅

print(get_opening_hours('西湖','2026-05-01'))
# → 杭州西湖风景名胜区；开放时间：周一-周日 00:00-24:00（24h开放）；评分：4.9 ✅

print(get_opening_hours('灵隐寺','2026-06-15'))
# → 灵隐寺；开放时间：周一-周日 07:30-18:00 停止入园17:30；评分：4.9 ✅

print(get_opening_hours('火星基地','2026-06-01'))
# → 火星基地：2026-06-01 开放时间 08:30-17:00...，门票 60 元 ✅（降级 mock）
```

### 局限

- 高德免费 API 不提供"当日是否可预约"信息——原 mock 中的"当日可预约"无法从 API 获取
- `biz_ext.cost` 字段格式不统一（故宫为空列表，其他 POI 可能是数字），当前未在输出中展示票价
- 日期参数暂未用于筛选特定日期的开放规则，输出包含全部规则文本由 LLM 自行解读

---

## 7.5 get_weather → 和风天气 7d 预报 API（✅ 已完成）

### 设计要点

**City 映射**：复用 `geocode_poi` 获取坐标 → 传和风天气（B 方案）。不引入和风 GeoAPI 依赖。

**JWT 认证**：和风天气使用 Ed25519 签名的 JWT Bearer Token。

| 配置项 | .env 字段 | 说明 |
|--------|----------|------|
| Project ID | `QWEATHER_PROJECT_ID` | JWT payload 的 `sub` |
| Key ID | `QWEATHER_KEY_ID` | JWT header 的 `kid` |
| Private Key | `QWEATHER_PRIVATE_KEY` | Base64 DER 格式 Ed25519 私钥 |
| API Host | `QWEATHER_API_HOST` | 专属 API 域名 |

**JWT 缓存**：模块级变量缓存，1h 有效期，过期前 60s 自动刷新。

**坐标精度**：和风天气要求经纬度最多 2 位小数，代码中 `f"{lng:.2f},{lat:.2f}"` 截断。

**日期匹配**：和风返回未来 7 天数据。查询日期超出范围时 `_find_day` 返回 None → 自动降级 mock。

### 实现

```python
def _weather_qweather(city, date) -> str | None:
    geo = geocode_poi(city)
    location = f"{geo['lng']:.2f},{geo['lat']:.2f}"
    token = _get_jwt_token()  # EdDSA JWT, 缓存 1h
    resp = requests.get(f"https://{host}/v7/weather/7d",
                        params={"location": location},
                        headers={"Authorization": f"Bearer {token}"})
    target = _find_day(data["daily"], date)
    return _format_weather(city, date, target)
```

### 踩坑：JWT 401 排查

JWT 自验证通过（签名正确），但和风返回 401。排查 6 种密钥格式均失败后，**最终原因**是 `.env` 中 `QWEATHER_KEY_ID` 过期——用户在和风控制台更新凭据后 Key ID 从 `KEWGFFVW2K` 变为 `KBB6CBGYWH`。

**教训**：JWT 自验证通过只证明"私钥与公钥配对"，不能证明"公钥 = 服务端注册的公钥"。

### 输出格式

```
北京 2026-05-20：晴，16°C ~ 25°C，东风 1-3级，适合出行
杭州 2026-05-24：小雨，21°C ~ 26°C，东风 1-3级，建议带伞
```

出行建议：含"雨"→带伞 / >35°C→防暑 / <5°C→保暖 / 大风≥6级→注意安全 / 否则→适合出行。

### 依赖

```
pip install pyjwt cryptography
```

---

## 7.6 optimize_itinerary → 高德路径规划真实排序（✅ 已完成）

### 概述

将 `optimize_itinerary` 从"只填坐标"升级为"地理编码 + 路径规划 + POI 重排序 + 交通时间填充"的完整路线优化工具。

### 核心设计

**混合交通方式**：每对 POI 按 Haversine 距离自动选择 walking（< 1.5km）或 transit（≥ 1.5km）。高德 transit/integrated 端点本身包含步行段，无需单独处理。

**贪心最近邻排序**：每日 POI 中，第一个（Agent 选择的起点）固定不动，后续 POI 按最近邻贪心重排。

**geocode_poi 增强**：返回 dict 新增 `city` 字段（高德地理编码 API 响应中原有的数据），供 transit API 的必填 `city` 参数使用。向后兼容（现有调用方只取 `lat`/`lng` 不受影响）。

**降级策略**：任一 Direction API 调用失败 → 该日整体降级，保持 Agent 原始顺序 + Haversine 距离估算 travel_minutes_from_prev。

### 新增函数

`route_optimizer.py` 新增 9 个模块私有函数：

| 函数 | 职责 |
|------|------|
| `_select_mode(distance_m)` | <1500m → walking, ≥1500m → transit |
| `_haversine_distance(lat1, lng1, lat2, lng2)` | 球面距离（米） |
| `_amap_direction_direct(lng1, lat1, lng2, lat2, mode, city)` | 坐标直调高德 Direction API，返回分钟数 |
| `_extract_duration_direct(data, mode)` | 从 API 响应提取 duration（秒） |
| `_build_travel_time_matrix(items)` | 构建 N×(N-1) 有向旅行时间矩阵 |
| `_reorder_by_nearest_neighbor(items, matrix)` | 贪心最近邻重排，items[0] 固定 |
| `_fill_travel_times_from_matrix(items, matrix, index_map)` | 真实矩阵数据回填 travel_minutes_from_prev |
| `_estimate_travel_minutes_from_distance(distance_m)` | Haversine 距离 → 估算分钟 |
| `_fill_travel_times_fallback(items)` | 降级路径：保持原始顺序 + Haversine 估算 |

### API 消耗

5 POI/日 × 4 = 20 次/日，3 日行程 = 60 次/月。高德免费额度 15 万次/月（geocode+direction 共享），绰绰有余。

### 测试结果

20 个测试全部通过（3 个旧 + 17 个新）。

### 局限性

- `geocode_poi` 不传 `city` 参数时，Amap 对部分 POI（如"灵隐寺"）可能返回错误城市的同名地点。需要 Agent 或上层传入城市上下文来改善。
- 贪心最近邻不保证全局最优路径，但对 3-5 个 POI 的日常行程影响可忽略。
- transit 模式依赖 `city` 字段。若 geocode 返回空 city（mock 降级场景）且距离 ≥ 1.5km，当前实现会因缺少 city 而返回 None → 触发降级。

---

## API 参考速查

### 高德地理编码 API（7.1）

```
GET https://restapi.amap.com/v3/geocode/geo
参数：key, address（POI 名）, city（可选）
返回：{"status": "1", "geocodes": [{"location": "lng,lat"}]}
注意：location 格式为 "经度,纬度"（lng 在前）
```

### 高德路径规划 API（7.2）

| 交通方式 | 端点 | 必填参数 | 返回路径 |
|---------|------|---------|---------|
| 步行 | `GET /v3/direction/walking` | key, origin, destination | `route.paths[0].duration`（秒） |
| 驾车 | `GET /v3/direction/driving` | key, origin, destination | `route.paths[0].duration`（秒） |
| 公交 | `GET /v3/direction/transit/integrated` | key, origin, destination, **city** | `route.transits[0].duration`（秒） |

- origin/destination 格式：`"lng,lat"`（经度在前，与 geocode 返回一致）
- **duration 是字符串类型**，需要 `int()` 转换
- 公交 API 的 `city` 是必填参数（城市名或 citycode）
- 驾车 API 可选 `strategy`（0-20，10=默认躲避拥堵）

### 高德 POI 搜索 API（7.3）

```
GET https://restapi.amap.com/v3/place/text
参数：key, keywords（搜索关键词）, city（城市名）, offset（每页条数，默认20，最大25）, extensions=all
返回：{"status": "1", "count": "20", "pois": [{"name": "POI名", "type": "大类;中类;小类", "address": "地址", "location": "lng,lat", "rating": "4.5"}]}
注意：type 字段用 ";" 分隔三级分类，取第一段为分类名；rating 可能为空
```

### 高德 POI 深度信息 — biz_ext（7.4）

使用 POI 关键字搜索时传 `extensions=all`，返回的 `pois[].biz_ext` 包含：

| 字段 | 说明 | 示例 |
|------|------|------|
| `opentime2` | 详细开放时间（淡旺季、节假日规则） | `"04/01-10/31 周二-周日 08:30-17:00..."` |
| `rating` | 评分 | `"4.9"` |
| `cost` | 票价/人均消费 | `"60"` 或 `[]`（空表示无数据） |

注意：`biz_ext` 仅部分 POI 类型返回，且字段值可能为空列表

### 和风天气 7d 预报 API（7.5）

```
GET https://{host}/v7/weather/7d?location=lng,lat
Header: Authorization: Bearer {JWT_Token}
参数：location（经纬度 lng,lat，最多 2 位小数）
返回：{"code": "200", "daily": [{"fxDate": "2026-05-20", "tempMax": "25", "tempMin": "16", "textDay": "晴", "windDirDay": "东风", "windScaleDay": "1-3", ...}]}
```

JWT 生成要点：
- Header: `{"alg": "EdDSA", "kid": "KEY_ID"}`（不要 `typ` 字段）
- Payload: `{"sub": "PROJECT_ID", "iat": now-30, "exp": now+900}`
- 密钥：Ed25519 PKCS#8 PEM 格式
- 依赖：`pyjwt` + `cryptography`；POI 详情/ID 查询 API 不返回营业时间

---

## 新增概念

| 概念 | 解释 |
|------|------|
| **降级兜底** (Graceful Degradation) | API 不可用时自动切换到备用方案，而不是让系统崩溃 |
| **Tool 内部闭环** | 确定性流程（如"查坐标→算距离"）封装在 Tool 内部，不让 LLM 参与编排 |
| **API 响应格式转换** | 第三方 API 返回的格式不一定是你要的——高德坐标是 `"lng,lat"`，你的系统可能需要 `{lat, lng}`，中间必须做转换 |
| **同名歧义问题** | 同一个 POI 名在不同城市可能指向不同地点（如全国有多个"西湖"），传城市参数可以消除歧义 |
| **API 字段类型不可信** | 第三方 API 返回的数字可能是字符串类型（如高德 duration 返回 `"900"` 而非 `900`），必须显式转换，不要假设类型 |
| **公交路径规划的 city 约束** | 高德公交路径规划 API 要求必传 `city` 参数——这是 API 级别的硬约束，不是代码设计的选择 |

## 新增设计原则

1. **能确定做的事情，就不要让 LLM 来做** — 确定性逻辑留在代码，AI 只做不确定性判断
2. **先简单，再迭代** — 优先选最简单方案，验证可行后按需升级。复杂方案需要明确的触发条件
3. **接口不变，底层可换** — Tool 签名是 Agent 间的"合同"，内部实现从 mock 换到高德，上下游不动

## 经验教训

### 测试策略：开发阶段最小化

- **不**每完成一个小功能就跑全量测试（Step 7.1 只有 `geocode_poi` 一个函数改动，全量跑 22 个测试耗时 12 分钟，毫无必要）
- **要**只跑当前工具直接相关的测试（`test_route_optimizer` + `test_guide_parser`，8 秒）
- 全量测试留给整个 Step 7 阶段完成后做一次最终验证

### API 对接：永远不要假设字段类型

- 高德 Direction API 返回的 `duration` 是**字符串**（如 `"900"`），不是整数
- 直接对字符串做 `<= 0` 比较会抛 `TypeError`
- **教训**：对接新 API 时，对每个数值字段做显式 `int()` 或 `float()` 转换，即使文档说它是数字
