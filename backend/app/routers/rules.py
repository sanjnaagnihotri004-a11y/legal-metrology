
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Rule, User
from app.schemas.rule import RuleOut

router = APIRouter(tags=["rules"])


@router.get("/rules", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Rule).order_by(Rule.rule_id).all()