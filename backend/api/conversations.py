import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from models.conversation import Conversation, ConvStage
from models.message import Message

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_STAGES = {s.value for s in ConvStage}


@router.get("/conversations/{account_id}")
def list_conversations(
    account_id: int,
    stage: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    if stage is not None and stage not in VALID_STAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid stage '{stage}'. Must be one of: {', '.join(sorted(VALID_STAGES))}",
        )
    query = db.query(Conversation).filter(Conversation.account_id == account_id)
    if stage:
        query = query.filter(Conversation.stage == stage)
    convs = query.order_by(Conversation.last_message_at.desc()).all()
    return [
        {
            "id": c.id,
            "thread_id": c.instagram_thread_id,
            "username": c.interlocutor_username,
            "stage": c.stage.value,
            "messages_count": c.messages_count,
            "is_converted": c.is_converted,
            "bot_active": c.bot_active,
            "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
        }
        for c in convs
    ]


@router.get("/conversations/{account_id}/{thread_id}")
def get_conversation(account_id: int, thread_id: str, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(
        Conversation.account_id == account_id,
        Conversation.instagram_thread_id == thread_id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.sent_at.asc())
        .all()
    )
    return {
        "conversation": {
            "id": conv.id,
            "thread_id": conv.instagram_thread_id,
            "username": conv.interlocutor_username,
            "stage": conv.stage.value,
            "bot_active": conv.bot_active,
            "is_converted": conv.is_converted,
        },
        "messages": [
            {
                "id": m.id,
                "direction": m.direction.value,
                "content": m.content,
                "sent_at": m.sent_at.isoformat(),
                "delay_seconds": m.delay_seconds,
            }
            for m in msgs
        ],
    }


@router.post("/conversations/{thread_id}/takeover")
def takeover_conversation(thread_id: str, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(
        Conversation.instagram_thread_id == thread_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.bot_active = False
    db.commit()
    logger.info("thread=%s taken over by human", thread_id)
    return {"status": "taken_over", "thread_id": thread_id}


@router.post("/conversations/{thread_id}/restore")
def restore_bot(thread_id: str, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(
        Conversation.instagram_thread_id == thread_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.bot_active = True
    db.commit()
    logger.info("thread=%s bot restored", thread_id)
    return {"status": "restored", "thread_id": thread_id}
