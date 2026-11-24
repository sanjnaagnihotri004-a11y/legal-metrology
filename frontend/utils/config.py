import os
from dotenv import load_dotenv
load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
USE_MOCK = os.getenv("USE_MOCK", "false").lower() == "true"
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "120"))

CATEGORY_OPTIONS = {
    "Food": "food", "Edible oil": "edible_oil", "Beverages": "beverages",
    "Cosmetics": "cosmetics", "Personal care": "personal_care",
    "Detergent / household": "detergent_household", "Other": "other"
}
STATUS_LABELS = {
    "compliant": "Compliant", "non_compliant": "Non-compliant",
    "needs_review": "Needs review"
}
STATUS_COLORS = {
    "compliant": "#16834A", "non_compliant": "#D64545",
    "needs_review": "#D99018"
}
SEVERITY_COLORS = {"critical": "#D64545", "major": "#E58A24", "minor": "#D5A313"}
