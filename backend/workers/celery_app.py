import logging
import random
import time
from datetime import datetime, timezone
from celery import Celery
from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import update as sa_update
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
        "send-outbound-messages-hourly": {
            "task": "workers.celery_app.send_outbound_messages",
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
        try:
            self.retry(exc=exc, countdown=30)
        except MaxRetriesExceededError:
            logger.error("poll_all_accounts exhausted all retries — giving up")
    finally:
        db.close()


def _normalize_ts(ts) -> datetime:
    """Return a timezone-aware UTC datetime regardless of whether ts is naive or aware."""
    if ts is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if hasattr(ts, 'tzinfo') and ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _get_or_create_daily_stats(db, account_id: int):
    from models.stats import DailyStats
    from sqlalchemy.exc import IntegrityError
    today = datetime.now(timezone.utc).date()
    stats = db.query(DailyStats).filter(
        DailyStats.account_id == account_id,
        DailyStats.date == today,
    ).first()
    if not stats:
        try:
            stats = DailyStats(account_id=account_id, date=today)
            db.add(stats)
            db.commit()
            db.refresh(stats)
        except IntegrityError:
            # Another worker beat us — roll back and fetch the existing row
            db.rollback()
            stats = db.query(DailyStats).filter(
                DailyStats.account_id == account_id,
                DailyStats.date == today,
            ).first()
            logger.debug("_get_or_create_daily_stats: concurrent insert resolved for account_id=%d", account_id)
    return stats


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
                # Atomic increment filtered by account_id AND today's date to avoid corrupting historical rows
                _get_or_create_daily_stats(db, account_id)
                db.execute(
                    sa_update(DailyStats)
                    .where(DailyStats.account_id == account_id, DailyStats.date == datetime.now(timezone.utc).date())
                    .values(new_conversations=DailyStats.new_conversations + 1)
                )
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
            if viewer_id is None:
                logger.warning(
                    "account=%s thread=%s has no viewer_id — session may be invalid, skipping",
                    account.username, thread_id,
                )
                continue

            for msg in thread.messages:
                if msg.user_id == viewer_id:
                    continue

                msg_sent_at = _normalize_ts(msg.timestamp)

                if msg_sent_at <= last_msg_ts:
                    continue

                text = msg.text or ""
                if not text.strip():
                    # Media messages (photos, videos, reactions) have no text —
                    # skip to avoid calling the LLM with an empty message.
                    logger.debug(
                        "account=%s thread=%s skipping media/empty message from user_id=%s",
                        account.username, thread_id, msg.user_id,
                    )
                    continue

                new_msg = Message(
                    conversation_id=conv.id,
                    direction=Direction.incoming,
                    content=text,
                    sent_at=msg_sent_at,
                )
                db.add(new_msg)
                conv.last_message_at = msg_sent_at
                db.commit()
                db.refresh(new_msg)
                logger.info(
                    "account=%s received message thread=%s msg_id=%d",
                    account.username, thread_id, new_msg.id,
                )

                # Ensure today's stats row exists BEFORE any uncommitted UPDATEs.
                # _get_or_create may rollback on IntegrityError (concurrent worker) —
                # calling it here means nothing pending is lost if that happens.
                _get_or_create_daily_stats(db, account_id)
                db.execute(
                    sa_update(Conversation)
                    .where(Conversation.id == conv.id)
                    .values(messages_count=Conversation.messages_count + 1)
                )
                db.execute(
                    sa_update(DailyStats)
                    .where(DailyStats.account_id == account_id, DailyStats.date == datetime.now(timezone.utc).date())
                    .values(messages_received=DailyStats.messages_received + 1)
                )
                db.commit()

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
        try:
            self.retry(exc=exc, countdown=30)
        except MaxRetriesExceededError:
            logger.error("poll_account_dms account_id=%d exhausted all retries — giving up", account_id)
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
                "account=%d has no BotConfig — cannot process message, marking error",
                account_id,
            )
            account.bot_status = BotStatus.error
            account.pause_reason = "missing_config"
            db.commit()
            return
        if not can_send_message(account, config, db):
            pause_for_daily_limit(account, db)
            return

        # Pass config so min/max_delay_sec from Settings page are respected
        delay = get_human_delay(len(incoming.content), config)
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

        # --- Trigger matching ---
        from models.trigger import Trigger
        from services.instagram import fetch_user_info

        triggers = db.query(Trigger).filter(
            Trigger.account_id == account_id,
            Trigger.is_active.is_(True),
        ).all()

        matched_trigger = None
        incoming_lower = incoming.content.lower().strip()
        for trigger in triggers:
            if trigger.keyword.lower().strip() in incoming_lower:
                matched_trigger = trigger
                break

        if matched_trigger:
            user_info = fetch_user_info(conv.interlocutor_username or "", account, db)
            full_name = user_info.get("full_name", conv.interlocutor_username or "")
            try:
                trigger_text = matched_trigger.response_template.format(
                    username=conv.interlocutor_username or "",
                    full_name=full_name,
                )
            except KeyError:
                trigger_text = matched_trigger.response_template

            trig_success = send_dm(account, conv.instagram_thread_id, trigger_text, db)
            if trig_success:
                trig_msg = Message(
                    conversation_id=conv.id,
                    direction=Direction.outgoing,
                    content=trigger_text,
                    sent_at=datetime.now(timezone.utc),
                    delay_seconds=delay,
                    tokens_used=0,
                )
                db.add(trig_msg)
                conv.last_message_at = datetime.now(timezone.utc)
                db.commit()
                # Ensure stats row exists BEFORE uncommitted UPDATEs so a rollback on
                # IntegrityError (concurrent worker) can't silently drop the counter updates.
                _get_or_create_daily_stats(db, account_id)
                db.execute(
                    sa_update(Conversation)
                    .where(Conversation.id == conv.id)
                    .values(messages_count=Conversation.messages_count + 1)
                )
                db.execute(
                    sa_update(Account)
                    .where(Account.id == account_id)
                    .values(messages_today=Account.messages_today + 1)
                )
                db.execute(
                    sa_update(DailyStats)
                    .where(DailyStats.account_id == account_id, DailyStats.date == datetime.now(timezone.utc).date())
                    .values(messages_sent=DailyStats.messages_sent + 1)
                )
                db.commit()
                db.refresh(account)
                logger.info(
                    "account=%s trigger id=%d fired for thread=%s",
                    account.username, matched_trigger.id, conv.instagram_thread_id,
                )
                if not matched_trigger.use_ai_followup:
                    return
                # If use_ai_followup is True, fall through to AI response below
            else:
                return  # send failed

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
            conv.last_message_at = datetime.now(timezone.utc)
            db.commit()

            # Ensure stats row exists BEFORE uncommitted UPDATEs.
            _get_or_create_daily_stats(db, account_id)
            db.execute(
                sa_update(Conversation)
                .where(Conversation.id == conv.id)
                .values(messages_count=Conversation.messages_count + 1)
            )
            db.execute(
                sa_update(Account)
                .where(Account.id == account_id)
                .values(messages_today=Account.messages_today + 1)
            )
            db.execute(
                sa_update(DailyStats)
                .where(DailyStats.account_id == account_id, DailyStats.date == datetime.now(timezone.utc).date())
                .values(
                    messages_sent=DailyStats.messages_sent + 1,
                    tokens_used=DailyStats.tokens_used + tokens,
                )
            )
            db.commit()

            # Re-read updated messages_today for accurate logging
            db.refresh(account)
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
        import anthropic as _anthropic
        is_rate_limit = isinstance(exc, _anthropic.RateLimitError)
        is_api_err = isinstance(exc, (_anthropic.APIStatusError, _anthropic.APIConnectionError))

        if is_rate_limit:
            logger.warning(
                "process_message account_id=%d conv=%d: Anthropic rate limit — will retry",
                account_id, conversation_id,
            )
        else:
            logger.error(
                "process_message account_id=%d conv=%d msg=%d failed (retry %d/%d): %s",
                account_id, conversation_id, message_id,
                self.request.retries, self.max_retries, exc, exc_info=True,
            )
        try:
            countdown = 120 if is_rate_limit else 60
            self.retry(exc=exc, countdown=countdown)
        except MaxRetriesExceededError:
            # Don't kill the account for transient LLM errors — only for Instagram errors
            if is_rate_limit or is_api_err:
                logger.error(
                    "process_message account_id=%d conv=%d: LLM error exhausted retries — skipping message (account stays active)",
                    account_id, conversation_id,
                )
            else:
                logger.error(
                    "process_message account_id=%d conv=%d msg=%d exhausted retries — marking account error",
                    account_id, conversation_id, message_id,
                )
                from database import SessionLocal as _SL
                from models.account import Account as _Acct, BotStatus as _BS
                _db = _SL()
                try:
                    _acct = _db.query(_Acct).filter(_Acct.id == account_id).first()
                    if _acct and _acct.bot_status == _BS.active:
                        _acct.bot_status = _BS.error
                        _acct.pause_reason = "worker_max_retries_exceeded"
                        _db.commit()
                finally:
                    _db.close()
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
            try:
                check_and_reset_daily_limit(account, db)
            except Exception as exc:
                logger.error("reset_daily_limits: account=%s failed: %s", account.username, exc, exc_info=True)
    except Exception as exc:
        logger.error("reset_daily_limits failed: %s", exc, exc_info=True)
    finally:
        db.close()


@celery_app.task(name="workers.celery_app.send_outbound_messages")
def send_outbound_messages():
    """
    Scheduler: picks pending outbound targets and dispatches each as an
    individual send_single_outbound task with a random countdown jitter.
    Does NOT block — no time.sleep() here.
    """
    from database import SessionLocal
    from models.account import Account, BotStatus
    from models.outbound import OutboundTarget, OutboundStatus
    from models.stats import BotConfig

    db = SessionLocal()
    try:
        accounts = db.query(Account).filter(
            Account.bot_status == BotStatus.active,
            Account.is_active.is_(True),
        ).all()

        for account in accounts:
            try:
                config = db.query(BotConfig).filter(BotConfig.account_id == account.id).first()
                if config is None:
                    continue

                today = datetime.now(timezone.utc).date()
                today_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
                sent_today = db.query(OutboundTarget).filter(
                    OutboundTarget.account_id == account.id,
                    OutboundTarget.status == OutboundStatus.sent,
                    OutboundTarget.sent_at >= today_start,
                ).count()

                remaining = config.outbound_daily_limit - sent_today
                if remaining <= 0:
                    logger.debug("account=%s outbound daily limit reached (%d)", account.username, config.outbound_daily_limit)
                    continue

                targets = db.query(OutboundTarget).filter(
                    OutboundTarget.account_id == account.id,
                    OutboundTarget.status == OutboundStatus.pending,
                ).limit(remaining).all()

                logger.debug(
                    "account=%s outbound: %d pending, %d remaining today",
                    account.username, len(targets), remaining,
                )

                for i, target in enumerate(targets):
                    # Stagger sends: each target gets an independent jitter so they
                    # don't all fire at once and don't block the scheduler worker.
                    countdown = random.randint(60, 300) + i * 60
                    send_single_outbound.apply_async(args=[account.id, target.id], countdown=countdown)
                    logger.info(
                        "account=%s scheduled outbound target_id=%d @%s in %ds",
                        account.username, target.id, target.instagram_username, countdown,
                    )
            except Exception as exc:
                logger.error("send_outbound_messages: account=%s failed: %s", account.username, exc, exc_info=True)
    except Exception as exc:
        logger.error("send_outbound_messages failed: %s", exc, exc_info=True)
    finally:
        db.close()


@celery_app.task(name="workers.celery_app.send_single_outbound", bind=True, max_retries=2)
def send_single_outbound(self, account_id: int, target_id: int):
    from database import SessionLocal
    from models.account import Account, BotStatus
    from models.conversation import Conversation, ConvStage
    from models.outbound import OutboundTarget, OutboundStatus
    from models.stats import BotConfig, DailyStats
    from services.instagram import send_outbound_dm
    from services.anti_ban import can_send_message

    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.id == account_id).first()
        target = db.query(OutboundTarget).filter(OutboundTarget.id == target_id).first()
        config = db.query(BotConfig).filter(BotConfig.account_id == account_id).first()

        if not account or not target or not config:
            logger.warning("send_single_outbound: missing records account=%s target=%s", account_id, target_id)
            return

        if target.status != OutboundStatus.pending:
            logger.debug("send_single_outbound: target_id=%d already %s, skipping", target_id, target.status.value)
            return

        if account.bot_status != BotStatus.active or not can_send_message(account, config, db):
            logger.info("account=%s cannot send outbound (limit or paused), skipping target_id=%d", account.username, target_id)
            return

        message = target.initial_message or config.outbound_default_message
        if not message or not message.strip():
            target.status = OutboundStatus.skipped
            target.error_message = "No message configured"
            db.commit()
            logger.warning("account=%s target_id=%d skipped — no message", account.username, target_id)
            return

        today = datetime.now(timezone.utc).date()
        thread_id = send_outbound_dm(account, target.instagram_username, message, db)
        if thread_id:
            target.status = OutboundStatus.sent
            target.sent_at = datetime.now(timezone.utc)
            db.commit()

            existing_conv = db.query(Conversation).filter(
                Conversation.account_id == account_id,
                Conversation.instagram_thread_id == thread_id,
            ).first()
            if not existing_conv:
                conv = Conversation(
                    account_id=account_id,
                    instagram_thread_id=thread_id,
                    interlocutor_username=target.instagram_username,
                    stage=ConvStage.new,
                    last_message_at=datetime.now(timezone.utc),
                    messages_count=1,
                )
                db.add(conv)
                db.commit()

            # Ensure stats row exists BEFORE uncommitted UPDATEs.
            _get_or_create_daily_stats(db, account_id)
            db.execute(
                sa_update(Account)
                .where(Account.id == account_id)
                .values(messages_today=Account.messages_today + 1)
            )
            db.execute(
                sa_update(DailyStats)
                .where(DailyStats.account_id == account_id, DailyStats.date == today)
                .values(messages_sent=DailyStats.messages_sent + 1)
            )
            db.commit()
            logger.info("account=%s outbound DM sent to @%s thread=%s", account.username, target.instagram_username, thread_id)
        else:
            target.status = OutboundStatus.failed
            target.error_message = "send_outbound_dm returned None"
            db.commit()
            logger.warning("account=%s outbound DM failed for @%s target_id=%d", account.username, target.instagram_username, target_id)

    except Exception as exc:
        logger.error("send_single_outbound account=%s target=%s failed: %s", account_id, target_id, exc, exc_info=True)
        try:
            self.retry(exc=exc, countdown=120)
        except Exception:
            db2 = None
            try:
                from database import SessionLocal as _SL
                db2 = _SL()
                t = db2.query(OutboundTarget).filter(OutboundTarget.id == target_id).first()
                if t and t.status == OutboundStatus.pending:
                    t.status = OutboundStatus.failed
                    t.error_message = f"Worker error: {type(exc).__name__}"
                    db2.commit()
            finally:
                if db2:
                    db2.close()
    finally:
        db.close()
