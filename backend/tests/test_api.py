import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, get_db
from main import app

TEST_DATABASE_URL = "sqlite:///./test_api.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.clear()


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "db" in data


def test_list_accounts_empty():
    response = client.get("/api/accounts")
    assert response.status_code == 200
    assert response.json() == []


def test_pause_nonexistent_account_returns_404():
    response = client.post("/api/bot/999/pause")
    assert response.status_code == 404


def test_resume_nonexistent_account_returns_404():
    response = client.post("/api/bot/999/resume")
    assert response.status_code == 404


def test_get_status_nonexistent_account_returns_404():
    response = client.get("/api/bot/999/status")
    assert response.status_code == 404


def test_list_conversations_nonexistent_account_returns_404():
    response = client.get("/api/conversations/999")
    assert response.status_code == 404


def test_daily_stats_nonexistent_account_returns_404():
    response = client.get("/api/stats/999/daily?days=7")
    assert response.status_code == 404


def test_summary_nonexistent_account_returns_404():
    response = client.get("/api/stats/999/summary")
    assert response.status_code == 404


def test_conversations_invalid_stage_returns_422():
    response = client.get("/api/conversations/1?stage=invalid")
    assert response.status_code == 422


def test_get_config_nonexistent_returns_404():
    response = client.get("/api/bot/999/config")
    assert response.status_code == 404


def test_delete_nonexistent_account_returns_404():
    response = client.delete("/api/accounts/999")
    assert response.status_code == 404
