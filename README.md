# SmartAttend

SmartAttend is a monorepo for student attendance and classroom presence monitoring.

## Structure

- `kiosk/`: Raspberry Pi kiosk client for check-in and check-out capture
- `server/`: FastAPI backend, PostgreSQL/pgvector integration, CCTV monitoring scheduler
- `dashboard/`: React + Tailwind teacher dashboard and admin panel

## Stack

- Python 3.11+
- FastAPI
- PostgreSQL + pgvector
- DeepFace + OpenCV
- APScheduler
- React + Vite + Tailwind CSS

## Quick Start

### Backend

```bash
cd server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Dashboard

```bash
cd dashboard
npm install
npm run dev
```

### Kiosk

```bash
cd kiosk
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Notes

- The backend expects PostgreSQL with the `vector` extension enabled.
- DeepFace/ArcFace is GPU-optional but CPU-capable.
- The current implementation assumes 128-dimensional embeddings to match the provided spec.

