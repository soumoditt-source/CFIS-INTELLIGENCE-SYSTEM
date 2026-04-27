# AegisCX Technical Blueprint

## 1. System intent

AegisCX is designed to ingest spoken customer feedback, preserve the conversation as transcript evidence, and derive structured behavioral intelligence that can be audited by company teams. The architecture prioritizes three properties at once:

- transcript fidelity
- graceful degradation
- deployable full-stack ergonomics

## 2. Runtime architecture

### Backend

- Framework: FastAPI
- Persistence: SQLAlchemy async with PostgreSQL-compatible models and local SQLite fallback
- Processing mode: inline synchronous background processing by default, Celery-ready when enabled
- API shape: auth, recordings, analytics, reports, admin

### Frontend

- Framework: Next.js 14 App Router
- Language: TypeScript
- State: Zustand for auth, route-local state for page flows
- API client: Axios wrapper with retry handling for slower networks and long-running analysis

## 3. End-to-end processing path

### Stage 1: upload

The frontend supports chunked upload for resilience on slower or unstable networks. The backend also retains a legacy single-request upload path for compatibility and direct API testing.

### Stage 2: audio preparation

`backend/app/services/audio/processor.py` converts incoming media into normalized WAV audio, runs cleanup, and prepares chunk-aware files for later speech recognition. Temporary storage is handled in a project-local way so Windows temp-directory issues do not cascade into hard failures.

### Stage 3: speech to text

`backend/app/services/stt/engine.py` selects the best available backend in this order:

1. WhisperX
2. faster-whisper
3. deterministic mock fallback

The engine now keeps a shared in-process model cache so repeated recordings do not reload the STT stack. A background warmup call is triggered on application start to reduce first-upload latency.

### Stage 4: transcript persistence

`backend/app/services/inline_processor.py` persists the transcript and segment rows before deeper analysis. That design keeps the raw conversation available as soon as transcription is complete, even while higher-order analysis is still running.

### Stage 5: NLP intelligence

`backend/app/services/nlp/pipeline.py` performs local segment-level analysis:

- sentence embeddings
- sentiment
- emotion
- zero-shot intent
- named entities
- behavioral heuristics
- uncertainty scoring

Like STT, the NLP stack now uses shared process-level caches to avoid repeated transformer reloads.

### Stage 6: optional LLM refinement

`backend/app/services/llm/orchestrator.py` only activates when confidence is below threshold or when the local NLP stage degrades. The prompt has been tightened to favor compact but context-rich paragraph output rather than diffuse verbosity. It also avoids asking for exposed chain-of-thought style output.

### Stage 7: insight persistence

The inline processor writes:

- conversation overview
- executive summary
- behavioral summary
- product mentions
- praise and complaint highlights
- segment-level insight rows
- optional LLM-enriched fields

## 4. Auth and tenancy model

The system uses JWT access and refresh tokens. A recent stabilization pass changed password handling so:

- new passwords use PBKDF2-SHA256
- legacy bcrypt hashes still verify
- successful legacy logins are transparently rehashed

Every real user is also normalized into a company workspace. This prevents missing-tenant bugs where uploads or dashboards silently fail because `company_id` was absent.

## 5. Reporting behavior

The report endpoint attempts native PDF generation with WeasyPrint. On Windows systems that have the Python package installed but lack native rendering libraries, the endpoint now falls back to an HTML download instead of returning a `500` error. The frontend reads the returned content type and downloads the correct file accordingly.

## 6. Frontend reliability patterns

Recent frontend hardening focused on the user-facing failure modes that caused the generic client-side crash experience:

- persisted auth storage is parsed defensively
- route-level error boundaries prevent blank application crashes
- dashboard reload loops were removed
- detail views guard against partial transcript or insight payloads
- upload messaging distinguishes upload completion from analysis completion

## 7. Performance profile

On the verified local stack:

- fresh warmed uploads complete in under one minute for the sample test audio
- first cold boot remains slower because model caches must populate
- current safe local target remains roughly 5-minute media files and up to 1 GB upload size

The biggest latency wins in the current version come from:

- shared STT runtime caching
- shared NLP runtime caching
- startup warmup
- chunked upload retry behavior

## 8. Deployment model

The project is best deployed as two surfaces:

- Next.js frontend on Netlify
- FastAPI backend on a Python or Docker host

The frontend is configured to use `NEXT_PUBLIC_API_URL`, which keeps deployment simple as long as the backend CORS settings allow the Netlify domain.

## 9. Files worth reading first

- [backend/app/main.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/main.py)
- [backend/app/core/config.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/core/config.py)
- [backend/app/api/routes/auth.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/api/routes/auth.py)
- [backend/app/api/routes/recordings.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/api/routes/recordings.py)
- [backend/app/api/routes/reports_admin.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/api/routes/reports_admin.py)
- [backend/app/services/inline_processor.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/inline_processor.py)
- [backend/app/services/stt/engine.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/stt/engine.py)
- [backend/app/services/nlp/pipeline.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/nlp/pipeline.py)
- [backend/app/services/llm/orchestrator.py](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/app/services/llm/orchestrator.py)
- [frontend/src/app/upload/page.tsx](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/frontend/src/app/upload/page.tsx)
- [frontend/src/app/recording/[id]/page.tsx](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/frontend/src/app/recording/[id]/page.tsx)
