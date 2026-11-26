import csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
RESULTS = Path(__file__).resolve().parents[2] / "docs" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

def write_csv(name, rows):
    with open(RESULTS / name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def write_md(name, text):
    (RESULTS / name).write_text(text)
