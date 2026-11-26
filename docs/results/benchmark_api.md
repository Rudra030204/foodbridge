# API benchmark

Single uvicorn process, SQLite, client on the same machine, 100 requests per endpoint at concurrency 8. Dev-machine numbers; not a production claim.

| endpoint | p50 ms | p95 ms | max ms | req/s |
|---|---|---|---|---|
| GET /analytics/public | 69.2 | 192.0 | 268.2 | 93.9 |
| GET /listings (NGO) | 135.9 | 198.7 | 214.3 | 57.3 |
| GET /pickups/mine (NGO) | 128.5 | 184.5 | 199.5 | 62.1 |
| GET /analytics/impact (admin) | 80.1 | 174.6 | 218.5 | 92.5 |
| GET /predictions/forecast | 19.5 | 28.1 | 29.2 | 393.7 |
