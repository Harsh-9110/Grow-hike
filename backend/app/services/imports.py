import csv
import io
import zipfile
from itertools import islice
from xml.etree.ElementTree import ParseError
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from openpyxl import load_workbook
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, ImportPreview, LedgerEntry, Portfolio
from app.models.entities import utcnow
from app.schemas.requests import Money, Quantity
from app.services import market

MAX_BYTES = 2 * 1024 * 1024


def read_rows(content: bytes, filename: str) -> list[dict]:
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "Maximum upload is 2 MB")
    try:
        if filename.lower().endswith(".csv"):
            rows = list(islice(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))), 501))
        elif filename.lower().endswith(".xlsx"):
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(i.file_size for i in archive.infolist()) > 15 * 1024 * 1024:
                    raise ValueError("Expanded workbook is too large")
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True, keep_links=False)
            try:
                sheet = workbook.active
                values = iter(sheet.values)
                headers = [str(v).strip() if v is not None else "" for v in next(values)]
                rows = []
                for values_row in values:
                    rows.append(dict(zip(headers, values_row, strict=False)))
                    if len(rows) > 500:
                        raise ValueError("Maximum 500 rows")
            finally:
                workbook.close()
        else:
            raise ValueError("Use CSV or XLSX")
        if not rows or len(rows) > 500:
            raise ValueError("Upload between 1 and 500 rows")
        return rows
    except (ValueError, UnicodeError, zipfile.BadZipFile, StopIteration, KeyError, TypeError, ParseError, OSError) as exc:
        raise HTTPException(422, "Cannot read this file. Use a CSV or XLSX with a header row and up to 500 rows.") from exc


def preview(db: Session, user_id: str, rows: list[dict], mapping: dict, name: str) -> dict:
    from pydantic import BaseModel

    class ImportRow(BaseModel):
        symbol: str
        quantity: Quantity
        average_price: Money

    checked, errors, seen = [], [], set()
    for n, raw in enumerate(rows, 2):
        try:
            obj = ImportRow(symbol=str(raw[mapping["symbol"]]).strip().upper(), quantity=str(raw[mapping["quantity"]]), average_price=str(raw[mapping["average_price"]]))
            instrument = market.instrument_or_404(db, obj.symbol)
            if not instrument.tradable or obj.symbol in seen:
                raise ValueError("Duplicate symbol or non-tradable instrument")
            seen.add(obj.symbol)
            checked.append({"symbol": obj.symbol, "quantity": str(obj.quantity), "average_price": str(obj.average_price), "currency": instrument.currency})
        except (KeyError, ValueError, ValidationError, HTTPException):
            errors.append({"row": n, "message": "Unknown/duplicate symbol, missing column, or invalid positive quantity/average price"})
    if errors:
        return {"valid": False, "errors": errors, "rows": checked, "preview_id": None}
    item = ImportPreview(user_id=user_id, name=name, rows=checked, expires_at=utcnow() + timedelta(minutes=30))
    db.add(item)
    db.commit()
    return {"valid": True, "errors": [], "rows": checked, "preview_id": item.id, "note": "Confirm creates a new read-only portfolio snapshot; it does not merge or modify paper trades. INR cost uses FX at import time."}


def confirm(db: Session, user_id: str, preview_id: str) -> dict:
    item = db.scalar(select(ImportPreview).where(ImportPreview.id == preview_id, ImportPreview.user_id == user_id).with_for_update())
    if not item:
        raise HTTPException(404, "Preview not found")
    if item.portfolio_id:
        return {"portfolio_id": item.portfolio_id, "replayed": True}
    if item.expires_at < utcnow():
        raise HTTPException(410, "Preview expired; upload again")
    fx = market.fx(db) if any(r["currency"] == "USD" for r in item.rows) else {"price": "1", "stale": False}
    if fx["stale"]:
        raise HTTPException(409, "Wait for a fresh FX rate before importing")
    portfolio = Portfolio(user_id=user_id, name=item.name, kind="import")
    db.add(portfolio)
    db.flush()
    for n, row in enumerate(item.rows, 1):
        db.add(LedgerEntry(portfolio_id=portfolio.id, sequence=n, kind="IMPORT", symbol=row["symbol"], quantity=Decimal(row["quantity"]), price=Decimal(row["average_price"]), fx_rate=Decimal(fx["price"]) if row["currency"] == "USD" else Decimal("1"), cash_delta=Decimal("0"), idempotency_key=f"import:{n}", request_hash="import"))
    item.portfolio_id = portfolio.id
    db.add(AuditEvent(user_id=user_id, action="portfolio_import", entity_id=portfolio.id))
    db.commit()
    return {"portfolio_id": portfolio.id, "replayed": False}
