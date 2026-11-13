
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Rule(Base):
    __tablename__ = "rules"

    rule_id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. "LM-R1"
    clause: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)