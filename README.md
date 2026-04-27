# AegisCX Intelligence Platform

AegisCX is a transcript-first customer feedback intelligence system for turning uploaded audio and video reviews into structured business insight. The platform accepts customer conversations, preserves the raw transcript, then layers sentiment, emotion, intent, behavioral cues, product mentions, and report-ready summaries on top for company teams.

## What the system does

- Accepts `mp3`, `mp4`, `wav`, `m4a`, `webm`, `ogg`, `flac`, and `mpeg` files up to `1 GB`
- Normalizes media with FFmpeg and prepares chunk-aware audio for reliable speech extraction
- Produces a verbatim transcript first, then enriches it with speaker turns when available
- Generates executive summaries, key praises, key complaints, product mentions, behavioral scoring, and structured JSON insights
- Exposes the full workflow through a FastAPI backend and Next.js dashboard

## Verified current state

The local stack has been re-verified on the current codebase:

- Frontend build passes
- Backend tests pass
- Auth register and login both work
- Seeded local demo login works
- Report download works with an automatic HTML fallback when native PDF libraries are unavailable on Windows
- A fresh warmed upload completed from upload to `ANALYZED` in about `53 seconds`

Local URLs:

- Frontend: `http://127.0.0.1:3000`
- API docs: `http://127.0.0.1:8000/api/docs`
- Health: `http://127.0.0.1:8000/api/v1/health`

## Architecture at a glance

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
  -> dashboard, analytics, and downloadable report output
```

## Core product behavior

The platform is designed around one principle: keep the original conversation intact, then add intelligence around it without losing evidential grounding. Every downstream insight starts from the saved transcript, not from summary-only interpretation. That means teams can inspect the raw wording, the structured speaker flow, and the higher-level analysis side by side.

The current implementation also favors continuity under imperfect local conditions. If a provider, native library, or model stage is unavailable, the system degrades gracefully instead of collapsing the user flow. That applies to guest-mode development access, report generation fallback, and model inference handoff.

## Key reliability upgrades in this version

- Password hashing now uses a stable PBKDF2 path for new accounts, while still accepting older bcrypt hashes.
- Every real account is normalized into a workspace so dashboard and upload flows do not break on missing `company_id`.
- The seeded development admin now uses a valid login email: `demo@aegiscx.app`.
- Report download now falls back to HTML when native PDF rendering libraries are unavailable.
- STT and NLP model stacks now reuse shared in-process caches instead of reloading on every recording.
- Startup triggers background model warmup so the first real upload is faster.
- Upload UI messaging now distinguishes between upload completion and ongoing server-side analysis.
- Local summaries were upgraded to produce denser paragraph-level context with stronger behavioral framing.

## Local quick start

### One-command launcher

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\launch_aegiscx.ps1
```

This launcher:

- clears ports `3000` and `8000`
- starts the FastAPI backend
- starts the Next.js frontend
- waits for both services
- writes runtime logs under `logs/`

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

## Local auth modes

### Development guest mode

If no token is present in local development, the backend can still expose the dashboard through the deterministic local mock admin path. That keeps the app usable during early testing.

### Seeded local demo admin

- Email: `demo@aegiscx.app`
- Password: `AegisCX123`

This account is for local development only and is re-seeded on startup.

## Environment setup

Use the example files as the safe baseline:

- [backend/.env.example](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/.env.example)
- [frontend/.env.example](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/frontend/.env.example)

Important backend settings:

- `SECRET_KEY`
- `DATABASE_URL`
- `REDIS_URL`
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

## Deployment notes

### Frontend on Netlify

This repo now includes a root [netlify.toml](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/netlify.toml) configured for the `frontend` app. On Netlify you should:

1. Connect the repository.
2. Keep the base directory as `frontend`.
3. Set `NEXT_PUBLIC_API_URL` to your deployed backend API root.

### Backend deployment

The FastAPI backend should be deployed separately on a Python or Docker host such as Render, Railway, Fly.io, or any container platform. Once deployed, update:

- backend `CORS_ORIGINS`
- frontend `NEXT_PUBLIC_API_URL`

More detail is in [DEPLOYMENT.md](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/DEPLOYMENT.md).

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
|-- launch_aegiscx.ps1
|-- netlify.toml
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
- Frontend auth store: [frontend/src/lib/auth.ts](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/frontend/src/lib/auth.ts)
- Upload page: [frontend/src/app/upload/page.tsx](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/frontend/src/app/upload/page.tsx)
- Recording detail: [frontend/src/app/recording/[id]/page.tsx](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/frontend/src/app/recording/[id]/page.tsx)

## Technical reference

For a deeper engineering walkthrough, see [TECHNICAL.md](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/TECHNICAL.md).
