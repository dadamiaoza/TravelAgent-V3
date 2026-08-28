"""攻略来源持久化接口单元测试。"""
import uuid
from types import SimpleNamespace

from app.api.v1.sources import create_source, get_source, list_sources
from app.schemas.trip import SourceCreateRequest


class FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._result

    def all(self):
        return self._result if isinstance(self._result, list) else [self._result]


class FakeDB:
    def __init__(self, result=None):
        self._result = result
        self.added = []
        self.committed = False
        self.refreshed = []

    def query(self, *args, **kwargs):
        return FakeQuery(self._result)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        self.refreshed.append(obj)


def test_create_source_persists_document():
    """创建攻略应写入 source_documents。"""
    db = FakeDB()
    result = create_source(
        SourceCreateRequest(title="杭州攻略", text="第一天去了西湖，下午雷峰塔"),
        db=db,
    )

    assert result.title == "杭州攻略"
    assert result.content == "第一天去了西湖，下午雷峰塔"
    assert db.committed is True
    assert len(db.added) == 1


def test_list_sources_returns_documents():
    """攻略列表应返回已持久化的来源。"""
    doc = SimpleNamespace(id=uuid.uuid4(), title="攻略A", url=None, content="内容")
    db = FakeDB([doc])
    result = list_sources(db)
    assert result[0].title == "攻略A"


def test_get_source_returns_document():
    """按 ID 获取攻略详情。"""
    doc = SimpleNamespace(id=uuid.uuid4(), title="攻略B", url=None, content="内容")
    db = FakeDB(doc)
    result = get_source(doc.id, db=db)
    assert result.title == "攻略B"
