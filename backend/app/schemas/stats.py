
from pydantic import BaseModel, Field

from app.schemas.scan import ScanSummary


class TopRule(BaseModel):
    rule_id: str
    title: str
    count: int


class ViolationPoint(BaseModel):
    date: str  # YYYY-MM-DD
    count: int


class ScanPoint(BaseModel):
    date: str  # YYYY-MM-DD
    total: int
    compliant: int
    non_compliant: int


class CategoryStat(BaseModel):
    category: str
    total: int
    compliant: int
    non_compliant: int


class Stats(BaseModel):
    total_scans: int
    compliant: int
    non_compliant: int
    needs_review: int
    compliance_rate: float
    scans_today: int
    top_violated_rules: list[TopRule] = Field(default_factory=list)
    violations_over_time: list[ViolationPoint] = Field(default_factory=list)
    scans_over_time: list[ScanPoint] = Field(default_factory=list)
    by_category: list[CategoryStat] = Field(default_factory=list)
    recent_scans: list[ScanSummary] = Field(default_factory=list)