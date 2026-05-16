import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from models.account import Account, BotStatus


def make_account(days_old=20, messages_today=0, bot_status=BotStatus.active, last_reset_date=None):
    account = MagicMock(spec=Account)
    account.created_at = datetime.now(timezone.utc) - timedelta(days=days_old)
    account.messages_today = messages_today
    account.bot_status = bot_status
    account.daily_limit = 80
    account.last_reset_date = last_reset_date
    account.pause_reason = None
    return account


def make_config(max_messages=80, warmup=True):
    config = MagicMock()
    config.max_messages_per_day = max_messages
    config.warmup_mode = warmup
    config.min_delay_sec = 8.0
    config.max_delay_sec = 25.0
    return config


class TestGetWarmupLimit:
    def test_day_1_returns_15(self):
        from services.anti_ban import get_warmup_limit
        assert get_warmup_limit(make_account(days_old=1)) == 15

    def test_day_3_returns_15(self):
        from services.anti_ban import get_warmup_limit
        assert get_warmup_limit(make_account(days_old=3)) == 15

    def test_day_4_returns_30(self):
        from services.anti_ban import get_warmup_limit
        assert get_warmup_limit(make_account(days_old=4)) == 30

    def test_day_7_returns_30(self):
        from services.anti_ban import get_warmup_limit
        assert get_warmup_limit(make_account(days_old=7)) == 30

    def test_day_8_returns_50(self):
        from services.anti_ban import get_warmup_limit
        assert get_warmup_limit(make_account(days_old=8)) == 50

    def test_day_14_returns_50(self):
        from services.anti_ban import get_warmup_limit
        assert get_warmup_limit(make_account(days_old=14)) == 50

    def test_day_15_returns_80(self):
        from services.anti_ban import get_warmup_limit
        assert get_warmup_limit(make_account(days_old=15)) == 80


class TestGetHumanDelay:
    def test_delay_within_expected_range_short_message(self):
        from services.anti_ban import get_human_delay
        for _ in range(20):
            delay = get_human_delay(50)
            # min: 8 + 50*0.03 + 3 = 12.5; max: 25 + 50*0.03 + 12 = 38.5
            assert 12.5 <= delay <= 39.0, f"delay {delay} out of range"

    def test_longer_message_increases_average_delay(self):
        from services.anti_ban import get_human_delay
        short_delays = [get_human_delay(10) for _ in range(50)]
        long_delays = [get_human_delay(500) for _ in range(50)]
        assert sum(long_delays) / len(long_delays) > sum(short_delays) / len(short_delays)

    def test_uses_config_min_max_delay(self):
        from services.anti_ban import get_human_delay
        config = make_config(max_messages=80, warmup=False)
        config.min_delay_sec = 20.0
        config.max_delay_sec = 21.0
        for _ in range(20):
            delay = get_human_delay(0, config)
            # base: 20-21, reading: 0, typing: 3-12
            assert 23.0 <= delay <= 33.0, f"delay {delay} not using config values"

    def test_swaps_min_max_if_misconfigured(self):
        from services.anti_ban import get_human_delay
        config = make_config()
        config.min_delay_sec = 25.0
        config.max_delay_sec = 8.0  # min > max — should not crash
        for _ in range(10):
            delay = get_human_delay(0, config)
            assert delay >= 0


class TestGetTypingDuration:
    def test_typing_duration_within_range(self):
        from services.anti_ban import get_typing_duration
        for _ in range(20):
            duration = get_typing_duration(100)
            assert 5.0 <= duration <= 10.0, f"duration {duration} out of range"


class TestCanSendMessage:
    def test_active_account_under_limit_can_send(self):
        from services.anti_ban import can_send_message
        account = make_account(days_old=20, messages_today=5)
        config = make_config(max_messages=80, warmup=False)
        db = MagicMock()
        assert can_send_message(account, config, db) is True

    def test_paused_account_cannot_send(self):
        from services.anti_ban import can_send_message
        account = make_account(bot_status=BotStatus.paused)
        config = make_config()
        db = MagicMock()
        assert can_send_message(account, config, db) is False

    def test_error_account_cannot_send(self):
        from services.anti_ban import can_send_message
        account = make_account(bot_status=BotStatus.error)
        config = make_config()
        db = MagicMock()
        assert can_send_message(account, config, db) is False

    def test_account_at_limit_cannot_send(self):
        from services.anti_ban import can_send_message
        account = make_account(days_old=20, messages_today=80)
        config = make_config(max_messages=80, warmup=False)
        db = MagicMock()
        assert can_send_message(account, config, db) is False

    def test_warmup_mode_caps_limit_by_age(self):
        from services.anti_ban import can_send_message
        # day-1 account, warmup=True, config limit=80, but warmup caps at 15
        account = make_account(days_old=1, messages_today=16)
        config = make_config(max_messages=80, warmup=True)
        db = MagicMock()
        assert can_send_message(account, config, db) is False

    def test_warmup_mode_respects_lower_config_limit(self):
        from services.anti_ban import can_send_message
        # day-20 account warmup limit=80, but config says max=30; messages=31
        account = make_account(days_old=20, messages_today=31)
        config = make_config(max_messages=30, warmup=True)
        db = MagicMock()
        assert can_send_message(account, config, db) is False
