"""Quick test script for Step 2: Fact Checker Agent with multiple tools."""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from app.agents.fact_checker import create_fact_checker

agent = create_fact_checker()

scenarios = [
    (
        "Scenario 1 — 天气查询",
        "北京 2026-06-01 天气如何？",
        ["get_weather"],
    ),
    (
        "Scenario 2 — 景点开放时间",
        "故宫博物院 2026-06-01 开门吗？门票多少钱？",
        ["get_opening_hours"],
    ),
    (
        "Scenario 3 — 复合查询",
        "我计划 2026-06-01 去故宫，当天的天气和开放时间分别怎样？",
        ["get_weather", "get_opening_hours"],
    ),
]

for title, question, expected_tools in scenarios:
    print(f"=== {title} ===")
    print(f"[User] {question}\n")
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})

    called_tools: list[str] = []
    for msg in result["messages"]:
        cls_name = type(msg).__name__
        tool_calls = getattr(msg, "tool_calls", None)
        content = getattr(msg, "content", "")

        if tool_calls:
            for tc in tool_calls:
                print(f"  → LLM 选择调用: {tc['name']}")
                called_tools.append(tc["name"])

    # Check expected tools were called
    missing = set(expected_tools) - set(called_tools)
    if missing:
        print(f"  ❌ 缺少 Tool 调用: {missing}")
    else:
        print(f"  ✅ 所有期望 Tool 已调用")

    # Print final synthesis
    final_msg = result["messages"][-1]
    final_content = getattr(final_msg, "content", "")
    if final_content:
        print(f"  [Agent] {str(final_content)[:300]}")
    print()

print("=== All scenarios complete ===")
