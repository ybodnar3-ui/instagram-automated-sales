import random
import time
from datetime import datetime, timezone, date
from celery import Celery
from config import settings

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
        for account in accounts:
            jitter = random.randint(0, 60)
            poll_account_dms.apply_async(args=[account.id], countdown=jitter)
    except Exception as exc:
        self.retry(exc=exc, countdown=30)
    finally:
        db.close()


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
        if not account or account.bot_status != BotStatus.active:
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
                conv = Conversation(
                    account_id=account_id,
                    instagram_thread_id=thread_id,
                    interlocutor_username=thread.users[0].username if thread.users else "unknown",
                    started_at=datetime.now(timezone.utc),
                )
                db.add(conv)
                db.commit()
                db.refresh(conv)

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

            viewer_id = thread.viewer_id
            for msg in thread.messages:
                if msg.user_id == viewer_id:
                    continue

                msg_sent_at = msg.timestamp
                if hasattr(msg_sent_at, 'tzinfo') and msg_sent_at.tzinfo is None:
                    from datetime import timezone as tz
                    msg_sent_at = msg_sent_at.replace(tzinfo=tz.utc)

                if last_msg is not None and msg_sent_at <= last_msg.sent_at:
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

                if can_send_message(account, config, db):
                    process_message.apply_async(args=[account_id, conv.id, new_msg.id])

    except Exception as exc:
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
            return
        if account.bot_status != BotStatus.active or not conv.bot_active:
            return
        if not can_send_message(account, config, db):
            pause_for_daily_limit(account, db)
            return

        delay = get_human_delay(len(incoming.content))
        time.sleep(delay)

        db.refresh(account)
        if account.bot_status != BotStatus.active:
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

            if not can_send_message(account, config, db):
                pause_for_daily_limit(account, db)

    except Exception as exc:
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
        for account in accounts:
            check_and_reset_daily_limit(account, db)
    finally:
        db.close()
