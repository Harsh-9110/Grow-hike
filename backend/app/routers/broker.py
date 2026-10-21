import hashlib
import json
from decimal import Decimal
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AuditEvent, BrokerConnection, User
from app.services.cache import redis
from app.services.imports import preview
from app.services.security import cipher, current_user

router = APIRouter(prefix="/broker", tags=["Read-only broker holdings"])
settings = get_settings()


def start(user: User = Depends(current_user)):
    cipher()
    if not settings.kite_api_key or not settings.kite_api_secret:
        raise HTTPException(503, "Configure Kite API credentials and callback URL first")
    state = secrets.token_urlsafe(32)
    redis.set(f"kite:{state}", user.id, ex=300)
    return {"url": "https://kite.zerodha.com/connect/login?" + urlencode({"v": "3", "api_key": settings.kite_api_key, "redirect_params": urlencode({"state": state})}), "state": state}


@router.get("/kite/callback")
def callback(request: Request, request_token: str, state: str, db: Session = Depends(get_db)):
    expected = request.cookies.get("gh_kite", "")
    if not expected or not secrets.compare_digest(expected, state):
        raise HTTPException(400, "Broker state mismatch")
    user_id = redis.getdel(f"kite:{state}")
    if not user_id:
        raise HTTPException(400, "Broker session expired")
    checksum = hashlib.sha256((settings.kite_api_key + request_token + settings.kite_api_secret).encode()).hexdigest()
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post("https://api.kite.trade/session/token", headers={"X-Kite-Version": "3"}, data={"api_key": settings.kite_api_key, "request_token": request_token, "checksum": checksum})
            response.raise_for_status()
        access = json.loads(response.text, parse_float=Decimal)["data"]["access_token"]
        encrypted = cipher().encrypt(access.encode()).decode()
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(502, "Broker authorization failed") from exc
    connection = db.get(BrokerConnection, user_id)
    if connection:
        connection.encrypted_token = encrypted
    else:
        db.add(BrokerConnection(user_id=user_id, encrypted_token=encrypted))
    db.add(AuditEvent(user_id=user_id, action="broker_connected"))
    db.commit()
    result = RedirectResponse(settings.frontend_url + "/?page=import&broker=connected", status_code=303)
    result.delete_cookie("gh_kite", path="/api/broker")
    return result


@router.post("/kite/authorize")
def authorize(response: Response, user: User = Depends(current_user)):
    result = start(user)
    response.set_cookie("gh_kite", result["state"], max_age=300, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/api/broker")
    return {"url": result["url"]}


@router.get("/kite/status")
def status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"connected": db.get(BrokerConnection, user.id) is not None, "note": "Holdings access only in this app. Kite tokens normally expire at 06:00 IST the next day; reconnect when expired. The app never calls broker order endpoints."}


@router.post("/kite/preview")
def holdings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    connection = db.get(BrokerConnection, user.id)
    if not connection:
        raise HTTPException(409, "Connect a broker account first")
    try:
        token = cipher().decrypt(connection.encrypted_token.encode()).decode()
        with httpx.Client(timeout=10) as client:
            response = client.get("https://api.kite.trade/portfolio/holdings", headers={"X-Kite-Version": "3", "Authorization": f"token {settings.kite_api_key}:{token}"})
            response.raise_for_status()
        rows = []
        for row in json.loads(response.text, parse_float=Decimal)["data"]:
            if row.get("quantity", 0) <= 0:
                continue
            # BSE uses a different Yahoo code; only explicit catalogue mappings are accepted.
            if row["exchange"] != "NSE":
                raise HTTPException(422, "This broker import supports NSE holdings only. Import other holdings by CSV with the Yahoo symbol.")
            rows.append({"symbol": row["tradingsymbol"] + ".NS", "quantity": str(row["quantity"]), "average_price": str(row["average_price"])})
        if not rows:
            raise HTTPException(422, "No supported holdings returned")
        return preview(db, user.id, rows, {"symbol": "symbol", "quantity": "quantity", "average_price": "average_price"}, "Kite holdings snapshot")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(409, "Broker session expired or access unavailable. Reconnect Kite.") from exc
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(502, "Unable to read broker holdings") from exc


@router.delete("/kite", status_code=204)
def disconnect(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(BrokerConnection).where(BrokerConnection.user_id == user.id))
    db.add(AuditEvent(user_id=user.id, action="broker_disconnected"))
    db.commit()
