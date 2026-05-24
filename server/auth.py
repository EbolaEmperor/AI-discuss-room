# server/auth.py
import os
import base64
import secrets
from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from server.db import get_db
from server.models import Participant

ADMIN_USER = os.environ.get("DISCUSS_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("DISCUSS_ADMIN_PASS", "admin")

basic_security = HTTPBasic()


def make_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()


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


def require_admin(credentials: HTTPBasicCredentials = Depends(basic_security)):
    if not (secrets.compare_digest(credentials.username, ADMIN_USER)
            and secrets.compare_digest(credentials.password, ADMIN_PASS)):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "auth_invalid", "message": "Bad admin credentials"}},
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
