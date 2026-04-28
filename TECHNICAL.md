# AegisCX Technical Blueprint

## 1. Product intent

AegisCX is built to turn spoken customer feedback into auditable intelligence. The system is transcript-first by design: it preserves the original conversation, then derives structured interpretation around that evidence instead of replacing it with a black-box summary.

Three design goals drive the codebase:

- transcript fidelity
- graceful degradation
- deployable full-stack ergonomics

## 2. Runtime architecture

### Backend

- Framework: FastAPI
- Persistence: SQLAlchemy async
- Local default database: SQLite
- Deployment database target: PostgreSQL
- Processing mode: inline background execution by default, Celery-compatible when enabled

### Frontend

- Framework: Next.js 14 App Router
- Language: TypeScript
- State: Zustand for auth plus route-local state
- API client: Axios wrapper with retry and error normalization

## 3. End-to-end processing path

### Stage 1: upload

The frontend supports chunked uploads so slower or unstable connections do not destroy the entire transfer. The backend also keeps a direct upload path for compatibility and easier API testing.

### Stage 2: audio preparation

[backend/app/services/audio/processor.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/audio/processor.py) normalizes incoming media into WAV audio, applies cleanup, and prepares chunk-aware files for later transcription.

### Stage 3: speech to text

[backend/app/services/stt/engine.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/stt/engine.py) selects the best available path in this order:

1. WhisperX
2. faster-whisper
3. deterministic fallback

The runtime keeps shared in-process model caches so repeated recordings do not reload the STT stack from scratch.

### Stage 4: transcript persistence

[backend/app/services/inline_processor.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/inline_processor.py) stores the transcript and segment records before deeper analysis. This means the conversation itself is preserved even if a later NLP or LLM stage degrades.

### Stage 5: NLP intelligence

[backend/app/services/nlp/pipeline.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/nlp/pipeline.py) performs local segment-level analysis across these dimensions:

- sentence embeddings
- sentiment
- emotion
- zero-shot intent
- named entities
- behavioral heuristics
- uncertainty scoring

This stage also uses shared process-level caches to avoid repeated transformer reloads.

### Stage 6: optional LLM refinement

[backend/app/services/llm/orchestrator.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/llm/orchestrator.py) only activates when the local model confidence drops below threshold or when a fallback is required. The prompts are tuned for compact but context-rich paragraph output.

### Stage 7: insight persistence

The processor writes:

- overview summary
- behavioral summary
- praise and complaint highlights
- product or feature mentions
- segment-level insight rows
- report-ready structured fields

## 4. Auth and tenancy model

The backend uses JWT access and refresh tokens. New passwords are hashed with PBKDF2-SHA256 while legacy bcrypt hashes can still be verified and transparently refreshed on successful login.

Every real user is normalized into a company workspace so dashboard, upload, and reporting flows do not break on missing `company_id`.

## 5. Reporting behavior

The report endpoint tries native PDF generation first. When local Windows PDF runtime libraries are missing, the endpoint falls back to an HTML report download instead of failing the user flow.

## 6. Frontend reliability patterns

Recent hardening focuses on the failure cases that previously caused blank client-side crashes:

- auth storage is parsed defensively
- route-level error boundaries catch rendering failures
- dynamic recording detail pages are preserved as real app routes
- upload progress is separated from server-side analysis progress
- detail views guard against partial transcript or insight payloads

## 7. Performance profile

On the verified local stack:

- a warmed sample upload completed to `ANALYZED` in about `28.6 seconds`
- the first cold run is slower because models have to load
- the current practical local target is roughly five-minute media files and up to one gigabyte uploads

Most of the recent speed gains come from:

- shared STT model caching
- shared NLP model caching
- startup warmup
- resilient chunked upload handling

## 8. Deployment model

### Local development

The best fidelity path is still local:

- frontend on `127.0.0.1:3000`
- backend on `127.0.0.1:8000`
- SQLite by default

### Zero-cost public demo

The current zero-cost public deployment target is:

- Vercel Hobby for the Next.js frontend
- Render Free Web Service for the FastAPI backend
- Render Free Postgres for the database

That stack is sufficient for public testing from any device, but it has hard platform constraints:

- free Render services sleep when idle
- free Render disk is ephemeral
- free Render Postgres expires after 30 days

So this stack is best described as public-demo ready, not durable long-term production infrastructure.

## 9. Files worth reading first

- [backend/app/main.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/main.py)
- [backend/app/core/config.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/core/config.py)
- [backend/app/core/database.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/core/database.py)
- [backend/app/api/routes/auth.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/api/routes/auth.py)
- [backend/app/api/routes/recordings.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/api/routes/recordings.py)
- [backend/app/api/routes/reports_admin.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/api/routes/reports_admin.py)
- [backend/app/services/inline_processor.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/inline_processor.py)
- [backend/app/services/stt/engine.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/stt/engine.py)
- [backend/app/services/nlp/pipeline.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/nlp/pipeline.py)
- [backend/app/services/llm/orchestrator.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/llm/orchestrator.py)
- [frontend/src/app/upload/page.tsx](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/frontend/src/app/upload/page.tsx)
- [frontend/src/app/recording/[id]/RecordingDetail.tsx](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/frontend/src/app/recording/[id]/RecordingDetail.tsx)
