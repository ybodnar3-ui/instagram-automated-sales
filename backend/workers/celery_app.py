import logging
import random
import time
from datetime import datetime, timezone, date
from celery import Celery
from config import settings, setup_logging

setup_logging()
logger = logging.getLogger(__name__)

celery_app = Celery(
    "igbot",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "poll-instagram-every-90s": {
            "task": "workers.celery_app.poll_all_accounts",
            "schedule": 90.0,
        },
        "reset-daily-limits-hourly": {
            "task": "workers.celery_app.reset_daily_limits",
            "schedule": 3600.0,
        },
    },
)


@celery_app.task(name="workers.celery_app.poll_all_accounts", bind=True, max_retries=3)
def poll_all_accounts(self):
    from database import SessionLocal
    from models.account import Account, BotStatus

    db = SessionLocal()
    try:
        accounts = (
            db.query(Account)
            .filter(Account.bot_status == BotStatus.active, Account.is_active.is_(True))
            .all()
        )
        logger.debug("poll_all_accounts: scheduling polls for %d active accounts", len(accounts))
        for account in accounts:
            jitter = random.randint(0, 60)
            poll_account_dms.apply_async(args=[account.id], countdown=jitter)
    except Exception as exc:
        logger.error("poll_all_accounts failed: %s", exc, exc_info=True)
        self.retry(exc=exc, countdown=30)
    finally:
        db.close()


def _normalize_ts(ts) -> datetime:
    """Return a timezone-aware UTC datetime regardless of whether ts is naive or aware."""
    if ts is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if hasattr(ts, 'tzinfo') and ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


@celery_app.task(name="workers.celery_app.poll_account_dms", bind=True, max_retries=3)
def poll_account_dms(self, account_id: int):
    from database import SessionLocal
    from models.account import Account, BotStatus
    from models.conversation import Conversation
    from models.message import Message, Direction
    from models.stats import BotConfig, DailyStats
    from services.instagram import poll_inbox
    from services.anti_ban import can_send_message

    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            logger.warning("poll_account_dms: account_id=%d not found", account_id)
            return
        if account.bot_status != BotStatus.active:
            logger.debug("account=%s is %s, skipping poll", account.username, account.bot_status.value)
            return

        config = db.query(BotConfig).filter(BotConfig.account_id == account_id).first()
        threads = poll_inbox(account, db)

        for thread in threads:
            thread_id = str(thread.id)

            conv = db.query(Conversation).filter(
                Conversation.account_id == account_id,
                Conversation.instagram_thread_id == thread_id,
            ).first()

            if not conv:
                username = thread.users[0].username if thread.users else "unknown"
                conv = Conversation(
                    account_id=account_id,
                    instagram_thread_id=thread_id,
                    interlocutor_username=username,
                    started_at=datetime.now(timezone.utc),
                )
                db.add(conv)
                db.commit()
                db.refresh(conv)
                logger.info(
                    "account=%s new conversation thread=%s user=%s",
                    account.username, thread_id, username,
                )

                today = date.today()
                stats = db.query(DailyStats).filter(
                    DailyStats.account_id == account_id,
                    DailyStats.date == today,
                ).first()
                if not stats:
                    stats = DailyStats(account_id=account_id, date=today)
                    db.add(stats)
                stats.new_conversations += 1
                db.commit()

            if not conv.bot_active:
                continue

            last_msg = (
                db.query(Message)
                .filter(Message.conversation_id == conv.id)
                .order_by(Message.sent_at.desc())
                .first()
            )
            last_msg_ts = _normalize_ts(last_msg.sent_at if last_msg else None)

            viewer_id = thread.viewer_id
            for msg in thread.messages:
                if msg.user_id == viewer_id:
                    continue

                msg_sent_at = _normalize_ts(msg.timestamp)

                if msg_sent_at <= last_msg_ts:
                    continue

                new_msg = Message(
                    conversation_id=conv.id,
                    direction=Direction.incoming,
                    content=msg.text or "",
                    sent_at=msg_sent_at,
                )
                db.add(new_msg)
                conv.last_message_at = msg_sent_at
                conv.messages_count += 1
                db.commit()
                db.refresh(new_msg)
                logger.info(
                    "account=%s received message thread=%s msg_id=%d",
                    account.username, thread_id, new_msg.id,
                )

                if can_send_message(account, config, db):
                    process_message.apply_async(args=[account_id, conv.id, new_msg.id])
                else:
                    logger.info(
                        "account=%s daily limit reached, not scheduling reply for thread=%s",
                        account.username, thread_id,
                    )

    except Exception as exc:
        logger.error(
            "poll_account_dms account_id=%d failed (retry %d/%d): %s",
            account_id, self.request.retries, self.max_retries, exc, exc_info=True,
        )
        self.retry(exc=exc, countdown=30)
    finally:
        db.close()


@celery_app.task(name="workers.celery_app.process_message", bind=True, max_retries=2)
def process_message(self, account_id: int, conversation_id: int, message_id: int):
    from database import SessionLocal
    from models.account import Account, BotStatus
    from models.conversation import Conversation
    from models.message import Message, Direction
    from models.stats import BotConfig, DailyStats
    from services.llm import generate_response
    from services.instagram import send_dm
    from services.anti_ban import get_human_delay, can_send_message, pause_for_daily_limit

    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.id == account_id).first()
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        config = db.query(BotConfig).filter(BotConfig.account_id == account_id).first()
        incoming = db.query(Message).filter(Message.id == message_id).first()

        if not all([account, conv, incoming]):
            logger.warning(
                "process_message: missing records account=%s conv=%s msg=%s — aborting",
                account_id, conversation_id, message_id,
            )
            return
        if account.bot_status != BotStatus.active or not conv.bot_active:
            logger.debug(
                "account=%s or conv=%d is inactive, skipping message",
                account_id, conversation_id,
            )
            return
        if config is None:
            logger.error(
                "account=%d has no BotConfig — cannot process message, pausing account",
                account_id,
            )
            account.bot_status = BotStatus.error
            account.pause_reason = "missing_config"
            db.commit()
            return
        if not can_send_message(account, config, db):
            pause_for_daily_limit(account, db)
            return

        delay = get_human_delay(len(incoming.content))
        logger.debug(
            "account=%s sleeping %.1fs before reply to thread=%s",
            account.username, delay, conv.instagram_thread_id,
        )
        time.sleep(delay)

        db.refresh(account)
        if account.bot_status != BotStatus.active:
            logger.info(
                "account=%s status changed to %s during delay, aborting reply",
                account.username, account.bot_status.value,
            )
            return

        response_text, tokens = generate_response(conv, config, db)
        success = send_dm(account, conv.instagram_thread_id, response_text, db)

        if success:
            out_msg = Message(
                conversation_id=conv.id,
                direction=Direction.outgoing,
                content=response_text,
                sent_at=datetime.now(timezone.utc),
                delay_seconds=delay,
                tokens_used=tokens,
            )
            db.add(out_msg)
            account.messages_today += 1
            conv.last_message_at = datetime.now(timezone.utc)
            conv.messages_count += 1

            today = date.today()
            stats = db.query(DailyStats).filter(
                DailyStats.account_id == account_id,
                DailyStats.date == today,
            ).first()
            if not stats:
                stats = DailyStats(account_id=account_id, date=today)
                db.add(stats)
            stats.messages_sent += 1
            stats.tokens_used += tokens
            db.commit()
            logger.info(
                "account=%s replied to thread=%s tokens=%d messages_today=%d",
                account.username, conv.instagram_thread_id, tokens, account.messages_today,
            )

            if not can_send_message(account, config, db):
                pause_for_daily_limit(account, db)
        else:
            logger.warning(
                "account=%s send_dm returned False for thread=%s",
                account.username, conv.instagram_thread_id,
            )

    except Exception as exc:
        logger.error(
            "process_message account_id=%d conv=%d msg=%d failed (retry %d/%d): %s",
            account_id, conversation_id, message_id,
            self.request.retries, self.max_retries, exc, exc_info=True,
        )
        self.retry(exc=exc, countdown=60)
    finally:
        db.close()


@celery_app.task(name="workers.celery_app.reset_daily_limits")
def reset_daily_limits():
    from database import SessionLocal
    from models.account import Account
    from services.anti_ban import check_and_reset_daily_limit

    db = SessionLocal()
    try:
        accounts = db.query(Account).filter(Account.is_active.is_(True)).all()
        logger.debug("reset_daily_limits: checking %d accounts", len(accounts))
        for account in accounts:
            check_and_reset_daily_limit(account, db)
    except Exception as exc:
        logger.error("reset_daily_limits failed: %s", exc, exc_info=True)
    finally:
        db.close()
