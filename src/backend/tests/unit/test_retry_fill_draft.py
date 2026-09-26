"""Retry payload copy: default keeps fill_draft; discard drops only that key."""
from app.services.generation_jobs import (
    FILL_DRAFT_PAYLOAD_KEY,
    copy_job_payload_for_retry,
    payload_has_reusable_fill_draft,
)


def _payload() -> dict:
    return {
        "selected_entities": [{"poi_name": "西湖", "day_index": 1, "seq": 1}],
        FILL_DRAFT_PAYLOAD_KEY: {"city": "杭州", "days": [{"day_index": 1}]},
    }


def test_default_copy_keeps_fill_draft_and_entities() -> None:
    source = _payload()
    copied = copy_job_payload_for_retry(source)
    assert copied[FILL_DRAFT_PAYLOAD_KEY] == source[FILL_DRAFT_PAYLOAD_KEY]
    assert copied["selected_entities"] == source["selected_entities"]
    assert copied is not source
    copied["selected_entities"][0]["poi_name"] = "雷峰塔"
    assert source["selected_entities"][0]["poi_name"] == "西湖"


def test_explicit_false_keeps_fill_draft() -> None:
    copied = copy_job_payload_for_retry(_payload(), discard_fill_draft=False)
    assert FILL_DRAFT_PAYLOAD_KEY in copied
    assert payload_has_reusable_fill_draft(copied) is True


def test_discard_drops_draft_and_keeps_selected_entities() -> None:
    copied = copy_job_payload_for_retry(_payload(), discard_fill_draft=True)
    assert FILL_DRAFT_PAYLOAD_KEY not in copied
    assert copied["selected_entities"][0]["poi_name"] == "西湖"
    assert payload_has_reusable_fill_draft(copied) is False


def test_discard_without_draft_or_payload_is_empty_of_that_key() -> None:
    entities_only = {"selected_entities": [{"poi_name": "西湖"}]}
    copied = copy_job_payload_for_retry(entities_only, discard_fill_draft=True)
    assert copied == entities_only
    assert copy_job_payload_for_retry(None) == {}
    assert copy_job_payload_for_retry(None, discard_fill_draft=True) == {}
    assert payload_has_reusable_fill_draft(None) is False
    assert payload_has_reusable_fill_draft({"fill_draft": "not-a-dict"}) is False
