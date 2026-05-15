from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from database import get_db
from models.stats import DailyStats
from models.conversation import Conversation

router = APIRouter()


@router.get("/stats/{account_id}/daily")
def get_daily_stats(
    account_id: int,
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    since = date.today() - timedelta(days=days - 1)
    stats = (
        db.query(DailyStats)
        .filter(DailyStats.account_id == account_id, DailyStats.date >= since)
        .order_by(DailyStats.date.asc())
        .all()
    )
    return [
        {
            "date": s.date.isoformat(),
            "messages_sent": s.messages_sent,
            "messages_received": s.messages_received,
            "new_conversations": s.new_conversations,
            "conversions": s.conversions,
            "tokens_used": s.tokens_used,
        }
        for s in stats
    ]


@router.get("/stats/{account_id}/summary")
def get_summary(account_id: int, db: Session = Depends(get_db)):
    agg = db.query(
        func.coalesce(func.sum(DailyStats.messages_sent), 0).label("sent"),
        func.coalesce(func.sum(DailyStats.messages_received), 0).label("received"),
        func.coalesce(func.sum(DailyStats.tokens_used), 0).label("tokens"),
    ).filter(DailyStats.account_id == account_id).one()

    total_convs = (
        db.query(func.count(Conversation.id))
        .filter(Conversation.account_id == account_id)
        .scalar()
        or 0
    )
    total_converted = (
        db.query(func.count(Conversation.id))
        .filter(Conversation.account_id == account_id, Conversation.is_converted.is_(True))
        .scalar()
        or 0
    )

    return {
        "total_messages_sent": agg.sent,
        "total_messages_received": agg.received,
        "total_tokens_used": agg.tokens,
        "total_conversations": total_convs,
        "total_conversions": total_converted,
        "conversion_rate_pct": round(total_converted / total_convs * 100, 1) if total_convs else 0.0,
    }
