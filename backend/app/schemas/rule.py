
from pydantic import BaseModel, ConfigDict

from app.schemas.common import Severity


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    clause: str
    title: str
    description: str
    severity: Severity
    active: bool