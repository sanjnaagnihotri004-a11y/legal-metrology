
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import (
    Category, RuleStatus, ScanStatus, Severity, UtcDatetime,
)


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brand: str
    barcode: str | None = None
    category: Category


class InspectorOut(BaseModel):
    id: int
    name: str


class ExtractedField(BaseModel):
    found: bool
    value: str | None = None
    confidence: float | None = None
    bbox: list[int] | None = None  # [x1, y1, x2, y2]


class NetQuantityField(ExtractedField):
    quantity: float | None = None
    unit: str | None = None
    font_height_mm: float | None = None
    min_font_height_mm: float | None = None


class ExtractedFields(BaseModel):
    manufacturer_name_address: ExtractedField
    net_quantity: NetQuantityField
    mrp: ExtractedField
    mfg_date: ExtractedField
    consumer_care: ExtractedField


class RuleResult(BaseModel):
    rule_id: str
    clause: str
    title: str
    description: str
    severity: Severity
    status: RuleStatus
    message: str
    bbox: list[int] | None = None


class EvidenceOut(BaseModel):
    id: int
    scan_id: int
    file_url: str
    note: str | None = None
    uploaded_by: str  # inspector's name
    created_at: UtcDatetime


class Scan(BaseModel):
    """The full Scan object (frontend doc, Section 5.5)."""
    id: int
    product: ProductOut
    inspector: InspectorOut
    created_at: UtcDatetime
    status: ScanStatus
    score: float
    corrected: bool = False
    notes: str | None = None
    label_width_mm: float
    image_width_px: int | None = None
    image_height_px: int | None = None
    image_url: str
    annotated_image_url: str
    ocr_text: str | None = None
    ocr_confidence: float | None = None
    extracted_fields: ExtractedFields
    rule_results: list[RuleResult]
    violations_count: int
    evidence: list[EvidenceOut] = Field(default_factory=list)


class ScanSummary(BaseModel):
    """One row in the history list (GET /scans)."""
    id: int
    product_name: str
    brand: str
    category: Category
    status: ScanStatus
    score: float
    violations_count: int
    inspector_name: str
    created_at: UtcDatetime


class ScanListResponse(BaseModel):
    items: list[ScanSummary]
    total: int
    page: int
    page_size: int


class RecheckRequest(BaseModel):
    corrections: dict[str, str]