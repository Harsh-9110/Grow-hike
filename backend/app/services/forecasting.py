"""Experimental CPU LSTM. Train on past data only, evaluate identical multi-day horizons."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert

from app.db import SessionLocal
from app.models import Forecast
from app.services import market


def train_evaluate(points: list[dict], epochs: int = 25, demo: bool = False) -> dict:
    import math
    import numpy as np
    import torch
    from torch import nn

    torch.manual_seed(42)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    prices = [Decimal(p["close"]) for p in points]
    if len(prices) < 320:
        raise ValueError("At least 320 daily closes are required for walk-forward evaluation")
    window, horizons = 20, [1, 3, 5]

    class LSTM(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(1, 16, batch_first=True)
            self.head = nn.Linear(16, 1)

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.head(out[:, -1]).squeeze(-1)

    def fit_predict(train: list[Decimal]) -> list[Decimal]:
        # Tensor inputs are unitless price ratios. Monetary anchors remain Decimal.
        anchor = train[-1]
        ratios = np.array([float(p / anchor) for p in train], dtype=np.float32)
        mean, std = float(ratios.mean()), max(float(ratios.std()), 1e-6)
        normalized = (ratios - mean) / std
        x = torch.tensor(np.array([normalized[n-window:n] for n in range(window, len(train))])).unsqueeze(-1)
        y = torch.tensor(normalized[window:])
        torch.manual_seed(42)
        model = LSTM()
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        model.train()
        for _ in range(epochs):
            optimizer.zero_grad()
            loss = nn.functional.mse_loss(model(x), y)
            loss.backward()
            optimizer.step()
        model.eval()
        current, predictions = list(normalized[-window:]), []
        with torch.no_grad():
            for _ in range(max(horizons)):
                output = model(torch.tensor([current[-window:]], dtype=torch.float32).unsqueeze(-1)).item()
                if not math.isfinite(output):
                    raise ValueError("Training diverged; no forecast was saved")
                current.append(output)
                predictions.append(anchor * Decimal(str(max(0.000001, output * std + mean))))
        return predictions

    end = len(prices) - max(horizons)
    origins = sorted(set([end - 40, end - 20, end]))
    errors = {h: {"lstm": [], "naive": [], "lstm_hits": 0, "naive_hits": 0} for h in horizons}
    folds = []
    def sign(n):
        return (n > 0) - (n < 0)
    for origin in origins:
        predictions = fit_predict(prices[:origin])
        last = prices[origin - 1]
        folds.append({"train_end": points[origin - 1]["date"], "test_end": points[origin + max(horizons) - 1]["date"]})
        for h in horizons:
            actual, predicted = prices[origin + h - 1], predictions[h - 1]
            errors[h]["lstm"].append(abs(actual - predicted))
            errors[h]["naive"].append(abs(actual - last))
            errors[h]["lstm_hits"] += int(sign(predicted - last) == sign(actual - last))
            errors[h]["naive_hits"] += int(sign(actual - last) == 0)
    evaluation = [{"horizon_sessions": h, "lstm_mae": str(sum(v["lstm"], Decimal(0)) / len(origins)), "naive_mae": str(sum(v["naive"], Decimal(0)) / len(origins)), "lstm_directional_accuracy": v["lstm_hits"] / len(origins), "naive_directional_accuracy": v["naive_hits"] / len(origins), "n_origins": len(origins)} for h, v in errors.items()]
    future = fit_predict(prices)
    return {"status": "experimental", "demo": demo, "trained_at": datetime.now(timezone.utc).isoformat(), "last_observation": points[-1]["date"], "forecasts": [{"horizon_sessions": h, "lstm": str(future[h-1]), "naive": str(prices[-1])} for h in horizons], "evaluation": evaluation, "folds": folds, "note": "Experimental, not financial advice. Three chronological expanding-window origins, scalers refit on training data only. Recursive multi-step forecasts. MAE is in quote currency; prices are unadjusted. Zero change is a neutral direction for the naive baseline. Three origins are a smoke evaluation, not evidence of predictive skill."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("--epochs", type=int, default=25)
    args = parser.parse_args()
    if not 1 <= args.epochs <= 200:
        parser.error("epochs must be between 1 and 200")
    with SessionLocal() as db:
        h = market.history(db, args.symbol.upper())
        if h["stale"]:
            raise ValueError("Refresh market history before training")
        result = train_evaluate(h["points"], args.epochs, h["demo"])
        db.execute(insert(Forecast).values(symbol=args.symbol.upper(), result=result).on_conflict_do_update(index_elements=[Forecast.symbol], set_={"result": result, "trained_at": datetime.now(timezone.utc)}))
        db.commit()
        import json
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
