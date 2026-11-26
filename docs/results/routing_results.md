# Routing results

Random scenarios in a ~18 km box (seed 11, 200 trials each). 'naive' = stops in request order.

| pickups | tight deadlines | naive km | NN km | NN+2-opt km | saving vs naive | miss rate naive | miss rate optimised |
|---|---|---|---|---|---|---|---|
| 2 | False | 32.57 | 29.35 | 28.15 | 13.5% | 0.0 | 0.0 |
| 2 | True | 32.08 | 29.01 | 28.24 | 12.0% | 0.505 | 0.465 |
| 3 | False | 48.33 | 38.95 | 36.98 | 23.5% | 0.0 | 0.0 |
| 3 | True | 50.86 | 39.91 | 38.75 | 23.8% | 0.76 | 0.63 |
| 4 | False | 68.02 | 48.96 | 46.95 | 31.0% | 0.0 | 0.0 |
| 4 | True | 67.46 | 48.53 | 47.09 | 30.2% | 0.905 | 0.84 |

All optimised routes passed the pickup-before-delivery precedence check. Synthetic geometry; straight-line (haversine) distances, not road distances.
