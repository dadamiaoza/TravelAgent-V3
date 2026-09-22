# 路径排序：LLM 主排 + 近邻降级 + 高德计时

> 状态：已拍板，已实现
> 日期：2026-09-22
> 范围：GenerationJob 的 fill → route（verify 基本不动）

## 已拍板默认
1. 降级阈值：相对近邻基线总耗时 **+50%**（且绝对多出建议 ≥30 分钟）
2. 跨天首版：**只告警、不自动换点**
3. `respect_fill_order` / `respect_fill_order`：**默认 true**（生产默认开）

## 目标
1. 主路径：信任 fill 顺序（LLM / 候选），默认不再近邻覆盖
2. 降级：fill 无效或明显绕路时退回近邻（整日或只修异常边）
3. 计时与排序解耦：日程钟优先高德；LLM/攻略路段时间为旁证，高德失败时有限采纳
4. 跨天连续性：fill 约束 DayN 终点与 DayN+1 起点；route 只几何核验告警

## 实现要点
### fill
- 路径 A（selected_entities）：按 day_index/seq 拼装；有明确 A→B 路段分钟才写入估计字段 source=guide
- 路径 B（itinerary_gen）：允许 travel 估计（source=llm），不再强制全 0；要求跨天连续并可选 day_continuity_note
- 停留时长 suggested_duration_h 不要误当路段

### route
- 参数 respect_fill_order: bool = True
- True 时不调用近邻重排；按当前顺序 geocode + 高德逐段计时
- Sanity 失败则降级近邻；打标 order_source=fill|nearest_neighbor
- 保留 travel_amap_minutes / travel_estimate_* / travel_minutes（采用值）/ route_verified / travel_discrepancy
- 高德 verified → 采用高德；失败 → guide 明确路段 → LLM → Haversine；禁止三数取中

### 降级条件
1. 无合法顺序 / JSON 坏
2. 同日跨城级跳跃（复用现有距离阈值）
3. 相对近邻基线总耗时 +50% 且绝对值明显偏高
4. 高德大面积不可达（建议 ≥50% 点未核验）
5. 显式请求重排（reoptimize / respect_fill_order=False）

### 跨天
- fill prompt + day_continuity_note
- route：相邻日边界过远只 warning，首版不自动挪点

## 成功标准
- 未触发降级时同日顺序与 fill 一致
- 故意绕路 fill 能降级近邻并打标
- 高德成功时日程耗时来自高德；与估计超阈有提示
- 高德全失败任务仍能完成且 route_verified=false
- 跨天首尾过远有 warning

## 落地对照
- 生成路径 `route_itinerary_draft` 默认 `respect_fill_order=True`：按 fill 顺序地理编码并逐段计时。
- 降级整日最近邻（起点固定），`order_source` 为 `fill` 或 `nearest_neighbor`。阈值是 Haversine 估计相对最近邻 +50% 且绝对多出 ≥30 分钟；同日跳跃复用 250km。高德路段至少一半没有分钟数时也降级。没有密钥不算“大面积失败”，只走估计回退。
- 高德 Direction 只打最终顺序的相邻段（约 N-1 次/天）。+50% 基线和最近邻重排都用 Haversine，不构建 N×(N-1) 高德矩阵。5 个点的全量矩阵曾是 20 次请求，见 [development-notes §23/§28](../retrospectives/development-notes.md)。知识地图 §11 的有向矩阵不再用于决定顺序。
- 日程采用值写在 `travel_minutes_from_prev` / `travel_minutes`。高德成功优先；否则 guide → llm → Haversine，不取平均。绝对差 ≥15 分钟且相对差 ≥40% 时写 `travel_discrepancy`，并附在 `travel_advice` 上以便卡片展示。
- 坏 JSON 仍抛出，由生成任务按格式错误重试；没有合法顺序的当天标记降级。
- 显式重排：`respect_fill_order=False`（重新计算路线 / reoptimize）。`reorder=False` 仍锁定调用方顺序，只补时间。
- 跨天只在相邻日首尾超过 250km 时写 `day_boundary_warning`，不挪点。fill 提示词要求跨天衔接，并允许可选 `day_continuity_note` 与 `travel_estimate_source=llm`。
- 勾选候选只在有明确路段分钟时写 `travel_estimate_source=guide`。`suggested_duration_h` 仍只表示停留。
