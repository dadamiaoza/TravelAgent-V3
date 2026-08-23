"""A-3 facts/check 统一风险汇总接口测试。

这里直接调用 check_facts 并 mock Agent，避免依赖真实 LLM 和数据库。
"""
import json
from unittest.mock import patch

from langchain_core.messages import AIMessage

from app.api.v1.facts import check_facts
from app.schemas.trip import FactCheckItem, FactCheckRequest


class FakeDB:
    """最小可用的 fake DB，只记录 add/commit 调用。"""

    def __init__(self):
        self.added = []
        self.committed = False

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True



def _fake_agent(output: list[dict]):
    class FakeAgent:
        def invoke(self, messages):
            # 记录 prompt，方便断言规则引擎结果被注入
            self.last_prompt = messages["messages"][0]["content"]
            return {
                "messages": [
                    AIMessage(content=json.dumps(output, ensure_ascii=False)),
                ]
            }

    return FakeAgent()


def test_check_facts_returns_unified_risk_for_closed_rule():
    """命中周一闭馆规则时，返回统一风险结构且 checked_at 由后端填充。"""
    fake = _fake_agent([
        {
            "poi_name": "萍乡博物馆",
            "date": "2026-08-24",
            "risk": "high",
            "risk_type": "weekly_closure",
            "reason": "命中周一闭馆规则",
            "source": "规则配置：museum-monday-closed",
            "weather": "晴",
            "opening_hours": "开放时间 09:00-17:00",
            "needs_manual_confirmation": True,
            "advice": "出行前请再次确认",
        },
    ])

    db = FakeDB()
    with patch("app.api.v1.facts.create_fact_checker", return_value=fake):
        result = check_facts(FactCheckRequest(
            items=[FactCheckItem(poi_name="萍乡博物馆", date="2026-08-24")],
        ), db=db)

    item = result.results[0]
    assert item.risk == "high"
    assert item.risk_type == "weekly_closure"
    assert item.reason == "命中周一闭馆规则"
    assert item.checked_at is not None
    # 规则引擎结果必须已注入 prompt
    assert "museum-monday-closed" in fake.last_prompt
    # A-4：结果应被持久化
    assert db.committed is True
    assert len(db.added) == 1
    assert db.added[0].poi_name == "萍乡博物馆"
    assert db.added[0].risk == "high"


def test_check_facts_returns_low_risk_when_rule_not_hit():
    """周二未命中闭馆规则时，返回 low 风险。"""
    fake = _fake_agent([
        {
            "poi_name": "萍乡博物馆",
            "date": "2026-08-25",
            "risk": "low",
            "risk_type": "none",
            "reason": "未命中固定闭馆规则",
            "source": "",
            "weather": "晴",
            "opening_hours": "开放时间 09:00-17:00",
            "needs_manual_confirmation": True,
            "advice": "建议出行前以官方公告为准",
        },
    ])

    db = FakeDB()
    with patch("app.api.v1.facts.create_fact_checker", return_value=fake):
        result = check_facts(FactCheckRequest(
            items=[FactCheckItem(poi_name="萍乡博物馆", date="2026-08-25")],
        ), db=db)

    item = result.results[0]
    assert item.risk == "low"
    assert item.risk_type == "none"
    assert item.checked_at is not None
    assert len(db.added) == 1
    assert db.added[0].risk == "low"

def test_check_facts_persists_trip_and_item_association():
    """传入 trip_id / itinerary_item_id 时，持久化记录应保留关联。"""
    import uuid

    trip_id = uuid.uuid4()
    item_id = uuid.uuid4()
    fake = _fake_agent([
        {
            "poi_name": "萍乡博物馆",
            "date": "2026-08-24",
            "risk": "high",
            "risk_type": "weekly_closure",
            "reason": "周一闭馆",
            "source": "规则配置",
            "weather": "晴",
            "opening_hours": "09:00-17:00",
            "needs_manual_confirmation": True,
            "advice": "出行前确认",
        },
    ])

    db = FakeDB()
    with patch("app.api.v1.facts.create_fact_checker", return_value=fake):
        result = check_facts(FactCheckRequest(
            trip_id=trip_id,
            items=[FactCheckItem(
                itinerary_item_id=item_id,
                poi_name="萍乡博物馆",
                date="2026-08-24",
            )],
        ), db=db)

    assert len(db.added) == 1
    record = db.added[0]
    assert record.trip_id == trip_id
    assert record.itinerary_item_id == item_id
    assert result.results[0].poi_name == "萍乡博物馆"

