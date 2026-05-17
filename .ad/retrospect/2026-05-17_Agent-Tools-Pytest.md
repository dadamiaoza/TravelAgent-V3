# 2026-05-17 复盘：Step 2-A / 2-B / Step 3 — 多 Tool 调度 + pytest + 循环调用

开发内容：fact_checker 升级双 Tool → 脚本整理为 pytest → guide_parser 攻略解析 Agent。

---

## 问题速查表

| # | 类别 | 问题 | 解法 | 行号 |
|---|------|------|------|------|
| 1 | LLM 响应 | MiniMax `<think>` 标签污染 JSON 输出 | 正则去标签 + `[`/`]` 边界截取 | L16 |
| 2 | pytest | `scope="module"` 导致间歇性测试失败 | 改为 function-scoped fixture | L40 |
| 3 | Agent 行为 | LLM 过度抽取 POI | 断言放宽为 `>=`，验证"必须包含" | L55 |

---

## 错误清单

### 1. MiniMax `<think>` 标签污染 JSON 输出

**现象**：
```python
json.loads(final)  # JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

**原因**：MiniMax M2.7 开启了 reasoning（思考链），最终 AIMessage 的 `content` 包含了 `<think>推理过程...</think>\n\n[{...JSON...}]`。直接 `json.loads()` 因为内容不以 `[` 开头而失败。

**第一次修复**（部分成功）：
```python
import re
content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL)
```
正则可以去掉 `<think>` 块，但如果 LLM 生成了多个 `<think>` 块，或 XML 嵌套不规范，正则仍然可能失败。

**最终修复**：去掉所有 `<think>` 标签后，用 `[` 和 `]` 边界提取纯 JSON 数组：
```python
content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
start = content.find("[")
end = content.rfind("]")
if start != -1 and end > start:
    return content[start:end + 1]
```

**教训**：
- LLM 的 `response_format` 不等于"一定会只输出 JSON"——reasoning 模式的模型会输出思考过程
- 解析 LLM 输出时**永远要做防御性提取**，不能假设输出就是干净的 JSON
- 三个层次：直接 `json.loads()` → 正则清洗 → 边界字符定位（越来越鲁棒）

---

### 2. pytest `scope="module"` 导致间歇性测试失败

**现象**：
- 单独跑 `test_parse_named_pois_only` → PASSED
- 三个测试一起跑 → `test_parse_simple_travelogue` FAILED（JSONDecodeError）
- Debug 脚本（没走 pytest）→ 每次成功

**原因**：pytest fixture 使用了 `scope="module"`，三个测试共享同一个 agent 实例。LangChain agent 内部可能积累状态，导致后续测试的 prompt 被污染。加上 MiniMax API 响应本身有一定随机性，状态污染和随机性叠加，产生了间歇性失败。

**修复**：
```python
# 之前
@pytest.fixture(scope="module")
def agent():
    return create_guide_parser()

# 之后
@pytest.fixture
def agent():
    return create_guide_parser()
```

**教训**：
- Agent 测试**默认用 function scope**，除非确定 agent 是纯无状态的
- `scope="module"` 适用于昂贵的初始化（如加载模型），但 LangChain agent 创建成本很低
- 间歇性失败 + 单独跑能过 = 检查 fixture scope 和状态共享

---

### 3. LLM 过度抽取 POI

**现象**：
```
AssertionError: Expected 3 POIs, got 4: ['西湖', '雷峰塔', '灵隐寺', '茶园']
```
输入文本：`"第一天：西湖坐船，登上雷峰塔看全景。\n第二天：灵隐寺烧香，然后去附近的茶园转了一圈。"`

**原因**：LLM 忠实地提取了"茶园"作为第 4 个 POI。从 NLP 角度看这是正确的——"茶园"确实是文本中提到的一个地点。但测试预期只写了 3 个知名景点。

**修复**（两种方式）：
1. **放宽断言**：`assert len(geocode_calls) >= 3`（接受 LLM 多提取）
2. **精简输入**：把"附近的茶园"改为更明确的地名或直接去掉

**教训**：
- 测试 LLM Agent 时，**断言不要太精确**——LLM 的输出本质上是概率性的
- 验证"必须包含的"比验证"只有这些"更稳健：`assert "西湖" in day1_pois` 而不是 `assert len == 3`
- AI Agent 测试不能像传统单元测试那样写死精确值
