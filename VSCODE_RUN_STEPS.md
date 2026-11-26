# Run FoodBridge Plus in VS Code (step by step)

## Install once
1. **Python 3.11 or newer** - https://www.python.org/downloads/ (Windows: tick "Add Python to PATH").
2. **Node.js 20 or newer** (LTS) - https://nodejs.org
3. **VS Code** with the extensions *Python* and *ES7+ React snippets* (optional).
4. Check in a terminal: `python --version` (Windows may need `py --version`) and `node --version`.

## Open the project
1. Unzip the project. In VS Code: **File > Open Folder** and choose the `foodbridge` folder.
2. Open the terminal: **Terminal > New Terminal**. You will use **two terminals** (use the **+** button, or the split icon).

## Terminal 1 - backend
```bash
cd backend
python -m venv .venv
```
Activate it:
- Windows PowerShell: `.venv\Scripts\Activate.ps1` (if blocked: `Set-ExecutionPolicy -Scope Process Bypass` first)
- Windows cmd: `.venv\Scripts\activate.bat`
- Mac/Linux: `source .venv/bin/activate`

Then:
```bash
pip install -r requirements.txt
alembic upgrade head
python scripts/seed.py
uvicorn app.main:app --port 8000
```
Leave it running. Check http://localhost:8000/docs opens (API docs).
If VS Code asks for a Python interpreter, pick the one inside `backend/.venv`.

## Terminal 2 - frontend
```bash
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173** in the browser.

## Login (password for all: `Demo@1234`)
| Role | Email |
|---|---|
| Donor | donor1@demo.com |
| NGO | ngo6@demo.com (Old Age Care, close to donor1) |
| Volunteer | volunteer1@demo.com ... volunteer10@demo.com |
| Admin | admin@demo.com |

Tip: use one normal window and one incognito window to be two users at once.

## Quick demo (3 minutes)
Follow the "3-minute demo script" in README.md. Short version: donor1 posts food -> ngo6 claims it -> the volunteer shown on the NGO page accepts, starts the trip, enters the donor's pickup code, then the NGO's delivery code -> delivered. Finish on the admin page.

## Faster escalation for a live demo (optional)
Stop the backend and start it with time sped up 60x (Windows PowerShell: `$env:TIME_SCALE=60; uvicorn app.main:app --port 8000`; Mac/Linux: `TIME_SCALE=60 uvicorn app.main:app --port 8000`). Nobody claims -> escalation levels appear within seconds.

## Run the tests (optional, for the report)
```bash
cd backend && python -m pytest tests -q          # expect 111 passed
cd frontend && npm test                          # expect 22 passed
```
Browser tests: `cd frontend && npx playwright install chromium && npm run e2e` (backend must be running).

## Reset demo data
Stop the backend, delete `backend/foodbridge.db`, then run `alembic upgrade head` and `python scripts/seed.py` again.

## Common problems
| Problem | Fix |
|---|---|
| `python` not found | Use `py` (Windows) or `python3` (Mac/Linux) |
| `pip install` fails on a package | Upgrade pip: `python -m pip install --upgrade pip`, retry; use Python 3.11-3.13 |
| Page is blank / "Could not reach the server" | Backend (terminal 1) is not running or not on port 8000 |
| Port 5173 or 8000 busy | Close the old terminal or change the port (`--port 8001`; then set `API_PROXY=http://localhost:8001` before `npm run dev`) |
| Maps are grey | No internet (map tiles are loaded online) |
| "database is locked" | Only one backend should run; stop duplicates |
| Login says invalid | Seed was not run, or the DB was deleted: run the seed again |
| Docker | Not needed; skip it |
