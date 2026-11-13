
from pathlib import Path

import yaml

from app.db import Base, SessionLocal, engine
from app.models import Rule, User
from app.security import hash_password

RULES_FILE = Path(__file__).resolve().parent.parent / "rules" / "rules.yaml"

DEV_USERS = [
    {"name": "Admin User", "email": "admin@lm.test", "password": "Admin@123", "role": "admin"},
    {"name": "Asha Verma", "email": "inspector@lm.test", "password": "Inspector@123", "role": "inspector"},
]


def seed():
    Base.metadata.create_all(bind=engine)  # creates all tables if missing
    db = SessionLocal()
    try:
        rules = yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))["rules"]
        for r in rules:
            rule = db.get(Rule, r["rule_id"])
            if rule is None:
                db.add(Rule(**r))
            else:
                for key, value in r.items():
                    setattr(rule, key, value)

        for u in DEV_USERS:
            exists = db.query(User).filter(User.email == u["email"]).first()
            if not exists:
                db.add(
                    User(
                        name=u["name"],
                        email=u["email"],
                        password_hash=hash_password(u["password"]),
                        role=u["role"],
                    )
                )
        db.commit()
        print(f"Seed complete: {len(rules)} rules, {len(DEV_USERS)} dev users checked.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()