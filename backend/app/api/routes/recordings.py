"""
AegisCX Recordings Routes
===========================
Endpoints:
  POST /recordings/upload          — Upload audio/video file
  GET  /recordings/                — List recordings (paginated)
  GET  /recordings/{id}            — Get recording details
  GET  /recordings/{id}/status     — Real-time processing status
  GET  /recordings/{id}/transcript — Full transcript with segments
  GET  /recordings/{id}/insights   — Full analysis results
  DELETE /recordings/{id}          — Delete recording
"""

import shutil
import uuid
from pathlib import Path
from typing import Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Recording, Transcript, TranscriptSegment, Insight, SegmentInsight

router = APIRouter()
settings = get_settings()
log = structlog.get_logger("cfis.recordings")

# USE_CELERY is read from settings (backed by .env → USE_CELERY=false/true).
# This is the correct approach — pydantic-settings reads .env into typed fields,
# but does NOT back-populate os.environ, so os.environ.get() would miss .env values.
USE_CELERY: bool = settings.use_celery



# ─── Response Schemas ────────────────────────────────────────────────────────────
class RecordingResponse(BaseModel):
    id: str
    original_filename: str
    status: str
    file_size_bytes: Optional[int]
    duration_seconds: Optional[float]
    format: Optional[str]
    error_message: Optional[str] = None
    progress_message: Optional[str] = None
    transcript_ready: bool = False
    insights_ready: bool = False
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class PaginatedRecordings(BaseModel):
    items: list[RecordingResponse]
    total: int
    page: int
    per_page: int
    pages: int


class UploadResponse(BaseModel):
    recording_id: str
    task_id: str
    status: str
    message: str


class ChunkUploadResponse(BaseModel):
    upload_id: str
    chunk_index: int
    message: str


class UploadFinalizeRequest(BaseModel):
    upload_id: str
    filename: str
    company_name: Optional[str] = None
    product_category: Optional[str] = None
    num_speakers: Optional[int] = None


class StatusResponse(BaseModel):
    recording_id: str
    status: str
    progress_message: str
    error_message: Optional[str]
    duration_seconds: Optional[float]


class TranscriptSegmentSchema(BaseModel):
    segment_index: int
    speaker_label: Optional[str]
    start_time: float
    end_time: float
    text: str
    word_count: Optional[int]


class TranscriptResponse(BaseModel):
    recording_id: str
    full_text: str
    word_count: Optional[int]
    language: str
    num_speakers: Optional[int]
    stt_model: str
    segments: list[TranscriptSegmentSchema]


class InsightResponse(BaseModel):
    recording_id: str
    overall_sentiment: Optional[str]
    sentiment_score: Optional[float]
    dominant_emotion: Optional[str]
    customer_intent: Optional[str]
    intent_confidence: Optional[float]
    executive_summary: Optional[str]
    product_mentions: Optional[list]
    behavioral_signals: Optional[dict]
    emotion_arc: Optional[list]
    confidence_score: Optional[float]
    analysis_tier: str
    requires_human_review: bool
    full_analysis: dict


# ─── Status message map ──────────────────────────────────────────────────────────
STATUS_MESSAGES = {
    "PENDING": "Queued for processing",
    "AUDIO_PROCESSING": "Converting and cleaning audio...",
    "AUDIO_READY": "Audio prepared, starting transcription...",
    "TRANSCRIBING": "Transcribing speech to text (this may take a few minutes)...",
    "TRANSCRIBED": "Transcript ready, running AI analysis...",
    "ANALYZING": "Running sentiment, emotion, and behavioral analysis...",
    "ANALYZED": "Analysis complete ✓",
    "FAILED": "Processing failed",
}


def _serialize_recording(recording: Recording) -> RecordingResponse:
    """Return a UI-friendly recording payload with derived readiness flags."""
    return RecordingResponse(
        id=recording.id,
        original_filename=recording.original_filename,
        status=recording.status,
        file_size_bytes=recording.file_size_bytes,
        duration_seconds=recording.duration_seconds,
        format=recording.format,
        error_message=recording.error_message,
        progress_message=STATUS_MESSAGES.get(recording.status, recording.status),
        transcript_ready=recording.status in {"TRANSCRIBED", "ANALYZING", "ANALYZED"},
        insights_ready=recording.status == "ANALYZED",
        created_at=recording.created_at.isoformat(),
        updated_at=recording.updated_at.isoformat(),
    )


# ─── Endpoints ──────────────────────────────────────────────────────────────────
@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_recording(
    file: UploadFile = File(...),
    company_name: Optional[str] = Form(default=None),
    product_category: Optional[str] = Form(default=None),
    num_speakers: Optional[int] = Form(default=None),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Legacy single-shot upload. Retained for backwards compatibility.
    """
    filename = file.filename or "unknown"
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type: .{ext}. Allowed: {', '.join(settings.allowed_extensions)}",
        )

    content_length = file.size
    if content_length and content_length > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {settings.max_file_size_gb}GB",
        )

    recording_id = str(uuid.uuid4())
    raw_dir = settings.raw_audio_dir / recording_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_path = raw_dir / f"original.{ext}"

    try:
        with open(file_path, "wb") as f:
            while chunk := await file.read(8 * 1024 * 1024):
                f.write(chunk)
    except IOError as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    return await _finalize_recording_setup(
        recording_id=recording_id,
        filename=filename,
        ext=ext,
        file_path=file_path,
        company_name=company_name,
        product_category=product_category,
        num_speakers=num_speakers,
        current_user=current_user,
        db=db,
        background_tasks=background_tasks
    )


@router.post("/upload/chunk", response_model=ChunkUploadResponse, status_code=status.HTTP_200_OK)
async def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Dynamic Slicing Algorithm (DSA): Upload a file chunk.
    This enables highly resilient uploads over 3G/4G networks.
    """
    temp_dir = settings.raw_audio_dir / "temp_uploads" / upload_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    chunk_path = temp_dir / f"chunk_{chunk_index}"
    try:
        with open(chunk_path, "wb") as f:
            while chunk := await file.read(1 * 1024 * 1024): # 1MB internal buffer
                f.write(chunk)
    except IOError as e:
        log.error("chunk_upload_error", upload_id=upload_id, chunk_index=chunk_index, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to save chunk: {e}")
        
    log.info("chunk_uploaded", upload_id=upload_id, chunk_index=chunk_index, total=total_chunks)
    return ChunkUploadResponse(
        upload_id=upload_id,
        chunk_index=chunk_index,
        message=f"Chunk {chunk_index}/{total_chunks} received."
    )


@router.post("/upload/finalize", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def finalize_upload(
    req: UploadFinalizeRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Dynamic Slicing Algorithm (DSA): Finalize chunked upload.
    Reconstructs the file from chunks and dispatches processing.
    """
    ext = req.filename.split(".")[-1].lower() if "." in req.filename else ""
    if ext not in settings.allowed_extensions:
        raise HTTPException(status_code=422, detail=f"Unsupported type: .{ext}")

    temp_dir = settings.raw_audio_dir / "temp_uploads" / req.upload_id
    if not temp_dir.exists():
        raise HTTPException(status_code=404, detail="Upload ID not found")
        
    # Gather chunks and assemble
    chunk_files = sorted([f for f in temp_dir.iterdir() if f.name.startswith("chunk_")], key=lambda x: int(x.name.split("_")[1]))
    if not chunk_files:
        raise HTTPException(status_code=400, detail="No chunks found for this upload")

    recording_id = str(uuid.uuid4())
    raw_dir = settings.raw_audio_dir / recording_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_path = raw_dir / f"original.{ext}"
    
    try:
        with open(file_path, "wb") as outfile:
            for chunk_file in chunk_files:
                with open(chunk_file, "rb") as infile:
                    shutil.copyfileobj(infile, outfile)
    except IOError as e:
        log.error("reconstruction_error", upload_id=req.upload_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to reconstruct file")
        
    # Cleanup temp directory
    shutil.rmtree(temp_dir, ignore_errors=True)
    
    # Check total size
    actual_size = file_path.stat().st_size
    if actual_size > settings.max_file_size_bytes:
        shutil.rmtree(raw_dir, ignore_errors=True)
        raise HTTPException(status_code=413, detail="Assembled file exceeds size limit")

    return await _finalize_recording_setup(
        recording_id=recording_id,
        filename=req.filename,
        ext=ext,
        file_path=file_path,
        company_name=req.company_name,
        product_category=req.product_category,
        num_speakers=req.num_speakers,
        current_user=current_user,
        db=db,
        background_tasks=background_tasks
    )


async def _finalize_recording_setup(
    recording_id: str,
    filename: str,
    ext: str,
    file_path: Path,
    company_name: Optional[str],
    product_category: Optional[str],
    num_speakers: Optional[int],
    current_user: dict,
    db: AsyncSession,
    background_tasks: BackgroundTasks
) -> UploadResponse:
    """Helper to finalize DB creation and dispatch tasks."""
    actual_size = file_path.stat().st_size
    recording = Recording(
        id=recording_id,
        user_id=current_user["user_id"],
        company_id=current_user.get("company_id") or current_user["user_id"],
        original_filename=filename,
        file_path=str(file_path),
        file_size_bytes=actual_size,
        format=ext,
        status="PENDING",
    )
    db.add(recording)
    await db.commit()

    task_id = str(uuid.uuid4())
    if USE_CELERY:
        try:
            from app.workers.tasks import process_audio_task
            task = process_audio_task.apply_async(
                kwargs={"recording_id": recording_id, "file_path": str(file_path)},
                queue="audio_queue",
            )
            task_id = task.id
            log.info("celery_dispatch_ok", recording_id=recording_id, task_id=task_id)
            if company_name or product_category or num_speakers:
                log.info(
                    "recording_context_queued_without_inline_metadata",
                    recording_id=recording_id,
                    company_name=company_name,
                    product_category=product_category,
                    num_speakers=num_speakers,
                    message="Context metadata is used only by the inline local pipeline.",
                )
        except Exception as exc:
            log.warning("celery_unavailable", error=str(exc), fallback="inline_processor")
            from app.services.inline_processor import process_pipeline_inline
            background_tasks.add_task(
                process_pipeline_inline,
                recording_id=recording_id,
                file_path=str(file_path),
                num_speakers=num_speakers,
                company_name=company_name,
                product_category=product_category,
            )
    else:
        from app.services.inline_processor import process_pipeline_inline
        background_tasks.add_task(
            process_pipeline_inline,
            recording_id=recording_id,
            file_path=str(file_path),
            num_speakers=num_speakers,
            company_name=company_name,
            product_category=product_category,
        )
        log.info("inline_dispatch", recording_id=recording_id)

    return UploadResponse(
        recording_id=recording_id,
        task_id=task_id,
        status="PENDING",
        message=f"File '{filename}' uploaded successfully. Processing started.",
    )


@router.get("/", response_model=PaginatedRecordings)
async def list_recordings(
    page: int = 1,
    per_page: int = 20,
    status_filter: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all recordings for the current user's company.
    Supports pagination and status filtering.
    """
    per_page = min(per_page, 100)  # Cap at 100

    query = select(Recording).where(
        Recording.company_id == current_user.get("company_id", current_user["user_id"])
    )
    if status_filter:
        query = query.where(Recording.status == status_filter.upper())

    # Count total
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    # Paginate
    result = await db.execute(
        query.order_by(desc(Recording.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    recordings = result.scalars().all()

    return PaginatedRecordings(
        items=[_serialize_recording(r) for r in recordings],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )


@router.get("/{recording_id}/status", response_model=StatusResponse)
async def get_status(
    recording_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get real-time processing status for a recording.
    Poll this endpoint to track progress.
    """
    recording = await _get_recording_or_404(recording_id, current_user, db)

    return StatusResponse(
        recording_id=recording_id,
        status=recording.status,
        progress_message=STATUS_MESSAGES.get(recording.status, recording.status),
        error_message=recording.error_message,
        duration_seconds=recording.duration_seconds,
    )


@router.get("/{recording_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(
    recording_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the full speaker-diarized transcript for a recording.
    Only available once status reaches TRANSCRIBED or ANALYZED.
    """
    recording = await _get_recording_or_404(recording_id, current_user, db)

    if recording.status not in ("TRANSCRIBED", "ANALYZING", "ANALYZED"):
        raise HTTPException(
            status_code=status.HTTP_425_TOO_EARLY,
            detail=f"Transcript not ready yet. Current status: {recording.status}",
        )

    result = await db.execute(
        select(Transcript).where(Transcript.recording_id == recording_id)
    )
    transcript = result.scalar_one_or_none()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    segs_result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.transcript_id == transcript.id)
        .order_by(TranscriptSegment.segment_index)
    )
    segments = segs_result.scalars().all()

    return TranscriptResponse(
        recording_id=recording_id,
        full_text=transcript.full_text,
        word_count=transcript.word_count,
        language=transcript.language,
        num_speakers=transcript.num_speakers,
        stt_model=transcript.stt_model,
        segments=[
            TranscriptSegmentSchema(
                segment_index=s.segment_index,
                speaker_label=s.speaker_label,
                start_time=s.start_time,
                end_time=s.end_time,
                text=s.text,
                word_count=s.word_count,
            )
            for s in segments
        ],
    )


@router.get("/{recording_id}/insights", response_model=InsightResponse)
async def get_insights(
    recording_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get full AI analysis results for a recording.
    Only available once status = ANALYZED.
    """
    recording = await _get_recording_or_404(recording_id, current_user, db)

    if recording.status != "ANALYZED":
        raise HTTPException(
            status_code=status.HTTP_425_TOO_EARLY,
            detail=f"Analysis not ready yet. Current status: {recording.status}",
        )

    result = await db.execute(
        select(Insight).where(Insight.recording_id == recording_id)
    )
    insight = result.scalar_one_or_none()
    if not insight:
        raise HTTPException(status_code=404, detail="Insights not found")

    return InsightResponse(
        recording_id=recording_id,
        overall_sentiment=insight.overall_sentiment,
        sentiment_score=insight.sentiment_score,
        dominant_emotion=insight.dominant_emotion,
        customer_intent=insight.customer_intent,
        intent_confidence=insight.intent_confidence,
        executive_summary=insight.executive_summary,
        product_mentions=insight.product_mentions,
        behavioral_signals=insight.behavioral_signals,
        emotion_arc=insight.emotion_arc,
        confidence_score=insight.confidence_score,
        analysis_tier=insight.analysis_tier,
        requires_human_review=insight.requires_human_review,
        full_analysis=insight.full_analysis,
    )


@router.get("/{recording_id}", response_model=RecordingResponse)
async def get_recording(
    recording_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get basic recording metadata."""
    recording = await _get_recording_or_404(recording_id, current_user, db)
    return _serialize_recording(recording)


@router.delete("/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recording(
    recording_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a recording and all associated files and analysis data.
    Requires: admin or original uploader role.
    """
    recording = await _get_recording_or_404(recording_id, current_user, db)

    # Only admin or the uploader can delete
    if (current_user["role"] != "admin" and
            recording.user_id != current_user["user_id"]):
        raise HTTPException(status_code=403, detail="Not authorized to delete this recording")

    # Remove files
    raw_dir = settings.raw_audio_dir / recording_id
    proc_dir = settings.processed_audio_dir / recording_id
    for d in [raw_dir, proc_dir]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)

    await db.delete(recording)
    await db.commit()


# ─── Helper ─────────────────────────────────────────────────────────────────────
async def _get_recording_or_404(
    recording_id: str,
    current_user: dict,
    db: AsyncSession,
) -> Recording:
    """Fetch recording by ID, verify ownership, raise 404 if not found."""
    result = await db.execute(
        select(Recording).where(Recording.id == recording_id)
    )
    recording = result.scalar_one_or_none()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    company_id = current_user.get("company_id", current_user["user_id"])
    if recording.company_id != company_id and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    return recording
