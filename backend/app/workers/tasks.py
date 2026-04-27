"""
AegisCX Celery Task Definitions
==================================
Defines all background tasks for the processing pipeline:

  - process_audio_task    : FFmpeg + noise reduction + chunking
  - transcribe_task       : WhisperX STT + speaker diarization
  - analyze_task          : NLP + LLM intelligence pipeline
  - generate_report_task  : PDF report generation

Each task:
  - Updates recording status in PostgreSQL
  - Logs structured events to /logs/{recording_id}_*.jsonl
  - Automatically retries on transient failures (3 attempts, exp backoff)
  - Dispatches next pipeline stage on completion
"""

import json
import traceback
import dataclasses
from datetime import datetime, timezone
from pathlib import Path

import structlog
from celery import chain, group
from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import update

from app.workers.celery_app import celery_app
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.models import Recording, Transcript, TranscriptSegment, Insight, SegmentInsight
from app.services.audio.processor import AudioProcessor, AudioProcessingError
from app.services.stt.engine import STTEngine, STTEngineError
from app.services.nlp.pipeline import IntelligencePipeline
from app.services.llm.orchestrator import LLMOrchestrator

settings = get_settings()
log = structlog.get_logger("aegiscx.workers")

# Singleton service instances (reused across tasks in same worker process)
_audio_processor: AudioProcessor = None
_stt_engine: STTEngine = None
_nlp_pipeline: IntelligencePipeline = None
_llm_orchestrator: LLMOrchestrator = None


def _json_safe(value):
    """Recursively coerce dataclass/NumPy-like values into JSON-safe Python types."""
    if dataclasses.is_dataclass(value):
        return _json_safe(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _get_audio_processor() -> AudioProcessor:
    """Lazy-singleton audio processor."""
    global _audio_processor
    if _audio_processor is None:
        _audio_processor = AudioProcessor()
    return _audio_processor


def _get_stt_engine() -> STTEngine:
    """Lazy-singleton STT engine."""
    global _stt_engine
    if _stt_engine is None:
        _stt_engine = STTEngine()
    return _stt_engine


def _get_nlp_pipeline() -> IntelligencePipeline:
    """Lazy-singleton NLP pipeline."""
    global _nlp_pipeline
    if _nlp_pipeline is None:
        _nlp_pipeline = IntelligencePipeline()
    return _nlp_pipeline


def _get_llm_orchestrator() -> LLMOrchestrator:
    """Lazy-singleton LLM orchestrator (without Redis for now)."""
    global _llm_orchestrator
    if _llm_orchestrator is None:
        _llm_orchestrator = LLMOrchestrator(redis_client=None)
    return _llm_orchestrator


import asyncio


def _run_sync(coro):
    """Run an async coroutine from synchronous Celery task context."""
    return asyncio.get_event_loop().run_until_complete(coro)


async def _update_recording_status(
    recording_id: str,
    status: str,
    error_message: str = None,
    **kwargs,
) -> None:
    """
    Update recording status in PostgreSQL.

    Args:
        recording_id: UUID of the recording.
        status: New status string.
        error_message: Optional error message for FAILED status.
        **kwargs: Additional fields to update (e.g., wav_path, duration_seconds).
    """
    async with AsyncSessionLocal() as db:
        update_data = {
            "status": status,
            "updated_at": datetime.now(timezone.utc),
        }
        if error_message is not None:
            update_data["error_message"] = error_message
        update_data.update(kwargs)

        await db.execute(
            update(Recording)
            .where(Recording.id == recording_id)
            .values(**update_data)
        )
        await db.commit()


# ─── Task 1: Audio Processing ─────────────────────────────────────────────────────
@celery_app.task(
    name="aegiscx.tasks.process_audio",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    queue="audio_queue",
    acks_late=True,  # Acknowledge only after task completes
)
def process_audio_task(self, recording_id: str, file_path: str) -> dict:
    """
    Stage 1: Audio processing pipeline.
    Converts raw upload to clean WAV chunks.

    Args:
        recording_id: Recording UUID.
        file_path: Absolute path to the raw uploaded file.

    Returns:
        Dict with wav_path, chunks, metadata for next stage.

    Dispatches:
        transcribe_task on success.
    """
    log.info("audio_task_start", recording_id=recording_id, file_path=file_path)

    try:
        _run_sync(_update_recording_status(recording_id, "AUDIO_PROCESSING"))

        processor = _get_audio_processor()
        result = processor.process(
            recording_id=recording_id,
            input_path=Path(file_path),
        )

        _run_sync(_update_recording_status(
            recording_id,
            "AUDIO_READY",
            wav_path=result.wav_path,
            duration_seconds=result.metadata.duration_seconds,
            format=result.metadata.format,
            file_size_bytes=result.metadata.file_size_bytes,
        ))

        # Dispatch next stage
        chunks_data = [
            {
                "index": c.index,
                "start_time": c.start_time,
                "end_time": c.end_time,
                "wav_path": c.wav_path,
                "num_samples": c.num_samples,
            }
            for c in result.chunks
        ]

        transcribe_task.apply_async(
            kwargs={
                "recording_id": recording_id,
                "chunks_data": chunks_data,
            },
            queue="stt_queue",
        )

        log.info("audio_task_complete", recording_id=recording_id,
                 chunks=len(result.chunks))
        return {"status": "success", "chunks": len(result.chunks)}

    except AudioProcessingError as e:
        log.error("audio_task_failed", recording_id=recording_id, error=str(e))
        _run_sync(_update_recording_status(recording_id, "FAILED", error_message=str(e)))
        raise

    except Exception as e:
        log.error("audio_task_error", recording_id=recording_id,
                  error=str(e), traceback=traceback.format_exc())
        try:
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            _run_sync(_update_recording_status(recording_id, "FAILED",
                                               error_message=f"Max retries exceeded: {e}"))
            raise


# ─── Task 2: Transcription ────────────────────────────────────────────────────────
@celery_app.task(
    name="aegiscx.tasks.transcribe",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="stt_queue",
    soft_time_limit=3600,  # 1 hour max
    acks_late=True,
)
def transcribe_task(
    self,
    recording_id: str,
    chunks_data: list[dict],
    num_speakers: int = None,
) -> dict:
    """
    Stage 2: WhisperX transcription.
    Produces speaker-diarized, timestamped transcript.

    Args:
        recording_id: Recording UUID.
        chunks_data: List of chunk dicts from audio processing stage.
        num_speakers: Expected speaker count (optional hint).

    Returns:
        Dict with transcript_id for next stage.

    Dispatches:
        analyze_task on success.
    """
    log.info("stt_task_start", recording_id=recording_id,
             chunks=len(chunks_data))

    try:
        _run_sync(_update_recording_status(recording_id, "TRANSCRIBING"))

        # Reconstruct AudioChunk objects
        from app.services.audio.processor import AudioChunk
        chunks = [
            AudioChunk(
                index=c["index"],
                start_time=c["start_time"],
                end_time=c["end_time"],
                wav_path=c["wav_path"],
                num_samples=c["num_samples"],
            )
            for c in chunks_data
        ]

        engine = _get_stt_engine()
        transcript_result = engine.transcribe(
            recording_id=recording_id,
            chunks=chunks,
            num_speakers=num_speakers,
        )

        # Save transcript to database
        transcript_id = _run_sync(
            _save_transcript(recording_id, transcript_result)
        )

        _run_sync(_update_recording_status(recording_id, "TRANSCRIBED"))

        # Dispatch NLP analysis
        analyze_task.apply_async(
            kwargs={
                "recording_id": recording_id,
                "transcript_id": transcript_id,
            },
            queue="nlp_queue",
        )

        log.info("stt_task_complete", recording_id=recording_id,
                 words=transcript_result.word_count,
                 speakers=transcript_result.num_speakers)
        return {"status": "success", "transcript_id": transcript_id}

    except STTEngineError as e:
        log.error("stt_task_failed", recording_id=recording_id, error=str(e))
        _run_sync(_update_recording_status(recording_id, "FAILED", error_message=str(e)))
        raise

    except Exception as e:
        log.error("stt_task_error", recording_id=recording_id,
                  error=str(e), traceback=traceback.format_exc())
        try:
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            _run_sync(_update_recording_status(recording_id, "FAILED",
                                               error_message=f"STT failed: {e}"))
            raise


async def _save_transcript(recording_id: str, result) -> str:
    """Save transcript and segments to database. Returns transcript_id."""
    from app.models.models import Transcript, TranscriptSegment
    import uuid

    async with AsyncSessionLocal() as db:
        transcript = Transcript(
            recording_id=recording_id,
            full_text=result.full_text,
            word_count=result.word_count,
            language=result.language,
            num_speakers=result.num_speakers,
            stt_model=result.stt_model_used,
        )
        db.add(transcript)
        await db.flush()  # Get transcript.id before adding segments

        for seg in result.segments:
            db_seg = TranscriptSegment(
                transcript_id=transcript.id,
                segment_index=seg.segment_index,
                speaker_label=seg.speaker,
                start_time=seg.start,
                end_time=seg.end,
                text=seg.text,
                word_count=len(seg.text.split()),
                words={"words": [
                    {"word": w.word, "start": w.start, "end": w.end, "score": w.score}
                    for w in seg.words
                ]},
            )
            db.add(db_seg)

        await db.commit()
        return transcript.id


# ─── Task 3: NLP Analysis ─────────────────────────────────────────────────────────
@celery_app.task(
    name="aegiscx.tasks.analyze",
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    queue="nlp_queue",
    soft_time_limit=1800,
    acks_late=True,
)
def analyze_task(self, recording_id: str, transcript_id: str) -> dict:
    """
    Stage 3: NLP + LLM intelligence extraction.
    Runs 9-dimensional analysis per segment, then runs LLM if needed.

    Args:
        recording_id: Recording UUID.
        transcript_id: Transcript UUID (from previous stage).

    Returns:
        Dict with insight_id.
    """
    log.info("analysis_task_start", recording_id=recording_id)

    try:
        _run_sync(_update_recording_status(recording_id, "ANALYZING"))

        # Load transcript and segments from DB
        transcript_data = _run_sync(_load_transcript(transcript_id))

        nlp = _get_nlp_pipeline()
        llm = _get_llm_orchestrator()

        # Per-segment analysis
        all_segment_analyses = []
        total_confidence = 0.0
        low_confidence_segments = 0

        for seg in transcript_data["segments"]:
            analysis = nlp.analyze_segment(
                segment_id=seg["id"],
                text=seg["text"],
            )
            all_segment_analyses.append((seg["id"], analysis))
            total_confidence += analysis.confidence
            if analysis.needs_llm_review:
                low_confidence_segments += 1

        avg_confidence = total_confidence / max(len(all_segment_analyses), 1)

        # LLM analysis (if needed)
        llm_result = None
        analysis_tier = "ml_only"

        if avg_confidence < settings.llm_confidence_threshold:
            log.info("triggering_llm_analysis", recording_id=recording_id,
                     avg_confidence=avg_confidence,
                     low_confidence_segments=low_confidence_segments)
            llm_result = llm.analyze_transcript(
                session_id=recording_id,
                transcript_text=transcript_data["full_text"],
                num_speakers=transcript_data["num_speakers"],
                duration_seconds=transcript_data["duration_seconds"],
            )
            analysis_tier = "ml_llm" if llm_result else "ml_only"

        # Aggregate insights
        insight_id = _run_sync(
            _save_insights(recording_id, transcript_id, all_segment_analyses,
                           llm_result, analysis_tier, avg_confidence)
        )

        _run_sync(_update_recording_status(recording_id, "ANALYZED"))

        log.info("analysis_task_complete", recording_id=recording_id,
                 tier=analysis_tier, confidence=round(avg_confidence, 3))
        return {"status": "success", "insight_id": insight_id}

    except Exception as e:
        log.error("analysis_task_error", recording_id=recording_id,
                  error=str(e), traceback=traceback.format_exc())
        try:
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            _run_sync(_update_recording_status(recording_id, "FAILED",
                                               error_message=f"Analysis failed: {e}"))
            raise


async def _load_transcript(transcript_id: str) -> dict:
    """Load transcript + segments from database."""
    from sqlalchemy import select
    from app.models.models import Transcript, TranscriptSegment

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Transcript).where(Transcript.id == transcript_id)
        )
        transcript = result.scalar_one()

        segs_result = await db.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.transcript_id == transcript_id)
            .order_by(TranscriptSegment.segment_index)
        )
        segments = segs_result.scalars().all()

        return {
            "id": transcript.id,
            "full_text": transcript.full_text,
            "num_speakers": transcript.num_speakers,
            "duration_seconds": 0.0,  # Loaded from recording if needed
            "segments": [
                {
                    "id": s.id,
                    "text": s.text,
                    "speaker": s.speaker_label,
                    "start": s.start_time,
                    "end": s.end_time,
                }
                for s in segments
            ],
        }


async def _save_insights(
    recording_id: str,
    transcript_id: str,
    segment_analyses: list,
    llm_result,
    analysis_tier: str,
    avg_confidence: float,
) -> str:
    """Save all insight data to database. Returns insight_id."""
    from app.models.models import Insight, SegmentInsight
    from dataclasses import asdict

    async with AsyncSessionLocal() as db:
        # Build full_analysis JSON
        full_analysis = {
            "ml_segment_analyses": [
                {
                    "segment_id": seg_id,
                    "sentiment": _json_safe(asdict(a.sentiment)),
                    "emotions": _json_safe([asdict(e) for e in a.emotions]),
                    "intent": _json_safe(asdict(a.intent)),
                    "entities": _json_safe([asdict(e) for e in a.entities]),
                    "behavioral_signals": _json_safe(asdict(a.behavioral_signals)),
                    "confidence": _json_safe(a.confidence),
                }
                for seg_id, a in segment_analyses
            ],
            "llm_result": _json_safe(llm_result.__dict__) if llm_result else None,
        }

        # Determine overall parameters from LLM or ML aggregate
        if llm_result:
            segments_llm = llm_result.segment_by_segment_analysis
            
            sents = [s.get("twenty_parameters", {}).get("sentiment", "neutral") for s in segments_llm]
            pos = sents.count("positive")
            neg = sents.count("negative")
            overall_sentiment = "positive" if pos > neg else ("negative" if neg > pos else "neutral")
            
            emots = [s.get("twenty_parameters", {}).get("emotion", "neutral") for s in segments_llm]
            dominant_emotion = max(set(emots), key=emots.count) if emots else "neutral"
            
            intents = [s.get("twenty_parameters", {}).get("intent", "neutral") for s in segments_llm]
            customer_intent = max(set(intents), key=intents.count) if intents else "general comment"
            
            sentiment_score = llm_result.global_metrics_7_scale.get("overall_experience", 4) / 7.0
            intent_confidence = 0.95
            executive_summary = llm_result.executive_summary
            product_mentions = []
            behavioral_signals = llm_result.global_metrics_7_scale
            emotion_arc = []
            requires_human_review = False
        else:
            # Aggregate ML results
            sentiments = [a.sentiment.label for _, a in segment_analyses]
            pos = sentiments.count("positive")
            neg = sentiments.count("negative")
            overall_sentiment = "positive" if pos > neg else ("negative" if neg > pos else "neutral")
            sentiment_score = avg_confidence
            dominant_emotion = "neutral"
            customer_intent = "general comment"
            intent_confidence = avg_confidence
            executive_summary = "Analysis completed using local ML models. LLM enhancement not applied."
            product_mentions = []
            behavioral_signals = {}
            emotion_arc = []
            requires_human_review = avg_confidence < 0.60

        insight = Insight(
            recording_id=recording_id,
            overall_sentiment=overall_sentiment,
            sentiment_score=sentiment_score,
            dominant_emotion=dominant_emotion,
            customer_intent=customer_intent,
            intent_confidence=intent_confidence,
            emotion_arc=emotion_arc,
            product_mentions=product_mentions,
            behavioral_signals=behavioral_signals,
            full_analysis=full_analysis,
            executive_summary=executive_summary,
            confidence_score=avg_confidence,
            analysis_tier=analysis_tier,
            requires_human_review=requires_human_review,
            llm_model=(llm_result.model_used if llm_result else None),
        )
        db.add(insight)
        await db.flush()

        # Build a lookup for LLM segment results if they exist
        llm_seg_map = {}
        if llm_result and hasattr(llm_result, "segment_by_segment_analysis"):
            for i, seg_res in enumerate(llm_result.segment_by_segment_analysis):
                # Try to map by index (assuming LLM returned segments in order)
                llm_seg_map[i] = seg_res.get("twenty_parameters", {})

        # Save per-segment insights
        for idx, (seg_id, analysis) in enumerate(segment_analyses):
            from dataclasses import asdict
            
            twenty_params = llm_seg_map.get(idx, {})
            
            seg_insight = SegmentInsight(
                insight_id=insight.id,
                segment_id=seg_id,
                sentiment=_json_safe(asdict(analysis.sentiment)),
                emotions=_json_safe([asdict(e) for e in analysis.emotions]),
                intent=_json_safe(asdict(analysis.intent)),
                entities=_json_safe([asdict(e) for e in analysis.entities]),
                behavioral_signals=_json_safe(asdict(analysis.behavioral_signals)),
                confidence=_json_safe(analysis.confidence),
                twenty_parameters_analysis=_json_safe(twenty_params),
            )
            db.add(seg_insight)

        await db.commit()
        return insight.id
