"""Latency benchmark against a RUNNING server (default http://localhost:8000). Usage: python -m scripts.benchmark_api [base_url]"""
import json, statistics as st, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from scripts._common import write_csv, write_md

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000") + "/api/v1"

def req(path, tok=None, body=None):
    h = {"content-type": "application/json"}
    if tok: h["authorization"] = "Bearer " + tok
    t = time.perf_counter()
    r = urllib.request.urlopen(urllib.request.Request(BASE + path, json.dumps(body).encode() if body is not None else None, h))
    data = json.load(r); return (time.perf_counter() - t) * 1000, data

def pct(v, p): v = sorted(v); return v[min(len(v) - 1, int(len(v) * p / 100))]

def main(n=100, workers=8):
    _, t = req("/auth/login", body={"email": "ngo1@demo.com", "password": "Demo@1234"}); tok = t["access_token"]
    _, a = req("/auth/login", body={"email": "admin@demo.com", "password": "Demo@1234"}); atok = a["access_token"]
    cases = [("GET /analytics/public", "/analytics/public", None), ("GET /listings (NGO)", "/listings?limit=50", tok),
             ("GET /pickups/mine (NGO)", "/pickups/mine", tok), ("GET /analytics/impact (admin)", "/analytics/impact", atok),
             ("GET /predictions/forecast", "/predictions/forecast?days=7", atok)]
    rows = []
    for name, path, tk in cases:
        req(path, tk)  # warm-up
        with ThreadPoolExecutor(workers) as ex:
            t0 = time.perf_counter(); lat = [x[0] for x in ex.map(lambda _: req(path, tk), range(n))]; wall = time.perf_counter() - t0
        rows.append({"endpoint": name, "requests": n, "concurrency": workers, "p50_ms": round(pct(lat, 50), 1), "p95_ms": round(pct(lat, 95), 1),
                     "max_ms": round(max(lat), 1), "req_per_s": round(n / wall, 1)})
    write_csv("benchmark_api.csv", rows)
    md = f"# API benchmark\n\nSingle uvicorn process, SQLite, client on the same machine, {n} requests per endpoint at concurrency {workers}. Dev-machine numbers; not a production claim.\n\n| endpoint | p50 ms | p95 ms | max ms | req/s |\n|---|---|---|---|---|\n"
    md += "".join(f"| {r['endpoint']} | {r['p50_ms']} | {r['p95_ms']} | {r['max_ms']} | {r['req_per_s']} |\n" for r in rows)
    write_md("benchmark_api.md", md); print(md)

if __name__ == "__main__":
    main()
