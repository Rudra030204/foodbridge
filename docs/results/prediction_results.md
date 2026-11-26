# Prediction results

Data is **synthetic** (generated with weekday, month and event-season patterns plus noise), so these numbers show the pipeline works, not real-world accuracy.
Time-based split: train rows 3480, test rows 672 (last 28 days, from 2026-10-27). Metric: error in meals per donor-day (lower is better).

| method | MAE | RMSE |
|---|---|---|
| gradient_boosting | 42.045 | 88.211 |
| naive_last_week | 43.634 | 91.5 |
| moving_average_7d | 67.777 | 118.782 |

Best MAE: **gradient_boosting**.
