import secrets
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AuditEvent, RefreshToken, User
from app.models.entities import utcnow
from app.schemas.requests import Credentials
from app.services.cache import limit, redis
from app.services.security import create_tokens, current_user, digest, password_hash, require_csrf, verify_password

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


def create_paper_portfolio(db: Session, user_id: str):
    from decimal import Decimal
    from app.models import LedgerEntry, Portfolio
    p = Portfolio(user_id=user_id, name="Paper portfolio", kind="paper")
    db.add(p)
    db.flush()
    db.add(LedgerEntry(portfolio_id=p.id, sequence=1, kind="DEPOSIT", quantity=Decimal("0"), price=Decimal("0"), fx_rate=Decimal("1"), cash_delta=Decimal("1000000"), idempotency_key="initial-deposit", request_hash="initial-deposit"))
    return p


def auth_limit(request: Request, email: str = ""):
    ip = request.client.host if request.client else "unknown"
    limit("login-ip", ip, 20, 300)
    if email:
        limit("login-account", email.lower(), 10, 300)


@router.post("/register", status_code=201)
def register(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    auth_limit(request, str(body.email))
    user = User(email=str(body.email).lower(), password_hash=password_hash(body.password))
    db.add(user)
    try:
        db.flush()
        create_paper_portfolio(db, user.id)
        result = create_tokens(db, user, response)
        db.add(AuditEvent(user_id=user.id, action="register"))
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Unable to register this email") from exc


@router.post("/login")
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    auth_limit(request, str(body.email))
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    if not verify_password(body.password, user.password_hash if user else None) or (user and user.is_demo and not settings.demo_mode):
        raise HTTPException(401, "Invalid email or password")
    result = create_tokens(db, user, response)
    db.add(AuditEvent(user_id=user.id, action="login"))
    db.commit()
    return result


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get("gh_refresh", "")
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest(raw)).with_for_update())
    if not row:
        raise HTTPException(401, "Please sign in again")
    require_csrf(request, row)
    if row.revoked:
        # Reusing a rotated token revokes its whole session, including issued access tokens.
        db.execute(update(RefreshToken).where(RefreshToken.family == row.family).values(revoked=True))
        db.commit()
        raise HTTPException(401, "Session replay detected; sign in again")
    if row.expires_at <= utcnow():
        raise HTTPException(401, "Session expired")
    row.revoked = True
    result = create_tokens(db, db.get(User, row.user_id), response, row.family)
    db.commit()
    return result


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest(request.cookies.get("gh_refresh", ""))).with_for_update())
    if row:
        require_csrf(request, row)
        db.execute(update(RefreshToken).where(RefreshToken.family == row.family).values(revoked=True))
        db.add(AuditEvent(user_id=row.user_id, action="logout"))
        db.commit()
    response.delete_cookie("gh_refresh", path="/api/auth", secure=settings.cookie_secure, samesite="lax")
    response.delete_cookie("gh_csrf", path="/", secure=settings.cookie_secure, samesite="lax")


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email}


@router.get("/google/start")
def google_start(request: Request):
    auth_limit(request)
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(503, "Configure Google OAuth credentials first")
    state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    import base64
    import hashlib
    import json
    redis.set(f"google:{state}", json.dumps({"nonce": nonce, "verifier": verifier}), ex=300)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {"client_id": settings.google_client_id, "redirect_uri": settings.backend_url + "/api/auth/google/callback", "response_type": "code", "scope": "openid email profile", "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"}
    response = RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))
    response.set_cookie("gh_oauth", state, max_age=300, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/api/auth/google")
    return response


@router.get("/google/callback")
def google_callback(request: Request, code: str, state: str, db: Session = Depends(get_db)):
    import json
    expected = request.cookies.get("gh_oauth", "")
    if not expected or not secrets.compare_digest(expected, state):
        raise HTTPException(400, "OAuth state mismatch")
    raw = redis.getdel(f"google:{state}")
    if not raw:
        raise HTTPException(400, "OAuth session expired")
    saved = json.loads(raw)
    try:
        with httpx.Client(timeout=10) as client:
            r = client.post("https://oauth2.googleapis.com/token", data={"code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret, "redirect_uri": settings.backend_url + "/api/auth/google/callback", "grant_type": "authorization_code", "code_verifier": saved["verifier"]})
            r.raise_for_status()
        token = r.json()["id_token"]
        jwks = jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs", cache_keys=True)
        claims = jwt.decode(token, jwks.get_signing_key_from_jwt(token).key, algorithms=["RS256"], audience=settings.google_client_id, issuer="https://accounts.google.com", options={"require": ["sub", "email", "exp", "nonce"]})
        if claims["nonce"] != saved["nonce"] or claims.get("email_verified") is not True:
            raise ValueError("Invalid identity")
    except (httpx.HTTPError, jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(400, "Unable to verify Google sign-in") from exc
    user = db.scalar(select(User).where(User.google_sub == claims["sub"]))
    if not user:
        if db.scalar(select(User.id).where(User.email == claims["email"].lower())):
            raise HTTPException(409, "Email already registered. Use your password to sign in.")
        user = User(email=claims["email"].lower(), google_sub=claims["sub"])
        db.add(user)
        db.flush()
        create_paper_portfolio(db, user.id)
    response = RedirectResponse(settings.frontend_url + "/oauth/callback", status_code=303)
    create_tokens(db, user, response)
    response.delete_cookie("gh_oauth", path="/api/auth/google")
    db.add(AuditEvent(user_id=user.id, action="google_login"))
    db.commit()
    return response
