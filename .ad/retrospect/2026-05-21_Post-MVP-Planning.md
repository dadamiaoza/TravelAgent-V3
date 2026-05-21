# Post-MVP 需求分析与后续规划

**日期**：2026-05-20
**状态**：需求分析完成，待排期实施
**背景**：Step 1-7 全部完成，MVP 全链路跑通。讨论下一阶段方向。

---

## MVP 完成清单

| 阶段 | 内容 | 状态 |
|------|------|------|
| S0 | 脚手架（Docker + DB + 健康检查） | ✅ |
| S1 | 最小闭环（手动输入 → 生成行程） | ✅ |
| S2 | 节点编辑 + 版本快照 | ✅ |
| S3 | 文本/链接攻略导入与解析 | ✅ |
| S4 | 路线优化（geocode + 坐标填充） | ✅ |
| S5 | 时效刷新 + 风险标签 | ✅ |
| S6 | Supervisor 多 Agent 编排 | ✅ |
| Step 7.1-7.5 | 5 个工具 Mock → 真实 API | ✅ |
| Step 7.6 | 路线优化 → 真实路径排序 | ✅ |

---

## 三个扩展方向

### 方向一：外部集成 — 搜索 + 抓取

**目标**：用户不再需要手动粘贴攻略文本，一句话就能触发搜索和抓取。

**方案**：

```
用户："帮我搜杭州三天两夜攻略"
  → LLM 调 Tavily MCP 搜索
  → 返回链接列表给用户确认
  → LLM 调 Firecrawl MCP 抓取网页 → Markdown
  → guide_parser 解析 → 候选 POI 列表
```

**接入方式**：MCP（Model Context Protocol）而非直接 API。原因：
- 搜索和抓取是"LLM 自主决策"的场景（搜什么关键词、抓哪个链接）
- MCP 让 LLM 自行发现和调用这些工具，不需要写 Tool 代码
- 与现有高德/和风天气的直接 API 模式互补——确定性调用走 API，开放性探索走 MCP

**为什么不是直接调 API**：
- Tavily/Firecrawl 如果封装为 Tool 函数，调用时机的判断逻辑（"该搜了""该抓了"）需要写在代码里
- MCP 接入后，Supervisor 自动发现这些能力，LLM 自行决定何时调用——更灵活
- **原则**：确定性逻辑留在代码（直接 API），不确定性决策交给 Agent（MCP）

---

### 方向二："抄作业"功能增强

**目标**：不只提取 POI 名称，而是把攻略里的所有有用信息结构化。

**当前 guide_parser 输出**：`["西湖", "灵隐寺", "雷峰塔"]`（只有名称列表）

**可提取的更多信息**：

| 攻略原文 | 当前 | 增强 |
|---------|------|------|
| "建议游玩 3-4 小时" | 丢弃 | → `suggested_duration_h: 3.5` |
| "一定要早上去，人少" | 丢弃 | → `best_time: "morning"` |
| "门票 60，学生半价" | 丢弃 | → `cost_estimate: 60` |
| "地铁 1 号线到龙翔桥站" | 丢弃 | → `transport_tip: "地铁1号线龙翔桥站"` |
| "附近有家知味观必吃" | 丢弃 | → `nearby_food: "知味观"` |
| "穿舒服的鞋，要走很多路" | 丢弃 | → `notes: "需大量步行，穿舒适鞋"` |

**实施**：纯 prompt 改动，不改代码架构。guide_parser 的 system_prompt 增加字段要求即可。

**多源合并去重**（需写代码）：

```
攻略A: ["西湖", "灵隐寺", "雷峰塔"]
攻略B: ["西湖", "断桥", "灵隐寺"]
攻略C: ["西湖", "九溪十八涧"]

合并去重后:
  - 西湖（3 篇攻略提到，高置信度）
  - 灵隐寺（2 篇提到）
  - 雷峰塔（1 篇提到）
  - 断桥（1 篇提到）
  - 九溪十八涧（1 篇提到）
  按提及次数降序展示
```

**源归属追踪**（需改 DB）：

在 `ItineraryItem` 加 `source` 字段，每个 POI 标注"来自攻略A（小红书@xxx）"。方便用户回溯原文确认细节。

---

### 方向三：记忆与状态分离

**核心问题**：当前 Agent 的 PostgresSaver 存的是**完整消息历史**——过程记录和任务状态混在一起。Agent 要"记住不要重复选景点"时，只能读历史消息文本推断，上下文越来越脏。

**核心原则**（引用自 knowledge-map.md）：

> 记忆和状态不要混用。记忆更像历史对话，状态更像当前任务摘要；如果什么都往 memory 里塞，后面上下文会越来越脏，也更难控制。

**当前 Level**：Level 1 — Memory = 完整消息列表（`{"messages": [...]}`）

**目标 Level**：Level 2 — Memory = 消息列表（经修剪） + 结构化摘要字段

**推荐架构：双通道**：

```
Agent 拿到的上下文 = 短期记忆 + 结构化状态

短期记忆（PostgresSaver）
  → 最近 N 轮消息
  → 旧消息自动替换为 LLM 摘要

结构化状态（注入 system_prompt）
  → 已规划 POI 集合
  → 剩余天数
  → 预算范围
  → 上次用户操作
```

**实施分两步**：

**第一步（可立即做）**：结构化状态注入

修改 `services/itinerary.py`，每次调 Agent 前从 DB 读取当前行程状态，拼入 system_prompt：

```python
def _build_prompt(trip: Trip, existing_items: list) -> str:
    planned = [item.poi_name for item in existing_items]
    return (
        f"目的地：{trip.destination}，日期：{trip.start_date} ~ {trip.end_date}，"
        f"{trip.people_count}人，预算 {trip.budget_min}-{trip.budget_max} 元。\n"
        f"已规划景点：{', '.join(planned) or '暂无'}（请勿重复选择）。\n"
    )
```

**第二步（需开发）**：上下文修剪中间件

Agent 调用前检查消息数量，超过阈值（如 20 条）时自动修剪：

```python
# 伪代码
if len(messages) > MAX_RECENT:
    old = messages[:-MAX_RECENT]
    recent = messages[-MAX_RECENT:]
    summary = llm.invoke("请用一段话摘要以下对话内容：", old)
    messages = [SystemMessage(f"[历史摘要] {summary}")] + recent
```

**第三步（远期）**：用户画像

跨行程偏好存独立表（`user_profile`），行程规划时自动注入偏好。需要先有用户系统。

---

## 推荐优先级

```
高优先级（立即可做，改动小，体验提升大）
├── 结构化状态注入 system_prompt    ← 解决"记忆脏"问题
├── guide_parser 输出增强           ← "抄作业"提取更多细节
└── 上下文修剪中间件                ← 防止 token 膨胀

中优先级（需一定开发量）
├── Tavily + Firecrawl MCP 接入    ← 搜索+抓取全自动
└── 多源合并去重                    ← 多篇攻略交叉验证

低优先级（锦上添花 / 依赖其他模块）
├── 源归属追踪（需改 DB schema）
├── 用户画像（需用户系统）
└── 图片攻略解析（需多模态 LLM）
```

---

## 附录：Step 7.6 路线优化技术细节

> 从 `knowledge-map.md` §11 移入。记录贪心排序、Haversine 距离、交通方式选择、矩阵构建、降级策略的具体实现逻辑。

### 贪心最近邻（Greedy Nearest-Neighbor）

一种 TSP（旅行商问题）的贪心算法：从起点开始，每次都去"下一个最近的未访问 POI"，直到遍历完所有 POI。

```
3 POI 示例：
  灵隐寺(起点固定) → 西湖(10min) vs 雷峰塔(50min) → 选西湖
  西湖 → 雷峰塔(20min) → 选雷峰塔
  最终顺序：灵隐寺 → 西湖 → 雷峰塔
```

- **为什么不用 LLM**：路径排序是纯计算问题（给定坐标和旅行时间，找最优顺序），不涉及语义判断。LLM 可能算错距离、给不一致的结果、浪费 token。
- **为什么贪心而非最优 TSP**：每日 3-5 个 POI，贪心近似度很高。最优 TSP（Held-Karp）复杂度 O(N²·2^N)，引入不必要的复杂度。
- **为什么固定起点**：Agent 选第一个 POI 是有意图的（如"早晨先去灵隐寺避开人流"），重排时应尊重这个决策。

### Haversine 球面距离

用经纬度计算地球表面两点间的大圆距离的数学公式：

```python
from math import radians, sin, cos, atan2, sqrt

R = 6371000  # 地球半径（米）
phi1, phi2 = radians(lat1), radians(lat2)
dphi = radians(lat2 - lat1)
dlambda = radians(lng2 - lng1)
a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
c = 2 * atan2(sqrt(a), sqrt(1 - a))
distance = R * c  # 米
```

**两种用途**：
1. **API 调用前**：快速判断 POI 间距 → 决定用 walking（<1.5km）还是 transit（≥1.5km）
2. **降级估算**：API 不可用时估算旅行时间（walking 5km/h → 1m ≈ 83m, transit 20km/h → 1m ≈ 333m）

### 按距离自动选择交通方式

```
Haversine(灵隐寺, 西湖) = 3.8km → ≥1500m → transit
Haversine(西湖, 雷峰塔) = 1.0km → <1500m → walking
```

- 全用 walking：跨城 POI 会算出 2 小时步行路线，不符合实际
- 全用 transit：500m 短距离也返回公交方案（含步行到站+等车），不如直接步行
- 1.5km 分界线 ≈ 步行约 18 分钟，是合理的步行/公交切换点
- 高德 transit/integrated 端点本身包含步行段（走到站+换乘），无需额外处理

### 有向旅行时间矩阵

N 个 POI 两两之间的旅行时间构成的 N×(N-1) 矩阵，key 为 `(from_index, to_index)` 原始索引。

**为什么是"有向"**：A→B 和 B→A 的公交方案可能不同（单行道、公交线路方向）。对于 walking 近似对称，但对 transit 有意义。

**为什么用原始索引**：同一日程可能有同名 POI（如"西湖"出现两次），用名称 key 会冲突。用索引唯一且稳定。

**all-or-nothing 降级策略**：任一 API 调用失败 → 该日整体降级到 Haversine 估算，避免"3 对真实数据 + 2 对估算数据"混在一起污染排序结果。

### geocode_poi 返回 city 字段

**为什么需要**：高德 transit API 的 `city` 参数是必填项。地理编码 API 的响应中原有 `city` 字段，之前被丢弃了。

**向后兼容**：`geocode_poi` 返回 dict 新增 `city` 键，已有调用方只取 `lat`/`lng` 不受影响。`optimize_itinerary` 在输出前移除 `city`（内部字段不暴露）。

### 完整数据流

```
optimize_itinerary(行程JSON)
  for each day:
    1. geocode_poi 所有item → 填 lat/lng/city
    2. 有Key → 构建旅行时间矩阵
       for each pair (i→j, i≠j):
         dist = Haversine(coord_i, coord_j)
         mode = dist < 1500 ? "walking" : "transit"
         city = items[j]["city"]
         matrix[(i,j)] = 高德DirectionAPI(coord_i, coord_j, mode, city)
       失败 → 降级
    3. 排序: 贪心最近邻(items, matrix), items[0]固定
    4. 填充: travel_minutes_from_prev ← matrix真实值
    5. 降级: 保序 + Haversine估算
    6. 更新seq, 移除city
  return JSON
```

### API 消耗估算

| 场景 | 每日 POI | 调用数/日 | 3 日行程总调用 |
|------|----------|----------|--------------|
| 少量景点 | 3 | 6 (3×2) | 18 |
| 正常行程 | 5 | 20 (5×4) | 60 |
| 密集行程 | 8 | 56 (8×7) | 168 |

高德免费额度 15 万次/月，正常使用绰绰有余。

---

## 相关文档

- `knowledge-map.md` §11 — 路线优化概念速查（精简版）
- `knowledge-map.md` §12 — 记忆架构与外部集成速查（精简版）
- `CONTEXT.md` — 领域术语表（含新增术语）
- `docs/decisions.md` — 决策 #11-15 记录
- `2026-05-20_Step7-Tool-Upgrade-Mock-to-API.md` — Step 7.1-7.6 实现记录
- `2026-05-17_Memory-State-Deep-Dive.md` — Memory/State 深度学习记录
