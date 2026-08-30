"""Pytest configuration.

Layering:
- unit: no DB / no LLM, fast
- integration: real DB, should use transaction rollback
- agent: real LLM / external services, excluded by default
"""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db, SessionLocal


AGENT_TEST_MODULES = {
    "test_agents.py",
    "test_itinerary_gen.py",
    "test_supervisor.py",
    "test_guide_parser.py",
    "test_merge.py",
}


def override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
def client():
    """FastAPI TestClient with real DB."""
    return TestClient(app)


@pytest.fixture
def db():
    """Direct DB session (integration style).

    TODO: switch to a transaction-rollback session to avoid polluting data.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def pytest_collection_modifyitems(items):
    """Automatically mark real-LLM/agent tests so `-m 'not agent'` excludes them."""
    for item in items:
        path_str = str(item.path)
        module_name = Path(item.path).name
        is_agent = (
            "tests/agents" in path_str
            or module_name in AGENT_TEST_MODULES
            or "agent" in item.name.lower()
            or "generate_itinerary" in item.name
        )
        if is_agent:
            item.add_marker(pytest.mark.agent)
        if "tests/unit" in path_str:
            item.add_marker(pytest.mark.unit)
        if "tests/integration" in path_str:
            item.add_marker(pytest.mark.integration)
