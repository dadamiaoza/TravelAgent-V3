"""Pytest configuration."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db, SessionLocal


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
    """Direct DB session (no rollback — integration style)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
