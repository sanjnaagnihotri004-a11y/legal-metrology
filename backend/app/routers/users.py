
import re

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.errors import AppError
from app.models import User
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return db.query(User).order_by(User.id).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise AppError(422, "VALIDATION_ERROR", "Some inputs are invalid",
                       {"email": "must be a valid email address"})
    if db.query(User).filter(User.email == email).first():
        raise AppError(422, "VALIDATION_ERROR", "Some inputs are invalid",
                       {"email": "already registered"})

    user = User(
        name=body.name.strip(),
        email=email,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise AppError(404, "NOT_FOUND", "User not found")

    if user.id == admin.id:
        if body.is_active is False:
            raise AppError(422, "VALIDATION_ERROR", "You cannot disable your own account",
                           {"is_active": "cannot disable yourself"})
        if body.role is not None and body.role != "admin":
            raise AppError(422, "VALIDATION_ERROR", "You cannot remove your own admin role",
                           {"role": "cannot demote yourself"})

    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    db.commit()
    db.refresh(user)
    return user