"""Surplus prediction (FR-10): gradient boosting vs two baselines on SYNTHETIC history.

Features: day_of_week, hour, area_cell, month, event_flag, rolling_7d_mean (past data only, no leakage).
All training data in this project is synthetic and labelled as such in the API and UI.
"""
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from app.core import clock
from app.core.config import settings
from app.core.errors import bad_request
from app.core.geo import area_cell
from app.db.models import SurplusHistory

SLOTS = (14, 17, 22)  # lunch-end, evening, dinner-end
EVENT_FLAGS = ("none", "wedding_season", "festival", "exam")
FESTIVALS = {(1, 14), (1, 26), (3, 14), (8, 15), (10, 2), (10, 20), (11, 8), (11, 12), (12, 25)}  # synthetic fixed calendar
TEST_DAYS = 28
CELL_SIZE = 0.05

# type -> (base meals/slot-day, slot weights for SLOTS, weekday multipliers Mon..Sun, flag multipliers)
PROFILES: dict[str, dict] = {
    "hostel": {"base": 55, "slots": (1.0, 0.2, 1.1), "dow": (1, 1, 1, 1, 1.1, 1.35, 1.4),
               "flags": {"exam": 1.25, "festival": 1.6, "wedding_season": 1.0}},
    "wedding": {"base": 140, "slots": (0.4, 0.3, 1.2), "dow": (0.4, 0.4, 0.5, 0.6, 1.6, 2.0, 1.9),
                "flags": {"wedding_season": 2.6, "festival": 1.4, "exam": 1.0}},
    "restaurant": {"base": 30, "slots": (1.0, 0.3, 1.2), "dow": (0.9, 0.9, 0.9, 1, 1.3, 1.5, 1.3),
                   "flags": {"festival": 1.4, "wedding_season": 1.1, "exam": 1.0}},
    "caterer": {"base": 70, "slots": (0.8, 0.4, 1.0), "dow": (0.6, 0.6, 0.7, 0.8, 1.3, 1.8, 1.6),
                "flags": {"wedding_season": 2.0, "festival": 1.5, "exam": 1.0}},
    "event": {"base": 50, "slots": (0.7, 0.8, 1.0), "dow": (1.2, 1.2, 1.1, 1.0, 1.0, 0.8, 0.7),
              "flags": {"festival": 0.7, "wedding_season": 1.0, "exam": 1.0}},
    "other": {"base": 25, "slots": (1.0, 0.8, 0.5), "dow": (1.1, 1.1, 1.1, 1.1, 1.0, 0.5, 0.4),
              "flags": {"festival": 0.6, "wedding_season": 1.0, "exam": 1.0}},
}


def event_flag_for(d: date) -> str:
    """Synthetic event calendar shared by history generation and forecasting."""
    if (d.month, d.day) in FESTIVALS:
        return "festival"
    if d.month in (11, 12, 1, 2, 4, 5, 6):  # North-India wedding seasons: Nov-Feb and Apr-Jun
        return "wedding_season"
    if d.month == 5 or (d.month == 12 and d.day <= 15):
        return "exam"
    return "none"


def generate_rows(donors: list[tuple[int, str, str]], end_date: date, days: int = 180, seed: int = 7) -> list[dict]:
    """Synthetic (donor_id, donor_type, area_cell) -> daily per-slot surplus rows ending on ``end_date``."""
    rng = random.Random(seed)
    rows = []
    for offset in range(days, 0, -1):
        d = end_date - timedelta(days=offset - 1)
        flag = event_flag_for(d)
        for donor_id, dtype, cell in donors:
            prof = PROFILES.get(dtype, PROFILES["other"])
            mult = prof["dow"][d.weekday()] * prof["flags"].get(flag, 1.0)
            for hour, w in zip(SLOTS, prof["slots"]):
                qty = max(0, round(prof["base"] * w * mult * (1 + rng.gauss(0, 0.15))))
                rows.append({"donor_id": donor_id, "date": datetime(d.year, d.month, d.day), "hour": hour,
                             "day_of_week": d.weekday(), "area_cell": cell, "quantity_meals": qty,
                             "event_flag": flag})
    return rows


def _frame(db) -> pd.DataFrame:
    recs = db.query(SurplusHistory.date, SurplusHistory.hour, SurplusHistory.area_cell, SurplusHistory.quantity_meals,
                    SurplusHistory.is_synthetic).all()
    if not recs:
        raise bad_request("no_history", "No surplus history available. Run the seed script first.")
    df = pd.DataFrame(recs, columns=["date", "hour", "area_cell", "qty", "synthetic"])
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df


def build_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to (date, cell, hour), densify gaps with zeros and add lag features."""
    agg = df.groupby(["date", "area_cell", "hour"], as_index=False)["qty"].sum()
    dates = pd.date_range(agg["date"].min(), agg["date"].max(), freq="D")
    keys = agg[["area_cell", "hour"]].drop_duplicates()
    grid = pd.MultiIndex.from_product([dates, range(len(keys))], names=["date", "k"]).to_frame(index=False)
    keys = keys.reset_index(drop=True).rename_axis("k").reset_index()
    full = grid.merge(keys, on="k").merge(agg, on=["date", "area_cell", "hour"], how="left").fillna({"qty": 0})
    full = full.sort_values(["area_cell", "hour", "date"]).reset_index(drop=True)
    g = full.groupby(["area_cell", "hour"])["qty"]
    full["rolling_7d_mean"] = g.transform(lambda s: s.shift(1).rolling(7, min_periods=7).mean())
    full["naive_last_week"] = g.shift(7)
    full["day_of_week"] = full["date"].dt.day_of_week
    full["month"] = full["date"].dt.month
    full["event_flag"] = full["date"].dt.date.map(event_flag_for)
    return full.dropna(subset=["rolling_7d_mean", "naive_last_week"]).reset_index(drop=True)


NUM, CAT = ["day_of_week", "month", "rolling_7d_mean", "naive_last_week", "hour"], ["area_cell", "event_flag"]


def _pipeline() -> Pipeline:
    pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), CAT)], remainder="passthrough")
    return Pipeline([("pre", pre), ("gbr", GradientBoostingRegressor(n_estimators=250, max_depth=3, learning_rate=0.08,
                                                                     subsample=0.9, random_state=42))])


def _metrics(y, pred) -> dict:
    return {"mae": round(float(mean_absolute_error(y, pred)), 3),
            "rmse": round(float(np.sqrt(mean_squared_error(y, pred))), 3)}


def evaluate_models(df: pd.DataFrame) -> tuple[Pipeline, dict]:
    """Time-based split (last 28 days = test). Returns the model fitted on TRAIN + metrics for all three methods."""
    data = build_dataset(df)
    cutoff = data["date"].max() - pd.Timedelta(days=TEST_DAYS - 1)
    train, test = data[data["date"] < cutoff], data[data["date"] >= cutoff]
    pipe = _pipeline().fit(train[NUM + CAT], train["qty"])
    metrics = {
        "gradient_boosting": _metrics(test["qty"], np.clip(pipe.predict(test[NUM + CAT]), 0, None)),
        "naive_last_week": _metrics(test["qty"], test["naive_last_week"]),
        "moving_average_7d": _metrics(test["qty"], test["rolling_7d_mean"]),
        "train_rows": int(len(train)), "test_rows": int(len(test)), "test_days": TEST_DAYS,
        "test_start": str(cutoff.date()),
    }
    return pipe, metrics


def train(db) -> dict:
    """Evaluate on the time split, refit on ALL data, save with joblib. Returns the metadata."""
    df = _frame(db)
    _, metrics = evaluate_models(df)
    data = build_dataset(df)
    final = _pipeline().fit(data[NUM + CAT], data["qty"])
    meta = {"pipeline": final, "metrics": metrics, "trained_at": clock.real_now().isoformat(),
            "is_synthetic": bool(df["synthetic"].all()), "cells": sorted(df["area_cell"].unique().tolist())}
    path = Path(settings.MODEL_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(meta, path)
    _FORECAST_CACHE.clear()
    return {k: v for k, v in meta.items() if k != "pipeline"}


def load_model(db) -> dict:
    path = Path(settings.MODEL_PATH)
    if not path.exists():
        train(db)
    return joblib.load(path)


def cell_center(cell: str) -> tuple[float, float]:
    i, j = (int(x) for x in cell.split("_"))
    return round((i + 0.5) * CELL_SIZE, 4), round((j + 0.5) * CELL_SIZE, 4)


_FORECAST_CACHE: dict = {}
_CACHE_TTL_S = 300.0


def forecast(db, days: int = 7) -> dict:
    """Cached wrapper: the recursive forecast does thousands of single-row predictions (~6 s), so results are
    kept for 5 minutes per ``days`` and dropped whenever the model is retrained."""
    import time
    hit = _FORECAST_CACHE.get(days)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL_S:
        return hit[1]
    result = _forecast_uncached(db, days)
    _FORECAST_CACHE[days] = (time.monotonic(), result)
    return result


def _forecast_uncached(db, days: int = 7) -> dict:
    """Recursive next-``days`` forecast per area cell (rolling mean uses earlier predictions)."""
    meta = load_model(db)
    pipe = meta["pipeline"]
    data = build_dataset(_frame(db))
    last_date = data["date"].max()
    out = []
    for cell in meta["cells"]:
        per_hour = {}
        for hour in SLOTS:
            hist = data[(data["area_cell"] == cell) & (data["hour"] == hour)].sort_values("date")
            per_hour[hour] = list(hist["qty"].tail(7)) if len(hist) >= 7 else [0.0] * 7
        day_rows = []
        for step in range(1, days + 1):
            d = (last_date + pd.Timedelta(days=step)).date()
            flag, by_hour = event_flag_for(d), {}
            for hour in SLOTS:
                x = pd.DataFrame([{"day_of_week": d.weekday(), "month": d.month, "hour": hour,
                                   "rolling_7d_mean": float(np.mean(per_hour[hour][-7:])),
                                   "naive_last_week": float(per_hour[hour][-7]), "area_cell": cell,
                                   "event_flag": flag}])
                y = max(0.0, float(pipe.predict(x[NUM + CAT])[0]))
                per_hour[hour].append(y)
                by_hour[str(hour)] = round(y, 1)
            day_rows.append({"date": str(d), "weekday": d.strftime("%a"), "event_flag": flag,
                             "expected_meals": round(sum(by_hour.values()), 1), "by_hour": by_hour})
        lat, lng = cell_center(cell)
        out.append({"area_cell": cell, "lat": lat, "lng": lng, "days": day_rows,
                    "week_total": round(sum(r["expected_meals"] for r in day_rows), 1)})
    return {"is_synthetic": meta["is_synthetic"], "trained_at": meta["trained_at"], "metrics": meta["metrics"],
            "note": "Forecast is trained on synthetic data generated for demonstration." if meta["is_synthetic"] else "",
            "cells": out}


def donor_cell(lat: float, lng: float) -> str:
    return area_cell(lat, lng, CELL_SIZE)
