"""Quick test script for Step 1: Fact Checker Agent."""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from app.agents.fact_checker import create_fact_checker

agent = create_fact_checker()

print("=== Step 1: Fact Checker Agent Test ===\n")

question = "北京 2026-06-01 天气如何？"
print(f"[User] {question}\n")
result = agent.invoke({"messages": [{"role": "user", "content": question}]})

for i, msg in enumerate(result["messages"]):
    cls_name = type(msg).__name__
    role = getattr(msg, "type", "?")
    tool_calls = getattr(msg, "tool_calls", None)
    content = getattr(msg, "content", "")
    print(f"[{i}] {cls_name}  role={role}  tool_calls={tool_calls}")
    if content:
        print(f"    {str(content)[:200]}")
    print()

print("=== Test complete ===")
