"""Train the surplus forecast and write the model-vs-baseline comparison. Usage: python -m scripts.train_prediction"""
from scripts._common import write_csv, write_md
from app.db.session import SessionLocal
from app.services import prediction

def main():
    with SessionLocal() as db:
        meta = prediction.train(db); db.commit()
    m = meta["metrics"]
    rows = [{"method": k, **m[k]} for k in ("gradient_boosting", "naive_last_week", "moving_average_7d")]
    write_csv("prediction_results.csv", rows)
    best = min(rows, key=lambda r: r["mae"])["method"]
    md = f"""# Prediction results

Data is **synthetic** (generated with weekday, month and event-season patterns plus noise), so these numbers show the pipeline works, not real-world accuracy.
Time-based split: train rows {m['train_rows']}, test rows {m['test_rows']} (last {m['test_days']} days, from {m['test_start']}). Metric: error in meals per donor-day (lower is better).

| method | MAE | RMSE |
|---|---|---|
""" + "".join(f"| {r['method']} | {r['mae']} | {r['rmse']} |\n" for r in rows) + f"\nBest MAE: **{best}**.\n"
    write_md("prediction_results.md", md); print(md)

if __name__ == "__main__":
    main()
