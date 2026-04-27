# Deployment Guide

## Recommended topology

Deploy AegisCX as two services:

1. frontend on Netlify
2. backend on a Python or Docker host

This keeps the Next.js user interface fast and CDN-friendly while allowing the FastAPI backend to keep its long-running media processing behavior.

## Frontend deployment on Netlify

The repository includes [netlify.toml](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/netlify.toml) configured for the `frontend` application.

### Netlify setup

1. Create a new site from this repository.
2. Confirm the build base is `frontend`.
3. Confirm the build command is `npm run build`.
4. Set `NEXT_PUBLIC_API_URL` to your deployed backend URL, for example:

```text
https://your-backend-domain.example/api/v1
```

5. Deploy.

### Required frontend environment variable

```text
NEXT_PUBLIC_API_URL=https://your-backend-domain.example/api/v1
```

## Backend deployment

The backend can be deployed on any platform that supports Python 3.11 or Docker.

### Minimum requirements

- Python 3.11+
- FFmpeg installed on the host
- writable storage for `data/` and `logs/`
- optional Redis if you want Celery or LLM caching

### Backend environment variables

Start from [backend/.env.example](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/backend/.env.example).

Important production values:

- `SECRET_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- `CORS_ORIGINS`
- `WHISPER_MODEL_SIZE`
- `WHISPER_DEVICE`
- `GOOGLE_API_KEY`
- `OPENAI_API_KEY`
- `MISTRAL_API_KEY`
- `HF_TOKEN`

### Example backend startup

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## CORS reminder

When the frontend is live on Netlify, the backend must include the Netlify site origin in `CORS_ORIGINS`.

Example:

```text
CORS_ORIGINS=https://your-site.netlify.app,http://localhost:3000,http://127.0.0.1:3000
```

## File storage note

This codebase currently stores uploads and generated artifacts on the backend filesystem. For production, you may eventually want to move raw uploads and generated reports to object storage, but that is not required for local or small deployment environments.

## Current production readiness summary

Ready now:

- frontend build pipeline
- backend API service
- chunked upload flow
- transcript and insights persistence
- report download fallback
- Netlify frontend wiring

Still recommended later for heavier production use:

- object storage for media
- background worker queue at scale
- production PostgreSQL
- HTTPS secrets management
- monitoring and alerting
