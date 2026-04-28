# AegisCX Intelligence Platform

AegisCX converts customer review audio and video into transcript-first business intelligence. The system preserves the original conversation, then layers sentiment, emotion, intent, product cues, behavioral signals, and structured summaries on top so a company can audit both the evidence and the interpretation in one place.

## Verified current state

The current repository has been restored to the last working local flow and re-aligned for deployment:

- frontend builds successfully
- backend tests pass
- auth register and login work
- seeded demo login works
- transcript, insights, and report download flow work
- a fresh warmed sample upload completed to `ANALYZED` in about `28.6 seconds`

## Local prerequisites

- Python `3.10+`
- Node.js `18+`
- FFmpeg on your `PATH`

Local URLs:

- Frontend: `http://127.0.0.1:3000`
- API docs: `http://127.0.0.1:8000/api/docs`
- Health: `http://127.0.0.1:8000/api/v1/health`

## What the product does

- Accepts `mp3`, `mp4`, `wav`, `m4a`, `webm`, `ogg`, `flac`, and `mpeg`
- Supports uploads up to `1 GB`
- Converts incoming media into normalized audio for stable speech extraction
- Produces a verbatim transcript before higher-level interpretation
- Adds sentiment, emotion, intent, entities, behavioral cues, and product-facing summaries
- Exposes recordings, analytics, and report downloads through a FastAPI backend and a Next.js dashboard

## System flow

```text
Upload
  -> media normalization
  -> audio cleanup
  -> chunk preparation
  -> STT transcription
  -> transcript persistence
  -> NLP intelligence analysis
  -> optional LLM refinement
  -> insight persistence
  -> dashboard and report output
```

## Local quick start

### Clean-machine setup

For a fresh local machine or a freshly cloned repo:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_aegiscx.ps1
```

This script:

- creates `backend\venv311`
- installs backend Python dependencies
- installs frontend npm dependencies
- creates local `.env` files from safe templates if missing
- initializes the local SQLite database

### One-command launcher

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\launch_aegiscx.ps1
```

This starts both services, clears the local ports, waits for readiness, and writes logs under `logs/`.

If the launcher detects a missing virtual environment or missing `node_modules`, it will automatically run `setup_aegiscx.ps1` first.

### Manual backend

```powershell
cd backend
.\venv311\Scripts\activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Manual frontend

```powershell
cd frontend
npm install
npm run dev
```

### Fresh local stack in two commands

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_aegiscx.ps1
powershell -ExecutionPolicy Bypass -File .\launch_aegiscx.ps1
```

## Local access

Seeded development demo account:

- Email: `demo@aegiscx.app`
- Password: `AegisCX123`

This account is intended for local and test environments only.

## Environment setup

Use the example files as the safe starting point:

- [backend/.env.example](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/.env.example)
- [frontend/.env.example](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/frontend/.env.example)

Important backend settings:

- `SECRET_KEY`
- `DATABASE_URL`
- `CORS_ORIGINS`
- `WHISPER_MODEL_SIZE`
- `WHISPER_DEVICE`
- `GOOGLE_API_KEY`
- `OPENAI_API_KEY`
- `MISTRAL_API_KEY`
- `HF_TOKEN`

Important frontend setting:

- `NEXT_PUBLIC_API_URL`

## API surface

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/recordings/upload`
- `POST /api/v1/recordings/upload/chunk`
- `POST /api/v1/recordings/upload/finalize`
- `GET /api/v1/recordings`
- `GET /api/v1/recordings/{id}`
- `GET /api/v1/recordings/{id}/status`
- `GET /api/v1/recordings/{id}/transcript`
- `GET /api/v1/recordings/{id}/insights`
- `GET /api/v1/analytics/overview`
- `GET /api/v1/analytics/products`
- `GET /api/v1/reports/{id}/json`
- `GET /api/v1/reports/{id}/pdf`
- `GET /api/v1/health`

## Zero-cost public deployment

The cleanest free deployment path for the current repository is:

1. frontend on Vercel Hobby
2. backend on Render Free Web Service
3. database on Render Free Postgres

That stack is good for testing from any device, public demos, and portfolio-style use. It is not the same as a fully durable production stack because free Render services sleep when idle and use ephemeral local disk storage.

Deployment instructions live in [DEPLOYMENT.md](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/DEPLOYMENT.md).

## Honest free-tier limits

- Free Render web services spin down after inactivity and take time to wake up.
- Free Render web services do not keep local filesystem changes between restarts or redeploys.
- Free Render Postgres is convenient for zero-cost testing, but it expires after 30 days.
- The app is public-demo ready on free services, but long-term production media retention needs object storage and a more durable database plan.

## Repository map

```text
CUSTOMER FEEDBACK SYSTEM TRANSCRIPT/
|-- backend/
|   |-- app/
|   |   |-- api/routes/
|   |   |-- core/
|   |   |-- models/
|   |   |-- services/
|   |   |   |-- audio/
|   |   |   |-- stt/
|   |   |   |-- nlp/
|   |   |   `-- llm/
|   |   `-- workers/
|   |-- data/
|   `-- requirements.txt
|-- frontend/
|   `-- src/
|-- setup_aegiscx.ps1
|-- launch_aegiscx.ps1
|-- render.yaml
|-- TECHNICAL.md
`-- DEPLOYMENT.md
```

## Important implementation files

- Backend entry: [backend/app/main.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/main.py)
- Auth routes: [backend/app/api/routes/auth.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/api/routes/auth.py)
- Recording routes: [backend/app/api/routes/recordings.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/api/routes/recordings.py)
- Report routes: [backend/app/api/routes/reports_admin.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/api/routes/reports_admin.py)
- Inline processor: [backend/app/services/inline_processor.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/inline_processor.py)
- STT engine: [backend/app/services/stt/engine.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/stt/engine.py)
- NLP pipeline: [backend/app/services/nlp/pipeline.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/nlp/pipeline.py)
- LLM orchestrator: [backend/app/services/llm/orchestrator.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/llm/orchestrator.py)
- Local bootstrap: [setup_aegiscx.ps1](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/setup_aegiscx.ps1)
- Frontend auth store: [frontend/src/lib/auth.ts](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/frontend/src/lib/auth.ts)
- Upload page: [frontend/src/app/upload/page.tsx](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/frontend/src/app/upload/page.tsx)
- Recording detail shell: [frontend/src/app/recording/[id]/page.tsx](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/frontend/src/app/recording/[id]/page.tsx)
- Recording detail UI: [frontend/src/app/recording/[id]/RecordingDetail.tsx](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/frontend/src/app/recording/[id]/RecordingDetail.tsx)

## Technical reference

For a deeper engineering walkthrough, see [TECHNICAL.md](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/TECHNICAL.md).
