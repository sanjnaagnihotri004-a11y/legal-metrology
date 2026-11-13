
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.errors import AppError
from app.models import User
from app.schemas.user import LoginRequest, LoginResponse, UserBrief
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.strip().lower()).first()

    # Same message for "no such user" and "wrong password", so attackers learn nothing
    if user is None or not verify_password(body.password, user.password_hash):
        raise AppError(401, "INVALID_CREDENTIALS", "Incorrect email or password")
    if not user.is_active:
        raise AppError(401, "INVALID_CREDENTIALS", "This account has been disabled")

    token = create_access_token(user.id, user.role)
    return LoginResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserBrief.model_validate(user),
    )


@router.get("/me", response_model=UserBrief)
def me(user: User = Depends(get_current_user)):
    return user