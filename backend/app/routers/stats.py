
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.mock_data import store
from app.models import User
from app.schemas.stats import Stats

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=Stats)
def get_stats(
    date_from: date | None = None,
    date_to: date | None = None,
    user: User = Depends(get_current_user),
):
    visible = store.visible_scans(user)  # admin: all, inspector: own, newest first
    today = datetime.now(timezone.utc).date()

    scans = []
    for s in visible:
        day = s["created_at"].date()
        if date_from and day < date_from:
            continue
        if date_to and day > date_to:
            continue
        scans.append(s)

    total = len(scans)
    compliant = sum(1 for s in scans if s["status"] == "compliant")
    non_compliant = sum(1 for s in scans if s["status"] == "non_compliant")
    needs_review = sum(1 for s in scans if s["status"] == "needs_review")

    titles = {r["rule_id"]: r["title"] for r in store.RULES}
    failures = Counter(
        r["rule_id"] for s in scans for r in s["rule_results"] if r["status"] == "fail"
    )

    violations_by_day = defaultdict(int)
    scans_by_day = defaultdict(lambda: {"total": 0, "compliant": 0, "non_compliant": 0})
    by_category = defaultdict(lambda: {"total": 0, "compliant": 0, "non_compliant": 0})
    for s in scans:
        day = s["created_at"].date().isoformat()
        violations_by_day[day] += s["violations_count"]
        for bucket in (scans_by_day[day], by_category[s["product"]["category"]]):
            bucket["total"] += 1
            if s["status"] == "compliant":
                bucket["compliant"] += 1
            elif s["status"] == "non_compliant":
                bucket["non_compliant"] += 1

    return {
        "total_scans": total,
        "compliant": compliant,
        "non_compliant": non_compliant,
        "needs_review": needs_review,
        "compliance_rate": round(compliant / total * 100, 1) if total else 0.0,
        "scans_today": sum(1 for s in visible if s["created_at"].date() == today),
        "top_violated_rules": [
            {"rule_id": rid, "title": titles.get(rid, rid), "count": n}
            for rid, n in failures.most_common(5)
        ],
        "violations_over_time": [
            {"date": d, "count": n} for d, n in sorted(violations_by_day.items())
        ],
        "scans_over_time": [{"date": d, **v} for d, v in sorted(scans_by_day.items())],
        "by_category": [
            {"category": c, **v}
            for c, v in sorted(by_category.items(), key=lambda kv: -kv[1]["total"])
        ],
        "recent_scans": [store.summary(s) for s in scans[:10]],
    }