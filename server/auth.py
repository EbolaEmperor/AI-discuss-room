# server/auth.py
import os
import base64
import secrets
from typing import Optional
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from server.db import get_db
from server.models import Participant, AdminUser

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
basic_security = HTTPBasic(auto_error=False)


def make_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()


def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_ctx.verify(plain, hashed)
    except Exception:
        return False


def err(code: str, message: str, http: int = 400, details: dict | None = None):
    raise HTTPException(
        status_code=http,
        detail={"error": {"code": code, "message": message, "details": details or {}}},
    )


def require_participant(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Participant:
    if not authorization or not authorization.lower().startswith("bearer "):
        err("auth_missing", "Bearer token required", http=401)
    token = authorization.split(" ", 1)[1].strip()
    p = db.query(Participant).filter(Participant.token == token).one_or_none()
    if not p:
        err("auth_invalid", "Token not recognized", http=401)
    return p


def authenticate_admin(db: Session, username: str, password: str) -> Optional[AdminUser]:
    user = db.query(AdminUser).filter(AdminUser.username == username).one_or_none()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def require_admin_basic(
    credentials: Optional[HTTPBasicCredentials] = Depends(basic_security),
    db: Session = Depends(get_db),
) -> AdminUser:
    """HTTP Basic admin auth — checks admin_users table. Used by CLI endpoints."""
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "auth_missing", "message": "Basic admin auth required"}},
            headers={"WWW-Authenticate": "Basic"},
        )
    user = authenticate_admin(db, credentials.username, credentials.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "auth_invalid", "message": "Bad admin credentials"}},
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


def require_admin_session(
    request: Request,
    db: Session = Depends(get_db),
) -> AdminUser:
    """Session-cookie admin auth — for browser HTML routes."""
    admin_id = request.session.get("admin_id")
    if not admin_id:
        err("auth_missing", "session required", http=401)
    user = db.query(AdminUser).filter(AdminUser.id == admin_id).one_or_none()
    if not user:
        request.session.pop("admin_id", None)
        err("auth_invalid", "session user gone", http=401)
    return user


def current_admin_or_none(request: Request, db: Session) -> Optional[AdminUser]:
    """Look up current session admin without raising — for templates that branch on login state."""
    admin_id = request.session.get("admin_id")
    if not admin_id:
        return None
    return db.query(AdminUser).filter(AdminUser.id == admin_id).one_or_none()


# Backward-compatible alias used by existing admin routes
require_admin = require_admin_basic
