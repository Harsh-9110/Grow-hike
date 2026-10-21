"""Pure FIFO accounting. This module deliberately has no database or HTTP dependency."""
from collections import defaultdict, deque
from dataclasses import dataclass, field
from decimal import DefaultContext, Decimal, getcontext
from typing import Any

DefaultContext.prec = 120
getcontext().prec = 120

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass
class Lot:
    quantity: Decimal
    price: Decimal
    fx: Decimal


@dataclass
class Book:
    cash: Decimal = ZERO
    deposits: Decimal = ZERO
    imported_cost: Decimal = ZERO
    realized: Decimal = ZERO
    realized_native: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    lots: dict[str, deque[Lot]] = field(default_factory=lambda: defaultdict(deque))

    def position(self, symbol: str, price: Decimal, fx: Decimal = ONE) -> dict:
        lots = self.lots[symbol]
        qty = sum((lot.quantity for lot in lots), ZERO)
        cost = sum((lot.quantity * lot.price for lot in lots), ZERO)
        base_cost = sum((lot.quantity * lot.price * lot.fx for lot in lots), ZERO)
        value = qty * price
        return {
            "quantity": qty, "average_cost": cost / qty if qty else ZERO,
            "cost": cost, "cost_inr": base_cost, "value": value, "value_inr": value * fx,
            "unrealized": value - cost, "unrealized_inr": value * fx - base_cost,
            "return_pct": (value / cost - ONE) * 100 if cost else ZERO,
        }


def replay(entries: list[Any]) -> Book:
    book = Book()
    for entry in entries:
        book.cash += entry.cash_delta
        if entry.kind == "DEPOSIT":
            book.deposits += entry.cash_delta
        elif entry.kind in ("BUY", "IMPORT"):
            book.lots[entry.symbol].append(Lot(entry.quantity, entry.price, entry.fx_rate))
            if entry.kind == "IMPORT":
                book.imported_cost += entry.quantity * entry.price * entry.fx_rate
        elif entry.kind == "SELL":
            remaining = entry.quantity
            while remaining > ZERO:
                if not book.lots[entry.symbol]:
                    raise ValueError("Ledger invariant violated: sell exceeds holdings")
                lot = book.lots[entry.symbol][0]
                used = min(remaining, lot.quantity)
                book.realized += used * (entry.price * entry.fx_rate - lot.price * lot.fx)
                book.realized_native[entry.symbol] += used * (entry.price - lot.price)
                lot.quantity -= used
                remaining -= used
                if lot.quantity == ZERO:
                    book.lots[entry.symbol].popleft()
    return book
