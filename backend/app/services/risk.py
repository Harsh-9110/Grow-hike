import math
from datetime import date
from decimal import Decimal, localcontext

from app.services.accounting import ONE, ZERO


def xirr(flows: list[tuple[date, Decimal]]) -> Decimal | None:
    """Bisection in a bounded domain; None is honest when no supported root exists."""
    if len(flows) < 2 or len({d for d, _ in flows}) < 2:
        return None
    if not any(v < 0 for _, v in flows) or not any(v > 0 for _, v in flows):
        return None
    first = min(d for d, _ in flows)
    with localcontext() as ctx:
        ctx.prec = 40

        def npv(rate):
            return sum((v / ((ONE + rate) ** (Decimal((day - first).days) / 365)) for day, v in flows), ZERO)

        lo, hi = Decimal("-0.9999"), Decimal("1000")
        flo = npv(lo)
        if flo * npv(hi) > 0:
            return None
        for _ in range(180):
            mid = (lo + hi) / 2
            fmid = npv(mid)
            if abs(fmid) < Decimal("0.00000001"):
                return mid
            if flo * fmid > 0:
                lo, flo = mid, fmid
            else:
                hi = mid
        return (lo + hi) / 2


def risk_metrics(values: list[Decimal]) -> dict:
    valid = [v for v in values if v > ZERO]
    if len(valid) < 2 or len(valid) != len(values):
        return {"volatility_pct": None, "max_drawdown_pct": None}
    returns = [float(b / a - ONE) for a, b in zip(valid, valid[1:], strict=False)]
    # These are unitless ratios, never monetary values.
    mean = sum(returns) / len(returns)
    volatility = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)) * math.sqrt(252) * 100 if len(returns) > 1 else None
    peak, drawdown = valid[0], ZERO
    for value in valid:
        peak = max(peak, value)
        drawdown = min(drawdown, value / peak - ONE)
    return {"volatility_pct": volatility, "max_drawdown_pct": str(drawdown * 100)}


