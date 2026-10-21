import hashlib
import secrets
from datetime import timedelta

import bcrypt
import jwt
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import RefreshToken, User
from app.models.entities import uid, utcnow

settings = get_settings()
bearer = HTTPBearer(auto_error=False)
DUMMY_HASH = bcrypt.hashpw(b"not-a-user-password", bcrypt.gensalt()).decode()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, stored: str | None) -> bool:
    return bcrypt.checkpw(password.encode(), (stored or DUMMY_HASH).encode()) and stored is not None


def create_tokens(db: Session, user: User, response: Response, family: str | None = None) -> dict:
    raw, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    family = family or uid()
    now = utcnow()
    db.add(RefreshToken(user_id=user.id, family=family, token_hash=digest(raw), csrf_hash=digest(csrf), expires_at=now + timedelta(days=settings.refresh_days)))
    token = jwt.encode({"sub": user.id, "sid": family, "iss": "grow-hike", "aud": "grow-hike-web", "iat": now, "exp": now + timedelta(minutes=settings.access_minutes)}, settings.jwt_secret, algorithm="HS256")
    common = {"secure": settings.cookie_secure, "samesite": "lax", "max_age": settings.refresh_days * 86400}
    response.set_cookie("gh_refresh", raw, httponly=True, path="/api/auth", **common)
    response.set_cookie("gh_csrf", csrf, httponly=False, path="/", **common)
    response.headers["Cache-Control"] = "no-store"
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "email": user.email}}


def current_user(auth: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    try:
        if auth is None:
            raise ValueError("missing")
        payload = jwt.decode(auth.credentials, settings.jwt_secret, algorithms=["HS256"], issuer="grow-hike", audience="grow-hike-web", options={"require": ["sub", "sid", "exp", "iat"]})
        active = db.scalar(select(RefreshToken.id).where(RefreshToken.family == payload["sid"], RefreshToken.revoked.is_(False), RefreshToken.expires_at > utcnow()).limit(1))
        user = db.get(User, payload["sub"])
        if not user or not active or (user.is_demo and not settings.demo_mode):
            raise ValueError("invalid session")
        # The SSE response may last minutes. Release this identity-check connection now.
        db.expunge(user)
        db.rollback()
        return user
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(401, "Please sign in", headers={"WWW-Authenticate": "Bearer"}) from exc


def require_csrf(request: Request, row: RefreshToken) -> None:
    if request.headers.get("origin") != settings.frontend_url:
        raise HTTPException(403, "Invalid request origin")
    header = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get("gh_csrf", "")
    if not header or not secrets.compare_digest(header, cookie) or not secrets.compare_digest(digest(header), row.csrf_hash):
        raise HTTPException(403, "Invalid CSRF token")


def cipher() -> Fernet:
    if not settings.encryption_key:
        raise HTTPException(503, "Set ENCRYPTION_KEY to enable broker connections")
    return Fernet(settings.encryption_key.encode())
