import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models.account import Account
from models.outbound import OutboundTarget, OutboundStatus

logger = logging.getLogger(__name__)
router = APIRouter()


class OutboundTargetCreate(BaseModel):
    instagram_username: str
    initial_message: Optional[str] = None


def _get_account_or_404(account_id: int, db: Session) -> Account:
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


def _serialize(t: OutboundTarget) -> dict:
    return {
        "id": t.id,
        "instagram_username": t.instagram_username,
        "initial_message": t.initial_message,
        "status": t.status.value,
        "scheduled_at": t.scheduled_at.isoformat(),
        "sent_at": t.sent_at.isoformat() if t.sent_at else None,
        "error_message": t.error_message,
        "created_at": t.created_at.isoformat(),
    }


@router.get("/outbound/{account_id}")
def list_outbound_targets(account_id: int, db: Session = Depends(get_db)):
    _get_account_or_404(account_id, db)
    targets = (
        db.query(OutboundTarget)
        .filter(OutboundTarget.account_id == account_id)
        .order_by(OutboundTarget.created_at.desc())
        .all()
    )
    return [_serialize(t) for t in targets]


@router.post("/outbound/{account_id}", status_code=201)
def add_outbound_target(account_id: int, body: OutboundTargetCreate, db: Session = Depends(get_db)):
    _get_account_or_404(account_id, db)
    username = body.instagram_username.strip().lstrip("@")
    if not username:
        raise HTTPException(status_code=422, detail="instagram_username must not be empty")
    target = OutboundTarget(
        account_id=account_id,
        instagram_username=username,
        initial_message=body.initial_message,
        status=OutboundStatus.pending,
        scheduled_at=datetime.now(timezone.utc),
    )
    db.add(target)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.error("account=%d failed to add outbound target @%s", account_id, username, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save outbound target")
    db.refresh(target)
    logger.info("account=%d added outbound target @%s id=%d", account_id, username, target.id)
    return _serialize(target)


@router.delete("/outbound/{account_id}/{target_id}")
def delete_outbound_target(account_id: int, target_id: int, db: Session = Depends(get_db)):
    _get_account_or_404(account_id, db)
    target = db.query(OutboundTarget).filter(
        OutboundTarget.id == target_id,
        OutboundTarget.account_id == account_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    db.delete(target)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.error("account=%d failed to delete outbound target id=%d", account_id, target_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete outbound target")
    logger.info("account=%d deleted outbound target id=%d", account_id, target_id)
    return {"status": "deleted", "id": target_id}
