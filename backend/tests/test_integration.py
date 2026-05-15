"""
Integration tests using SQLite for isolation.
Tests the full account lifecycle and anti-ban warmup logic.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DB_URL = "sqlite:///./test_integration.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_db():
    from database import Base, get_db
    from main import app
    Base.metadata.create_all(bind=test_engine)

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


@pytest.fixture
def db():
    session = TestSession()
    yield session
    session.close()


def test_full_account_lifecycle(client):
    """Create account, check status, pause, resume, update config, delete."""
    with patch("services.instagram.login_and_save") as mock_login:
        mock_login.return_value = MagicMock()
        resp = client.post("/api/accounts", json={
            "username": "test_ig_user",
            "password": "fake_password",
            "business_name": "Test Shop",
            "service_description": "nail services",
            "price_info": "from $30",
            "objections_script": "we offer refunds",
        })
        assert resp.status_code == 201, resp.json()
        account_id = resp.json()["id"]
        assert resp.json()["username"] == "test_ig_user"

    # List accounts
    resp = client.get("/api/accounts")
    assert resp.status_code == 200
    assert any(a["username"] == "test_ig_user" for a in resp.json())

    # Check initial status is active
    resp = client.get(f"/api/bot/{account_id}/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    # Pause bot
    resp = client.post(f"/api/bot/{account_id}/pause")
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"

    # Verify paused
    resp = client.get(f"/api/bot/{account_id}/status")
    assert resp.json()["status"] == "paused"
    assert resp.json()["pause_reason"] == "manual"

    # Resume bot
    resp = client.post(f"/api/bot/{account_id}/resume")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    # Verify active
    resp = client.get(f"/api/bot/{account_id}/status")
    assert resp.json()["status"] == "active"

    # Update config
    resp = client.put(f"/api/bot/{account_id}/config", json={"max_messages_per_day": 50})
    assert resp.status_code == 200

    # Verify config updated
    resp = client.get(f"/api/bot/{account_id}/config")
    assert resp.status_code == 200
    assert resp.json()["max_messages_per_day"] == 50

    # Stats initially empty
    resp = client.get(f"/api/stats/{account_id}/daily")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    resp = client.get(f"/api/stats/{account_id}/summary")
    assert resp.json()["total_conversations"] == 0
    assert resp.json()["conversion_rate_pct"] == 0.0

    # Conversations empty
    resp = client.get(f"/api/conversations/{account_id}")
    assert resp.status_code == 200
    assert resp.json() == []

    # Delete account
    resp = client.delete(f"/api/accounts/{account_id}")
    assert resp.status_code == 200

    # Verify deleted
    resp = client.get("/api/accounts")
    assert all(a["id"] != account_id for a in resp.json())


def test_anti_ban_warmup_limits(db):
    """Test that warmup mode properly restricts new accounts."""
    from models.account import Account, BotStatus
    from models.stats import BotConfig
    from services.anti_ban import can_send_message, get_warmup_limit

    # Create a brand-new account (day 0)
    account = Account(
        username="warmup_test",
        created_at=datetime.now(timezone.utc),
        messages_today=0,
        bot_status=BotStatus.active,
        is_active=True,
        daily_limit=80,
    )
    db.add(account)
    db.flush()

    config = BotConfig(
        account_id=account.id,
        max_messages_per_day=80,
        warmup_mode=True,
        business_name="Test",
        service_description="Test service",
        price_info="$10",
        objections_script="No objections",
    )
    db.add(config)
    db.flush()

    # Day 0 account — warmup limit should be 15
    warmup_limit = get_warmup_limit(account)
    assert warmup_limit == 15

    # Under limit: can send
    assert can_send_message(account, config, db) is True

    # At limit (16 messages for a day-0 account): cannot send
    account.messages_today = 16
    db.flush()
    assert can_send_message(account, config, db) is False

    # Without warmup mode: respects config limit (80)
    config.warmup_mode = False
    account.messages_today = 50
    db.flush()
    assert can_send_message(account, config, db) is True

    # With warmup mode but old account: 80 limit applies
    config.warmup_mode = True
    account.created_at = datetime.now(timezone.utc) - timedelta(days=20)
    account.messages_today = 79
    db.flush()
    assert can_send_message(account, config, db) is True  # 79 < 80

    account.messages_today = 80
    db.flush()
    assert can_send_message(account, config, db) is False  # 80 >= 80
