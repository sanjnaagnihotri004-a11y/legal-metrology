
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now():
    return datetime.now(timezone.utc)


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    status: Mapped[str] = mapped_column(String(20), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    label_width_mm: Mapped[float] = mapped_column(Float)
    image_width_px: Mapped[int | None] = mapped_column()
    image_height_px: Mapped[int | None] = mapped_column()
    image_path: Mapped[str | None] = mapped_column(String(500))
    annotated_path: Mapped[str | None] = mapped_column(String(500))

    ocr_text: Mapped[str | None] = mapped_column(Text)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    extracted_json: Mapped[dict] = mapped_column(JSON, default=dict)
    rule_results_json: Mapped[list] = mapped_column(JSON, default=list)
    violations_count: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)

    product = relationship("Product")
    user = relationship("User")
    violations = relationship(
        "Violation", back_populates="scan", cascade="all, delete-orphan"
    )
    evidence = relationship(
        "Evidence", back_populates="scan", cascade="all, delete-orphan"
    )


class Violation(Base):
    __tablename__ = "violations"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(20), index=True)
    severity: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    bbox_json: Mapped[list | None] = mapped_column(JSON)

    scan = relationship("Scan", back_populates="violations")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    note: Mapped[str | None] = mapped_column(String(300))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    scan = relationship("Scan", back_populates="evidence")