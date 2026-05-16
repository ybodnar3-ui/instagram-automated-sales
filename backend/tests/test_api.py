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


# ── Trigger tests ────────────────────────────────────────────────────────────

def _create_account_in_db(db_session):
    import uuid
    from models.account import Account, BotStatus
    from datetime import datetime, timezone
    acct = Account(
        username="testuser_" + uuid.uuid4().hex[:12],
        bot_status=BotStatus.active,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(acct)
    db_session.commit()
    db_session.refresh(acct)
    return acct


def test_list_triggers_nonexistent_account_returns_404():
    response = client.get("/api/triggers/999999")
    assert response.status_code == 404


def test_list_triggers_returns_empty_for_new_account():
    db = next(override_get_db())
    acct = _create_account_in_db(db)
    response = client.get(f"/api/triggers/{acct.id}")
    assert response.status_code == 200
    assert response.json() == []


def test_create_trigger_returns_201():
    db = next(override_get_db())
    acct = _create_account_in_db(db)
    payload = {"keyword": "+", "response_template": "Hi {username}!", "use_ai_followup": False}
    response = client.post(f"/api/triggers/{acct.id}", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["keyword"] == "+"
    assert data["response_template"] == "Hi {username}!"
    assert data["is_active"] is True


def test_delete_trigger_returns_200():
    db = next(override_get_db())
    acct = _create_account_in_db(db)
    payload = {"keyword": "+", "response_template": "Hi!", "use_ai_followup": False}
    created = client.post(f"/api/triggers/{acct.id}", json=payload).json()
    response = client.delete(f"/api/triggers/{acct.id}/{created['id']}")
    assert response.status_code == 200


# ── Outbound tests ────────────────────────────────────────────────────────────

def test_list_outbound_nonexistent_account_returns_404():
    response = client.get("/api/outbound/999999")
    assert response.status_code == 404


def test_list_outbound_returns_empty_for_new_account():
    db = next(override_get_db())
    acct = _create_account_in_db(db)
    response = client.get(f"/api/outbound/{acct.id}")
    assert response.status_code == 200
    assert response.json() == []


def test_add_outbound_target_returns_201():
    db = next(override_get_db())
    acct = _create_account_in_db(db)
    payload = {"instagram_username": "target_user", "initial_message": "Hey!"}
    response = client.post(f"/api/outbound/{acct.id}", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["instagram_username"] == "target_user"
    assert data["status"] == "pending"


def test_delete_outbound_target_returns_200():
    db = next(override_get_db())
    acct = _create_account_in_db(db)
    payload = {"instagram_username": "target_user"}
    created = client.post(f"/api/outbound/{acct.id}", json=payload).json()
    response = client.delete(f"/api/outbound/{acct.id}/{created['id']}")
    assert response.status_code == 200
