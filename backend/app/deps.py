
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import AppError
from app.models import User
from app.security import decode_access_token

# auto_error=False lets us return the contract's error format ourselves
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise AppError(401, "UNAUTHORIZED", "Not logged in")

    payload = decode_access_token(creds.credentials)
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise AppError(401, "UNAUTHORIZED", "Invalid token")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(401, "UNAUTHORIZED", "Account not found or disabled")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise AppError(403, "FORBIDDEN", "You do not have access")
    return user