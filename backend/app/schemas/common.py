
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import PlainSerializer

# Exact strings from the contract (Section 5.2)
Role = Literal["admin", "inspector"]
ScanStatus = Literal["compliant", "non_compliant", "needs_review"]
RuleStatus = Literal["pass", "fail", "not_checked"]
Severity = Literal["critical", "major", "minor"]
Category = Literal[
    "food", "edible_oil", "beverages", "cosmetics",
    "personal_care", "detergent_household", "other",
]
ReportFormat = Literal["pdf", "docx", "csv"]


def _to_utc_z(value: datetime) -> str:
    """Contract says: ISO 8601, UTC, ending with Z. SQLite returns naive datetimes."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


# Use this type for every timestamp in the API
UtcDatetime = Annotated[datetime, PlainSerializer(_to_utc_z, return_type=str)]