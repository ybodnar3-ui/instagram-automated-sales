import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models.account import Account
from models.trigger import Trigger

logger = logging.getLogger(__name__)
router = APIRouter()


class TriggerCreate(BaseModel):
    keyword: str
    response_template: str
    use_ai_followup: bool = False
    is_active: bool = True


class TriggerUpdate(BaseModel):
    keyword: Optional[str] = None
    response_template: Optional[str] = None
    use_ai_followup: Optional[bool] = None
    is_active: Optional[bool] = None


def _get_account_or_404(account_id: int, db: Session) -> Account:
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.get("/triggers/{account_id}")
def list_triggers(account_id: int, db: Session = Depends(get_db)):
    _get_account_or_404(account_id, db)
    triggers = db.query(Trigger).filter(Trigger.account_id == account_id).all()
    return [
        {
            "id": t.id,
            "keyword": t.keyword,
            "response_template": t.response_template,
            "use_ai_followup": t.use_ai_followup,
            "is_active": t.is_active,
            "created_at": t.created_at.isoformat(),
        }
        for t in triggers
    ]


@router.post("/triggers/{account_id}", status_code=201)
def create_trigger(account_id: int, body: TriggerCreate, db: Session = Depends(get_db)):
    _get_account_or_404(account_id, db)
    if not body.keyword.strip():
        raise HTTPException(status_code=422, detail="keyword must not be empty")
    if not body.response_template.strip():
        raise HTTPException(status_code=422, detail="response_template must not be empty")
    trigger = Trigger(
        account_id=account_id,
        keyword=body.keyword.strip(),
        response_template=body.response_template,
        use_ai_followup=body.use_ai_followup,
        is_active=body.is_active,
    )
    db.add(trigger)
    db.commit()
    db.refresh(trigger)
    logger.info("account=%d created trigger id=%d keyword=%r", account_id, trigger.id, trigger.keyword)
    return {
        "id": trigger.id,
        "keyword": trigger.keyword,
        "response_template": trigger.response_template,
        "use_ai_followup": trigger.use_ai_followup,
        "is_active": trigger.is_active,
        "created_at": trigger.created_at.isoformat(),
    }


@router.put("/triggers/{account_id}/{trigger_id}")
def update_trigger(account_id: int, trigger_id: int, body: TriggerUpdate, db: Session = Depends(get_db)):
    _get_account_or_404(account_id, db)
    trigger = db.query(Trigger).filter(Trigger.id == trigger_id, Trigger.account_id == account_id).first()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    if body.keyword is not None:
        if not body.keyword.strip():
            raise HTTPException(status_code=422, detail="keyword must not be empty")
        trigger.keyword = body.keyword.strip()
    if body.response_template is not None:
        if not body.response_template.strip():
            raise HTTPException(status_code=422, detail="response_template must not be empty")
        trigger.response_template = body.response_template
    if body.use_ai_followup is not None:
        trigger.use_ai_followup = body.use_ai_followup
    if body.is_active is not None:
        trigger.is_active = body.is_active
    db.commit()
    db.refresh(trigger)
    logger.info("account=%d updated trigger id=%d", account_id, trigger_id)
    return {
        "id": trigger.id,
        "keyword": trigger.keyword,
        "response_template": trigger.response_template,
        "use_ai_followup": trigger.use_ai_followup,
        "is_active": trigger.is_active,
        "created_at": trigger.created_at.isoformat(),
    }


@router.delete("/triggers/{account_id}/{trigger_id}")
def delete_trigger(account_id: int, trigger_id: int, db: Session = Depends(get_db)):
    _get_account_or_404(account_id, db)
    trigger = db.query(Trigger).filter(Trigger.id == trigger_id, Trigger.account_id == account_id).first()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    db.delete(trigger)
    db.commit()
    logger.info("account=%d deleted trigger id=%d", account_id, trigger_id)
    return {"status": "deleted", "id": trigger_id}
