"""
AegisCX Celery Application
==============================
Celery instance configuration for AegisCX background task processing.
Uses Redis as both broker and result backend.

Windows Note: Requires '-P solo' or '-P threads' during worker launch.
"""

import sys
from celery import Celery
from app.core.config import get_settings

settings = get_settings()

# ─── Initialization ────────────────────────────────────────────────────────────
# Note: On Windows, Celery needs the app instance to be easily importable.
celery_app = Celery(
    "aegiscx",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

# ─── Celery Configuration ────────────────────────────────────────────────────────
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task name mapping (Fixes common Windows 'not registered' errors)
    task_name_rewrite=lambda name, *args, **kwargs: name.replace("app.workers.tasks.", "aegiscx.tasks."),

    # Task routing
    task_routes={
        "aegiscx.tasks.process_audio": {"queue": "audio_queue"},
        "aegiscx.tasks.transcribe": {"queue": "stt_queue"},
        "aegiscx.tasks.analyze": {"queue": "nlp_queue"},
    },

    # Worker settings
    worker_prefetch_multiplier=1,   # Don't pre-fetch — each task is heavy
    task_acks_late=True,            # Acknowledge after completion
    task_reject_on_worker_lost=True,

    # Windows Compatibility Flags
    worker_enable_remote_control=False,  # Can cause hangs on Windows
    
    # Result settings
    result_expires=86400,

    # Rate limiting
    task_annotations={
        "aegiscx.tasks.analyze": {"rate_limit": "10/m"},
    },

    # Retry settings
    task_max_retries=3,
)

# ─── Diagnostics ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"--- AegisCX Celery Diagnostic ---")
    print(f"Broker: {settings.celery_broker_url}")
    print(f"Backend: {settings.celery_result_backend}")
    try:
        celery_app.connection().connect()
        print("SUCCESS: Broker is reachable.")
    except Exception as e:
        print(f"WARNING: Broker is NOT reachable: {str(e)}")
        print("Make sure Redis (local or cloud) is running.")
