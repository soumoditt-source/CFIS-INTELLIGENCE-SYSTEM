# Deployment Guide

This guide is written for the current restored AegisCX build, not for the earlier broken static-export attempt.

## Recommended zero-cost stack

For a public testable deployment with no required payment on the platform side, use:

1. Vercel Hobby for the Next.js frontend
2. Render Free Web Service for the FastAPI backend
3. Render Free Postgres for the database

This is the best zero-cost path for testing from any device with the current architecture. It is public-demo ready, but it is not a forever-production stack because Render free services sleep, free local disks are ephemeral, and free Render Postgres expires after 30 days.

## Before you deploy

Verify locally first:

```powershell
powershell -ExecutionPolicy Bypass -File .\launch_aegiscx.ps1
```

Then check:

- frontend opens on `http://127.0.0.1:3000`
- backend health works on `http://127.0.0.1:8000/api/v1/health`
- a sample upload reaches `ANALYZED`

## Backend on Render

The repo includes [render.yaml](/d:/CUSTOMER%20FEEDBACK%20SYSTEM%20TRANSCRIPT/render.yaml) for a Render Blueprint deployment.

### Render setup

1. Push your latest repository changes to GitHub.
2. Sign in to Render.
3. Create a new Blueprint instance from the GitHub repository.
4. Render will detect `render.yaml` at the repository root.
5. Confirm the region is `singapore`.
6. Let Render create:
   - one free web service named `aegiscx-api`
   - one free Postgres database named `aegiscx-db`

### Required backend environment values

Set these in the Render dashboard before the first real use:

- `CORS_ORIGINS`
  - example: `https://your-project.vercel.app,http://localhost:3000,http://127.0.0.1:3000`
- `GOOGLE_API_KEY`
- `MISTRAL_API_KEY`
- `OPENAI_API_KEY`
- `HF_TOKEN`

### Backend runtime notes

- The Dockerfile now binds to `PORT`, which matches Render expectations.
- The backend defaults are tuned for CPU-based free deployment: `WHISPER_MODEL_SIZE=base`, `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8`.
- `USE_CELERY=false` keeps the free deployment simple and avoids requiring Redis.

## Frontend on Vercel

### Vercel setup

1. Sign in to Vercel.
2. Import the GitHub repository.
3. In project settings, set the Root Directory to `frontend`.
4. Keep the framework as Next.js.
5. Add the environment variable below.
6. Deploy.

### Required frontend environment variable

```text
NEXT_PUBLIC_API_URL=https://your-render-service.onrender.com/api/v1
```

### Important note about the frontend

This app must run as a real Next.js server deployment, not as a static export. The dynamic recording detail route is intentionally restored for server-backed behavior.

## Post-deploy wiring

After both services are live:

1. Copy the Vercel site URL.
2. Add it to the backend `CORS_ORIGINS` value in Render.
3. Redeploy the Render backend if needed.
4. Test login, upload, transcript, insights, and report download from the public Vercel URL.

## Public verification checklist

- `GET /api/v1/health` returns healthy
- register works
- login works
- upload works
- status polling reaches `ANALYZED`
- transcript page loads without crashing
- insights render
- report download returns either PDF or the HTML fallback

## Free-tier limits you should expect

### Render free backend

- sleeps after inactivity
- wakes up slowly on the next request
- loses local filesystem state on restart or redeploy

### Render free Postgres

- good for testing and demos
- expires 30 days after creation

### Vercel Hobby frontend

- good for personal projects and demos
- usage is capped by the Hobby plan

## When you are ready for a stronger production stack

Move these pieces first:

1. database from free temporary tier to a durable managed Postgres plan
2. raw upload and generated report storage from local disk to object storage
3. long-running processing from inline mode to queued workers

Those upgrades are optional for testing, but they are the real path from public demo to durable production.
