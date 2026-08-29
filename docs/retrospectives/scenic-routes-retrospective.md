# 城市 / 景区双模式路线规划复盘

> 本文档记录 `feat/city-scenic-routes` 分支中遇到的实际问题、调研结论、方案取舍和测试结果。
> 目标：后续继续开发时能快速理解“为什么景区内不能调用高德索道/接驳车路线，以及当前是怎么降级表达的”。

## 1. 核心问题：高德有没有景区内部路线规划能力？

### 调研结论
- 高德 Web服务 API 的路径规划主要支持：
  - 驾车
  - 骑行
  - 步行
  - 公交/地铁
- **没有**公开的“景区内路线规划 API”
- **没有**独立的“索道路线 API”
- **没有**独立的“景区接驳车路线 API”

### 为什么不能“假装能做”
- 如果调用高德步行 API 并声称返回的是索道/接驳车路线，属于虚构能力。
- 景区内部交通往往依赖现场指引、临时班次、季节调整，外部 API 无法保证。
- 产品原则：**宁可不画，也不画错；不给用户“已验证”的错觉。**

### 最终方向
- 按天区分两种模式：
  - `city`：城市常规路线
  - `scenic`：景区内部路线
- 景区内部：
  - 用 POI 搜索定位景点/索道站/接驳站
  - 用高德步行，必要时驾车连接这些点
  - 索道、接驳车、登山步道等只在业务层标注交通方式
  - 无法核实的路段只给建议，并提示以景区现场指引/官方班次为准

---

## 2. 数据模型设计

### 新增字段

| 表 | 字段 | 说明 |
|---|---|---|
| `itinerary_days` | `route_type` | `city` / `scenic`，按天划分 |
| `itinerary_items` | `route_verified` | 该段是否有可核实真实路线 |
| `itinerary_items` | `travel_advice` | 给游客的“以现场/官方为准”提示 |

### 为什么放在 Day 而不是 Trip
- 一趟行程可以混合城市日和景区日，例如：
  - Day 1 萍乡市区
  - Day 2 武功山景区
  - Day 3 返回市区/周边
- 按天控制路线策略比整趟行程更准确。

### 为什么索道/接驳车没有独立表
- 当前它们只是“两 POI 之间的一段交通方式”，本质是 `transport_mode` 的枚举值。
- 如果以后需要复杂班次/票价/时间表，再单独建模。

---

## 3. 路线优化层实现

### 交通方式选择

```text
城市模式：
  < 1500m  -> walking
  >= 1500m -> transit

景区模式：
  < 3000m  -> walking
  >= 3000m -> driving
```

- 景区模式**永远不会选 transit**
- 景区模式如果距离很远，允许用 driving，因为“必要时驾车”是合理需求

### 高德接口新增 driving 支持
- 原有 `_amap_direction_direct` 只支持 walking / transit
- 新增 `_AMAP_DRIVING_URL`
- 新增 driving 的 duration / polyline 提取
- 这样景区长距离段可以用真实驾车路径

### 景区业务层标注

- 优先读取 LLM / 用户显式给的 `transport_mode` 或 `suggested_transport`
- 如果没有显式值，根据前后 POI 名称推断：
  - 从“索道站/缆车站”出发去下一景点 → `cable_car`
  - 从“接驳站/观光车站”出发去下一景点 → `shuttle`
  - 包含“登山步道/栈道”等 → `hiking`
  - 否则回退到高德 API 的 `walking` / `driving`

### 无法核实的路段怎么表达

| 字段 | 值 | 含义 |
|---|---|---|
| `transport_mode` | `cable_car` / `shuttle` / `hiking` | 业务层标注 |
| `route_polyline` | `null` | 不画成真实道路 |
| `route_verified` | `false` | 明确未核实 |
| `travel_advice` | 中文提示 | 建议以现场/官方为准 |

---

## 4. 遇到的问题与解决过程

### 问题 1：景区内不能用公交，但原有逻辑只会选 walking/transit

- 原 `_select_mode(distance)` 对长距离一律返回 `transit`
- 这会导致武功山内部出现“公交/地铁 XX 分钟”，明显不真实

**解决**
- `_select_mode` 增加 `route_type` 参数
- 景区模式返回 `walking` / `driving`
- 所有矩阵构建、降级估算都透传 `route_type`

### 问题 2：高德没有索道/接驳车路线，不能生成 polyline

- 一开始考虑过用步行 API 中可能的 `walk_type` 特殊路段代替
- 后来确认不能依赖这种非公开/不稳定的字段来声称索道路线
- 如果给索道画一条“高德真实路线”，用户会误以为系统已核实

**解决**
- 索道/接驳车/登山步道统一 `route_polyline = null`
- 前端用虚线 + 低透明度表示“参考示意”
- 同时展示 `travel_advice` 提示

### 问题 3：重排后取错前后节点名称

- 路线优化会用贪心最近邻重排 POI
- 最初在景区标注逻辑里用 `items[orig_from]` / `items[orig_to]` 取前后 POI
- 但 `items` 已经被原地重排，原始索引不再对应新顺序

**解决**
- 改为使用 `items[i - 1]` / `items[i]`
- 这样取到的是“重排后的真实相邻节点”

### 问题 4：索道站名称容易误导“去车站”也被标成索道

- 如果把“山脚 → 金顶索道下站”也标成 `cable_car`，不符合实际
- 实际应该是“步行/驾车到索道站”，再“坐索道从站到山顶”

**解决**
- 方向性推断：
  - 上一节点是索道站、当前节点不是 → `cable_car`
  - 当前节点是索道站、上一节点不是 → 保持 walking/driving
- 接驳车同理

### 问题 5：LLM 不一定稳定输出 route_type

- 只靠 prompt 强制输出，可能存在漏标
- 如果漏标，景区日就会被当城市日处理

**解决**
- 路线优化层增加启发式：
  - POI 名称包含 `索道 / 接驳 / 观光车 / 登山步道 / 游步道 / 景区`
  - 自动推断为 `scenic`
- prompt 仍要求 LLM 显式输出，双层保障

### 问题 6：前端如何表达“未核实”

- 如果只是把 `route_polyline` 置空，前端会回退画直线，看起来仍然像真实路线

**解决**
- 前端根据 `day.route_type === "scenic"` 判断
- 未核实路段使用虚线、降低透明度
- 索道橙色、接驳车紫色、公交绿色，避免混淆
- 节点卡片显示 `travel_advice`

### 问题 7：数据库结构变更

- 需要持久化 `route_type`、`route_verified`、`travel_advice`
- 本地数据库原本处于 `0009`

**解决**
- 新增 `0010_add_scenic_route_type.py`
- 本地执行：
  ```text
  alembic upgrade head
  0009 -> 0010
  ```
- `route_type` 带 `server_default='city'`，旧数据默认城市模式

---

## 5. 测试结果

```text
pytest tests/test_route_optimizer.py
28 passed
```

新增覆盖：

1. 景区模式只调用 walking/driving，绝不调用 transit
2. 景区索道 fallback：
   - `transport_mode = cable_car`
   - `route_polyline = null`
   - `route_verified = false`
   - `travel_advice` 包含“现场/官方”
3. 景区无法核实的步行段也有通用提示

前端验证：

```text
npm run build
✓ built successfully
```

---

## 6. 当前边界与诚实说明

- 高德步行/驾车即使返回了 polyline，也不代表这条路线一定适合游客通行。
- 景区内部步道、索道、接驳车的实时运营情况无法由当前系统保证。
- 旧行程不会自动重算为景区模式，需要重新生成；migration 只给旧数据默认 `city`。
- `route_type` 目前由 LLM + 名称启发式自动判断，还没有“用户手动切换城市/景区模式”的 UI。
- 后续如果能接入景区官方导览/班次数据，可以再把“建议”升级为“可核实”。