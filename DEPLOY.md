# Deploy FoodBridge Plus (one free service, 10 minutes)

The repo now builds into **one Docker image**: the React app is built and served by the FastAPI backend from the same address, so there is no CORS, no second server and no websocket proxy to set up.
Tested here: the combined serving (`/`, `/login`, `/donor`, `/api/...`, `/health`, `/docs`). **Not tested here: the Docker build itself** (no Docker in the build sandbox), so the first deploy may need one fix; send me the build log if it fails.

## Option A: Render (free, easiest)
1. Make a free GitHub account if needed. Create a new **private or public repository** and upload the project folder (everything including `Dockerfile` and `render.yaml`; `node_modules`, `.venv` and `*.db` are ignored by `.gitignore`/`.dockerignore`). With git installed:
   ```
   cd foodbridge_final
   git init
   git add .
   git commit -m "FoodBridge Plus"
   git branch -M main
   git remote add origin https://github.com/<your-username>/foodbridge.git
   git push -u origin main
   ```
2. Go to https://render.com, sign up with GitHub, **New > Blueprint**, pick the repo. Render reads `render.yaml` and creates the service (free plan).
   - Or **New > Web Service**, pick the repo, Runtime **Docker**, Plan **Free**, add env vars `SECRET_KEY` (any long random text), `DATABASE_URL` = `sqlite:////tmp/foodbridge.db`, `CORS_ORIGINS` = `*`, Health check path `/health`.
3. Wait for the build (5-10 min). Your URL will be `https://foodbridge-plus.onrender.com` (or similar). Log in with `donor1@demo.com` / `Demo@1234`.

## Know these limits of the free plan
- The service **sleeps after ~15 minutes without traffic**; the first visit then takes about a minute. Open the URL a few minutes before your demo.
- The disk is **temporary**: every restart or redeploy resets the database and re-seeds the demo data. Fine for a demo, not for real data. For persistent data use a Render PostgreSQL database and set `DATABASE_URL` to its URL (the code supports PostgreSQL but it is untested).
- Background jobs (escalation, expiry) run inside the same process, so they only run while the service is awake.

## Option B: demo from your laptop with a public link (no deployment)
Run backend and build as usual, then use a tunnel such as `ngrok http 8000` after copying the built frontend to `backend/static` (`cd frontend && npm run build && xcopy dist ..\backend\static /E /I` on Windows). Good as a backup if the free host is slow on the demo day.

## Before submitting
Keep the local run (VSCODE_RUN_STEPS.md) as your main demo; use the deployed link as a bonus and put it in the report.
