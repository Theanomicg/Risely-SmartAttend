# SmartAttend

SmartAttend is a monorepo for student attendance and classroom presence monitoring.

## Structure

- `kiosk/`: Raspberry Pi kiosk client for check-in and check-out capture
- `server/`: FastAPI backend, PostgreSQL/pgvector integration, CCTV monitoring scheduler
- `dashboard/`: React + Tailwind teacher dashboard and admin panel

In this project, `class_id` is the primary identifier for an academic class such as `Class-10-A`. The teacher view, attendance logs, kiosk check-in/check-out flow, alerts, and camera configuration should all use the same `class_id` value.

## Stack

- Python 3.11+
- FastAPI
- PostgreSQL + pgvector
- DeepFace + OpenCV
- APScheduler
- React + Vite + Tailwind CSS

## Quick Start

### Database

```bash
docker compose up -d postgres
```

Or from the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-db.ps1
```

If `.ps1` files open in an editor on your machine, use:

```cmd
scripts\start-db.cmd
```

### Backend

```bash
cd server
copy .env.example .env
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Recommended on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1
```

Or:

```cmd
scripts\start-backend.cmd
```

Use `--reload` only if your local Python environment allows the watcher process. The canonical script runs without reload to avoid Windows named-pipe permission issues.

The dashboard uses the local Vite proxy at `/api` and `/ws`, so restart the dashboard dev server after changing backend connectivity.

### Dashboard

```bash
cd dashboard
copy .env.example .env
npm install
npm run dev
```

Recommended on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-dashboard.ps1
```

Or:

```cmd
scripts\start-dashboard.cmd
```

### Kiosk

```bash
cd kiosk
copy .env.example .env
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Recommended on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-kiosk.ps1
```

Or:

```cmd
scripts\start-kiosk.cmd
```

Camera selection:

- The kiosk no longer defaults to camera index `0`.
- Set `SMARTATTEND_CLASS_ID=class-10-a` in [kiosk/.env](C:/Users/lamsa/Downloads/Risely-SmartAttend/kiosk/.env) so kiosk events are recorded for the correct class.
- Set `SMARTATTEND_CAMERA_INDEX=1` in [kiosk/.env](C:/Users/lamsa/Downloads/Risely-SmartAttend/kiosk/.env) to target the HD webcam instead of common virtual-camera slots.
- On Windows, `SMARTATTEND_CAMERA_BACKEND=dshow` is the canonical backend for USB webcams.

## Notes

- The dashboard includes an attendance log that shows each student's date, check-in time, check-out time, and current session status.
- The backend and kiosk startup scripts prefer their local `.venv` interpreters when present.
- The backend expects PostgreSQL with the `vector` extension enabled.
- DeepFace/ArcFace is GPU-optional but CPU-capable.
- The current implementation assumes 128-dimensional embeddings to match the provided spec.
- `compose.yaml` is the default Docker Compose entry point for this repo.
- Canonical runtime entry points live in `scripts/` to keep local setup predictable.
