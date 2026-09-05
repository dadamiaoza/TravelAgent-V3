"""Generation-path fact verification: rules + tools, never HTTP self-call."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.agents.tools.opening_hours import get_opening_hours
from app.agents.tools.weather import get_weather
from app.services.closure_rules import evaluate_closure_rule

logger = logging.getLogger(__name__)

VERIFY_TIMEOUT_SECONDS = 12


@dataclass
class VerifyOutcome:
    degraded: bool = False
    warnings: list[str] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.warnings:
            return "时效核对完成"
        return "；".join(self.warnings[:8])


def verify_itinerary_draft(
    draft: dict,
    *,
    city: str,
    start_date: date,
    timeout_seconds: float = VERIFY_TIMEOUT_SECONDS,
) -> VerifyOutcome:
    """Check weather and opening hours for a filled/routed draft.

    Failures degrade to warnings. Callers must not fail the generation job.
    """

    def run() -> VerifyOutcome:
        return _verify_sync(draft, city=city, start_date=start_date)

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(run).result(timeout=timeout_seconds)
    except FuturesTimeoutError:
        return VerifyOutcome(
            degraded=True,
            warnings=["时效核对未完成，行程已按路线生成"],
        )
    except Exception:
        logger.exception("itinerary verify failed")
        return VerifyOutcome(
            degraded=True,
            warnings=["时效核对未完成，行程已按路线生成"],
        )


def _verify_sync(draft: dict, *, city: str, start_date: date) -> VerifyOutcome:
    outcome = VerifyOutcome()
    weather_by_date: dict[str, str] = {}

    for day in draft.get("days") or []:
        day_index = int(day.get("day_index") or 1)
        day_date = start_date + timedelta(days=day_index - 1)
        date_key = day_date.isoformat()
        if date_key not in weather_by_date:
            try:
                weather_by_date[date_key] = get_weather(city or "", date_key)
            except Exception:
                logger.warning("weather lookup failed for %s %s", city, date_key)
                outcome.degraded = True
                outcome.warnings.append("天气查询失败，行程已按路线生成")
                weather_by_date[date_key] = ""

        for item in day.get("items") or []:
            poi_name = (item.get("poi_name") or "").strip()
            if not poi_name:
                continue
            rule = evaluate_closure_rule(poi_name, day_date)
            opening_hours = ""
            try:
                opening_hours = get_opening_hours(poi_name, date_key)
            except Exception:
                logger.warning("opening hours lookup failed for %s", poi_name)
                outcome.degraded = True
                outcome.warnings.append(f"{poi_name} 开放时间查询失败")

            risk = rule.get("risk") or "low"
            if rule.get("matched") and risk in {"medium", "high"}:
                reason = rule.get("reason") or "命中时效规则"
                outcome.warnings.append(f"{poi_name}（{date_key}）：{reason}")

            outcome.results.append(
                {
                    "poi_name": poi_name,
                    "day_index": day_index,
                    "date": date_key,
                    "risk": risk,
                    "risk_type": rule.get("rule_type"),
                    "reason": rule.get("reason"),
                    "source": rule.get("source"),
                    "weather": weather_by_date.get(date_key) or None,
                    "opening_hours": opening_hours or None,
                }
            )

    if outcome.degraded and not any("未完成" in warning for warning in outcome.warnings):
        outcome.warnings.append("时效核对未完成，行程已按路线生成")
    return outcome


def apply_verify_to_draft(draft: dict, outcome: VerifyOutcome) -> dict:
    """Stamp opening hours and short risk warnings onto draft items. Does not invent tips."""
    by_key: dict[tuple, dict] = {}
    for result in getattr(outcome, "results", None) or []:
        name = (result.get("poi_name") or "").strip()
        day_index = int(result.get("day_index") or 0)
        if name and day_index:
            by_key[(day_index, name)] = result

    for day in draft.get("days") or []:
        day_index = int(day.get("day_index") or 0)
        for item in day.get("items") or []:
            name = (item.get("poi_name") or "").strip()
            result = by_key.get((day_index, name))
            if not result:
                continue
            hours = (result.get("opening_hours") or "").strip()
            if hours:
                item["opening_hours"] = hours
            risk = result.get("risk") or "low"
            if risk in {"medium", "high"}:
                item["fact_warning"] = (result.get("reason") or "").strip() or "存在时效风险"
    return draft
