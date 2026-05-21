"""Unit tests for multi-source merge & dedup."""
import json
from unittest.mock import patch, MagicMock

from app.services.merge import merge_candidates


def _make_entities(*names):
    return [{"poi_name": n, "lat": None, "lng": None} for n in names]


class TestMergeCandidates:
    def test_single_source_noop(self):
        """Single source → same entities with mention_count=1."""
        sources = [("攻略A", _make_entities("西湖", "灵隐寺"))]
        result = merge_candidates(sources)
        assert len(result) == 2
        assert result[0]["poi_name"] == "西湖"
        assert result[0]["mention_count"] == 1
        assert result[0]["source_names"] == ["攻略A"]

    def test_empty_sources(self):
        result = merge_candidates([])
        assert result == []

    def test_empty_entities(self):
        result = merge_candidates([("攻略A", [])])
        assert result == []

    def test_llm_merge_two_sources(self):
        """Mock LLM response — verify merge call is made with correct prompt."""
        sources = [
            ("攻略A", _make_entities("西湖", "灵隐寺")),
            ("攻略B", _make_entities("杭州西湖", "雷峰塔")),
        ]

        mock_response = [
            {"poi_name": "西湖", "lat": None, "lng": None, "mention_count": 2, "source_names": ["攻略A", "攻略B"]},
            {"poi_name": "灵隐寺", "lat": None, "lng": None, "mention_count": 1, "source_names": ["攻略A"]},
            {"poi_name": "雷峰塔", "lat": None, "lng": None, "mention_count": 1, "source_names": ["攻略B"]},
        ]

        with patch("app.services.merge.ChatOpenAI") as mock_llm:
            mock_instance = MagicMock()
            mock_llm.return_value = mock_instance
            mock_instance.invoke.return_value.content = json.dumps(mock_response, ensure_ascii=False)

            result = merge_candidates(sources)

        assert len(result) == 3
        assert result[0]["poi_name"] == "西湖"
        assert result[0]["mention_count"] == 2
        assert result[0]["source_names"] == ["攻略A", "攻略B"]
        assert result[1]["mention_count"] == 1

    def test_llm_response_with_wrapping_text(self):
        """LLM may wrap JSON in prose — parse should still succeed."""
        sources = [
            ("攻略A", _make_entities("西湖")),
            ("攻略B", _make_entities("西湖")),
        ]

        wrapped = 'Here is the merged result:\n[{"poi_name": "西湖", "mention_count": 2, "source_names": ["攻略A", "攻略B"]}]\nDone.'

        with patch("app.services.merge.ChatOpenAI") as mock_llm:
            mock_instance = MagicMock()
            mock_llm.return_value = mock_instance
            mock_instance.invoke.return_value.content = wrapped

            result = merge_candidates(sources)

        assert len(result) == 1
        assert result[0]["mention_count"] == 2
