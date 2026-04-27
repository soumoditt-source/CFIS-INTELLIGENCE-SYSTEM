"""
CFIS Inline Processing Pipeline
=================================
Runs the complete Audio → STT → NLP → LLM pipeline synchronously inside
a FastAPI BackgroundTask thread — no Celery or Redis required.

Called from the upload endpoint when USE_CELERY=false or when Redis is
unreachable. Each stage updates the Recording status in SQLite so the
frontend's real-time polling always shows accurate progress.

Stage order:
  1. AudioProcessor  → WAV conversion, noise reduction, chunking
  2. STTEngine       → WhisperX / faster-whisper transcription
  3. IntelligencePipeline → 9-dim NLP analysis per segment
  4. LLMOrchestrator → 20-param LLM refinement (if confidence < threshold)
  5. Persist         → Save Transcript + Insights to DB, mark ANALYZED
"""

import asyncio
import dataclasses
import traceback
import uuid
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.models import (
    Insight,
    Recording,
    SegmentInsight,
    Transcript,
    TranscriptSegment,
)

settings = get_settings()
log = structlog.get_logger("cfis.inline")


# ─── Event-loop helper (run async from sync thread) ───────────────────────────

def _run(coro):
    """
    Execute an async coroutine from a synchronous background thread.
    Creates a fresh event loop per call — safe for thread-pool execution.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()


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


# ─── Database helpers ──────────────────────────────────────────────────────────

async def _set_status(
    recording_id: str,
    status: str,
    error_message: str = None,
    **extra_fields,
) -> None:
    """Update Recording.status (and optional extra columns) in one commit."""
    async with AsyncSessionLocal() as db:
        values = {
            "status": status,
            "updated_at": datetime.now(timezone.utc),
        }
        if error_message is not None:
            values["error_message"] = str(error_message)[:2000]
        # Coerce Path objects to str to avoid SQLAlchemy type errors
        for k, v in extra_fields.items():
            values[k] = str(v) if isinstance(v, Path) else v
        await db.execute(
            update(Recording)
            .where(Recording.id == recording_id)
            .values(**values)
        )
        await db.commit()


async def _persist_transcript(recording_id: str, result) -> str:
    """
    Save TranscriptResult → DB.  Returns the new transcript UUID.
    """
    async with AsyncSessionLocal() as db:
        t = Transcript(
            id=str(uuid.uuid4()),
            recording_id=recording_id,
            full_text=result.full_text,
            word_count=result.word_count,
            language=result.language,
            num_speakers=result.num_speakers,
            stt_model=result.stt_model_used,
        )
        db.add(t)
        await db.flush()   # get t.id before adding children

        for seg in result.segments:
            words_json = []
            if hasattr(seg, "words") and seg.words:
                words_json = [
                    {
                        "word": w.word,
                        "start": w.start,
                        "end": w.end,
                        "score": getattr(w, "score", 1.0),
                    }
                    for w in seg.words
                ]
            db.add(
                TranscriptSegment(
                    id=str(uuid.uuid4()),
                    transcript_id=t.id,
                    segment_index=seg.segment_index,
                    speaker_label=getattr(seg, "speaker", "SPEAKER_00"),
                    start_time=seg.start,
                    end_time=seg.end,
                    text=seg.text,
                    word_count=len(seg.text.split()),
                    words=words_json,
                )
            )
        await db.commit()
        return t.id


async def _load_segments_for_nlp(transcript_id: str) -> list[dict]:
    """Return [{id, text}] for every segment of a transcript."""
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(TranscriptSegment)
                .where(TranscriptSegment.transcript_id == transcript_id)
                .order_by(TranscriptSegment.segment_index)
            )
        ).scalars().all()
        return [{"id": r.id, "text": r.text} for r in rows]


async def _load_full_text(transcript_id: str) -> tuple[str, int]:
    """Return (full_text, num_speakers) from the Transcript row."""
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(Transcript).where(Transcript.id == transcript_id)
            )
        ).scalar_one()
        return row.full_text, (row.num_speakers or 1)


def _llm_result_to_dict(llm_result) -> Optional[dict]:
    """
    Safely serialize an LLMAnalysisResult dataclass to a JSON-safe dict.
    Falls back to a minimal summary dict if serialization fails.
    """
    if llm_result is None:
        return None
    try:
        if dataclasses.is_dataclass(llm_result):
            return dataclasses.asdict(llm_result)
        return vars(llm_result)
    except Exception as e:
        log.warning("llm_result_serialization_failed", error=str(e))
        return {
            "model_used": getattr(llm_result, "model_used", "unknown"),
            "latency_ms": getattr(llm_result, "latency_ms", 0),
            "from_cache": getattr(llm_result, "from_cache", False),
            "executive_summary": getattr(llm_result, "executive_summary", ""),
        }


def _majority_sentiment(counter: Counter) -> str:
    """Return a stable overall sentiment label from a sentiment distribution."""
    positive = counter.get("positive", 0)
    negative = counter.get("negative", 0)
    neutral = counter.get("neutral", 0)
    if positive and negative and abs(positive - negative) <= 1:
        return "mixed"
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral" if neutral or not counter else counter.most_common(1)[0][0]


def _build_highlights(segment_analyses: list[tuple[str, object]]) -> tuple[list[str], list[str]]:
    """Collect short complaint and praise snippets for the detail view/report."""
    complaints: list[str] = []
    praises: list[str] = []

    for _, analysis in segment_analyses:
        snippet = " ".join((analysis.text or "").split()).strip()
        if not snippet:
            continue
        trimmed = snippet[:180]
        if analysis.sentiment.label == "negative" and trimmed not in complaints:
            complaints.append(trimmed)
        elif analysis.sentiment.label == "positive" and trimmed not in praises:
            praises.append(trimmed)

    return complaints[:3], praises[:3]


def _build_product_mentions(
    segment_analyses: list[tuple[str, object]],
    company_name: Optional[str],
    product_category: Optional[str],
) -> list[dict]:
    """Infer product or brand mentions from NER and upload context."""
    buckets: dict[str, dict] = {}

    for _, analysis in segment_analyses:
        seen_names: set[str] = set()
        for entity in analysis.entities:
            if entity.entity_type not in {"ORG", "MISC"}:
                continue
            name = " ".join(str(entity.text).replace("_", " ").split()).strip(" .,:;!?-")
            if len(name) < 3 or name.lower() in seen_names:
                continue
            seen_names.add(name.lower())
            bucket = buckets.setdefault(
                name,
                {
                    "product_name": name,
                    "counts": Counter(),
                    "specific_feedback": "",
                    "aspect": product_category or None,
                },
            )
            bucket["counts"][analysis.sentiment.label] += 1
            if not bucket["specific_feedback"]:
                bucket["specific_feedback"] = analysis.text[:220]

    if not buckets and (product_category or company_name):
        fallback_name = product_category or company_name or "Customer feedback"
        fallback_text = segment_analyses[0][1].text[:220] if segment_analyses else ""
        buckets[fallback_name] = {
            "product_name": fallback_name,
            "counts": Counter({"neutral": max(len(segment_analyses), 1)}),
            "specific_feedback": fallback_text,
            "aspect": product_category if company_name and product_category else None,
        }

    product_mentions: list[dict] = []
    for bucket in buckets.values():
        counts = bucket["counts"]
        product_mentions.append(
            {
                "product_name": bucket["product_name"],
                "sentiment": _majority_sentiment(counts),
                "aspect": bucket["aspect"],
                "specific_feedback": bucket["specific_feedback"],
                "mention_count": int(sum(counts.values())),
            }
        )

    product_mentions.sort(key=lambda item: item.get("mention_count", 0), reverse=True)
    return product_mentions[:8]


def _build_behavioral_summary(segment_analyses: list[tuple[str, object]], llm_result) -> dict:
    """Aggregate behavioral cues across the full transcript."""
    if not segment_analyses and not llm_result:
        return {}

    count = max(len(segment_analyses), 1)
    hesitation = 0.0
    frustration = 0.0
    satisfaction = 0.0
    overall = 0.0
    purchase_signals = 0
    high_risk_segments = 0

    for _, analysis in segment_analyses:
        signals = analysis.behavioral_signals
        hesitation += float(signals.hesitation_score)
        frustration += float(signals.frustration_score)
        satisfaction += float(signals.satisfaction_score)
        overall += float(signals.overall_behavioral_score)
        purchase_signals += int(signals.purchase_intent_signals)
        if signals.frustration_score >= 0.5:
            high_risk_segments += 1

    summary = {
        "hesitation_level_score": round(hesitation / count, 3),
        "frustration_level_score": round(frustration / count, 3),
        "satisfaction_level_score": round(satisfaction / count, 3),
        "overall_behavioral_score": round(overall / count, 3),
        "purchase_intent_signal_count": purchase_signals,
        "purchase_intent_segment_ratio": round(purchase_signals / count, 3),
        "high_risk_segment_count": high_risk_segments,
    }

    if llm_result and getattr(llm_result, "global_metrics_7_scale", None):
        summary["llm_7_scale"] = _json_safe(llm_result.global_metrics_7_scale)

    return summary


def _build_emotion_arc(segment_analyses: list[tuple[str, object]]) -> list[dict]:
    """Create a lightweight emotion timeline that the UI can visualize."""
    emotion_arc: list[dict] = []
    for index, (segment_id, analysis) in enumerate(segment_analyses):
        dominant = analysis.emotions[0].emotion if analysis.emotions else "neutral"
        emotion_arc.append(
            {
                "segment_index": index,
                "segment_id": segment_id,
                "emotion": dominant,
                "sentiment": analysis.sentiment.label,
                "confidence": round(float(analysis.confidence), 3),
            }
        )
    return emotion_arc


def _build_local_summary(
    overall_sentiment: str,
    dominant_emotion: str,
    customer_intent: str,
    avg_confidence: float,
    product_mentions: list[dict],
    behavioral_signals: dict,
    segment_count: int,
    complaints: list[str],
    praises: list[str],
) -> str:
    """
    Generate a dense paragraph-level summary when the LLM layer is skipped.

    The goal is to preserve contextual richness without becoming verbose:
    one compact paragraph for the overall conversation and one for the most
    actionable praise and friction signals.
    """
    focus_item = product_mentions[0]["product_name"] if product_mentions else "the reviewed product"
    frustration = behavioral_signals.get("frustration_level_score", 0)
    satisfaction = behavioral_signals.get("satisfaction_level_score", 0)
    hesitation = behavioral_signals.get("hesitation_level_score", 0)

    overview = (
        f"This session covers {focus_item} across {segment_count} analyzed segments and trends "
        f"{overall_sentiment} overall. The dominant emotional tone is {dominant_emotion}, while "
        f"the primary customer intent is {customer_intent}. Behavioral scoring suggests "
        f"{'strong satisfaction' if satisfaction >= 0.35 else 'measured satisfaction'}"
        f"{', elevated frustration' if frustration >= 0.35 else ''}"
        f"{', and noticeable hesitation' if hesitation >= 0.2 else ''}. "
        f"Local confidence for this interpretation is {avg_confidence:.0%}."
    )

    evidence_parts: list[str] = []
    if praises:
        evidence_parts.append(f"Positive evidence includes: {praises[0]}")
    if complaints:
        evidence_parts.append(f"Primary friction point: {complaints[0]}")

    if not evidence_parts:
        evidence_parts.append(
            "The transcript is structurally clear, but no single praise or complaint dominated the exchange."
        )

    return f"{overview}\n\n{' '.join(evidence_parts)}"


async def _persist_insights(
    recording_id: str,
    transcript_id: str,
    segment_analyses: list[tuple[str, object]],   # [(seg_id, SegmentAnalysis)]
    llm_result,
    analysis_tier: str,
    avg_confidence: float,
    company_name: Optional[str] = None,
    product_category: Optional[str] = None,
) -> str:
    """
    Build and save Insight + SegmentInsight rows.  Returns insight UUID.
    """
    sentiments = Counter(a.sentiment.label for _, a in segment_analyses)
    emotion_labels = Counter(
        a.emotions[0].emotion for _, a in segment_analyses if a.emotions
    )
    intent_labels = Counter(a.intent.label for _, a in segment_analyses)

    overall_sentiment = _majority_sentiment(sentiments)
    dominant_emotion = (
        emotion_labels.most_common(1)[0][0] if emotion_labels else "neutral"
    )
    customer_intent = (
        intent_labels.most_common(1)[0][0] if intent_labels else "general comment"
    )

    complaints, praises = _build_highlights(segment_analyses)
    product_mentions = _build_product_mentions(
        segment_analyses,
        company_name=company_name,
        product_category=product_category,
    )
    behavioral_signals = _build_behavioral_summary(segment_analyses, llm_result)
    emotion_arc = _build_emotion_arc(segment_analyses)

    sentiment_score_map = {
        "positive": 0.85,
        "neutral": 0.5,
        "negative": 0.15,
        "mixed": 0.5,
    }
    if segment_analyses:
        sentiment_score = round(
            sum(
                sentiment_score_map.get(a.sentiment.label, 0.5)
                for _, a in segment_analyses
            )
            / len(segment_analyses),
            4,
        )
        intent_confidence = round(
            sum(float(a.intent.score) for _, a in segment_analyses)
            / len(segment_analyses),
            4,
        )
    else:
        sentiment_score = 0.5
        intent_confidence = round(avg_confidence, 4)

    requires_human_review = avg_confidence < 0.60
    review_reason = "Low confidence analysis requires human review." if requires_human_review else None
    llm_model_used = None
    executive_summary = _build_local_summary(
        overall_sentiment=overall_sentiment,
        dominant_emotion=dominant_emotion,
        customer_intent=customer_intent,
        avg_confidence=avg_confidence,
        product_mentions=product_mentions,
        behavioral_signals=behavioral_signals,
        segment_count=len(segment_analyses),
        complaints=complaints,
        praises=praises,
    )

    if llm_result:
        g = llm_result.global_metrics_7_scale or {}
        segments_llm = llm_result.segment_by_segment_analysis or []

        llm_sentiments = Counter(
            s.get("twenty_parameters", {}).get("sentiment", "neutral")
            for s in segments_llm if isinstance(s, dict)
        )
        if llm_sentiments:
            overall_sentiment = _majority_sentiment(llm_sentiments)

        llm_emotions = Counter(
            s.get("twenty_parameters", {}).get("emotion", "neutral")
            for s in segments_llm if isinstance(s, dict)
        )
        if llm_emotions:
            dominant_emotion = llm_emotions.most_common(1)[0][0]

        llm_intents = Counter(
            s.get("twenty_parameters", {}).get("intent", "general comment")
            for s in segments_llm if isinstance(s, dict)
        )
        if llm_intents:
            customer_intent = llm_intents.most_common(1)[0][0]

        executive_summary = llm_result.executive_summary or executive_summary
        sentiment_score = round(g.get("product_sentiment", 4) / 7.0, 4) if g else sentiment_score
        intent_confidence = max(intent_confidence, 0.9)
        requires_human_review = False
        review_reason = None
        llm_model_used = llm_result.model_used

    segment_summaries = []
    for seg_id, a in segment_analyses:
        try:
            segment_summaries.append({
                "segment_id": seg_id,
                "sentiment": _json_safe(asdict(a.sentiment)),
                "top_emotion": _json_safe(asdict(a.emotions[0])) if a.emotions else None,
                "intent": _json_safe(asdict(a.intent)),
                "behavioral": _json_safe(asdict(a.behavioral_signals)),
                "confidence": _json_safe(a.confidence),
            })
        except Exception as e:
            log.warning("segment_summary_serialization_failed", seg_id=seg_id, error=str(e))

    llm_payload = _llm_result_to_dict(llm_result) or {}
    if complaints and "key_complaints" not in llm_payload:
        llm_payload["key_complaints"] = complaints
    if praises and "key_praises" not in llm_payload:
        llm_payload["key_praises"] = praises

    full_analysis = {
        "context": {
            "company_name": company_name,
            "product_category": product_category,
        },
        "conversation_overview": {
            "overall_sentiment": overall_sentiment,
            "dominant_emotion": dominant_emotion,
            "customer_intent": customer_intent,
            "segment_count": len(segment_analyses),
            "top_focus": product_mentions[0]["product_name"] if product_mentions else None,
        },
        "ml_segment_count": len(segment_analyses),
        "ml_avg_confidence": round(avg_confidence, 4),
        "llm_result": llm_payload,
        "key_complaints": complaints,
        "key_praises": praises,
        "segment_summaries": segment_summaries,
    }

    llm_seg_map: dict[int, dict] = {}
    if llm_result and hasattr(llm_result, "segment_by_segment_analysis"):
        for i, seg_data in enumerate(llm_result.segment_by_segment_analysis):
            if isinstance(seg_data, dict):
                llm_seg_map[i] = seg_data.get("twenty_parameters", {})

    async with AsyncSessionLocal() as db:
        insight = Insight(
            id=str(uuid.uuid4()),
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
            review_reason=review_reason,
            llm_model=llm_model_used,
            ml_models_used={
                "embedding_model": settings.embedding_model,
                "sentiment_model": settings.sentiment_model,
                "emotion_model": settings.emotion_model,
                "intent_model": settings.intent_model,
                "ner_model": settings.ner_model,
                "stt_model": settings.whisper_model_size,
            },
        )
        db.add(insight)
        await db.flush()

        for idx, (seg_id, analysis) in enumerate(segment_analyses):
            try:
                db.add(
                    SegmentInsight(
                        id=str(uuid.uuid4()),
                        insight_id=insight.id,
                        segment_id=seg_id,
                        sentiment=_json_safe(asdict(analysis.sentiment)),
                        emotions=_json_safe([asdict(e) for e in analysis.emotions]),
                        intent=_json_safe(asdict(analysis.intent)),
                        entities=_json_safe([asdict(e) for e in analysis.entities]),
                        behavioral_signals=_json_safe(asdict(analysis.behavioral_signals)),
                        confidence=_json_safe(analysis.confidence),
                        twenty_parameters_analysis=_json_safe(llm_seg_map.get(idx, {})),
                    )
                )
            except Exception as e:
                log.warning("segment_insight_save_failed", seg_id=seg_id, error=str(e))

        await db.commit()
        return insight.id


# ─── Main pipeline function ────────────────────────────────────────────────────

def process_pipeline_inline(
    recording_id: str,
    file_path: str,
    num_speakers: Optional[int] = None,
    company_name: Optional[str] = None,
    product_category: Optional[str] = None,
) -> None:
    """
    Full processing pipeline — runs in a FastAPI BackgroundTask thread.

    Stages:
      PENDING → AUDIO_PROCESSING → AUDIO_READY
              → TRANSCRIBING     → TRANSCRIBED
              → ANALYZING        → ANALYZED
              (or FAILED at any point with error_message)

    Args:
        recording_id: UUID of the Recording row.
        file_path:    Absolute path to the uploaded original file.
        num_speakers: Optional speaker count hint for diarization.
        company_name: Optional company context provided during upload.
        product_category: Optional product context provided during upload.
    """
    log.info("inline_pipeline_start", recording_id=recording_id, file=file_path)

    # ══ Stage 1 — Audio Processing ═══════════════════════════════════════════
    try:
        _run(_set_status(recording_id, "AUDIO_PROCESSING"))

        from app.services.audio.processor import AudioProcessor
        audio_result = AudioProcessor().process(
            recording_id=recording_id,
            input_path=Path(file_path),
        )
        chunks = audio_result.chunks

        _run(
            _set_status(
                recording_id,
                "AUDIO_READY",
                wav_path=str(audio_result.wav_path),   # ensure str, not Path
                duration_seconds=float(audio_result.metadata.duration_seconds),
            )
        )
        log.info("audio_ok", recording_id=recording_id, chunks=len(chunks))

    except Exception as exc:
        tb = traceback.format_exc()
        log.error("audio_failed", recording_id=recording_id, error=str(exc), traceback=tb)
        _run(_set_status(recording_id, "FAILED",
                         error_message=f"Audio processing error: {exc}"))
        return

    # ══ Stage 2 — Speech-to-Text ═════════════════════════════════════════════
    try:
        _run(_set_status(recording_id, "TRANSCRIBING"))

        from app.services.stt.engine import STTEngine
        transcript_result = STTEngine().transcribe(
            recording_id=recording_id,
            chunks=chunks,
            num_speakers=num_speakers,
        )

        # Guard: if STT produced no segments, create a placeholder
        if not transcript_result.segments:
            log.warning("stt_no_segments", recording_id=recording_id,
                        message="STT returned 0 segments — may be silent audio or unsupported language")

        transcript_id = _run(_persist_transcript(recording_id, transcript_result))

        _run(_set_status(recording_id, "TRANSCRIBED"))
        log.info("stt_ok", recording_id=recording_id,
                 words=transcript_result.word_count,
                 speakers=transcript_result.num_speakers)

    except Exception as exc:
        tb = traceback.format_exc()
        log.error("stt_failed", recording_id=recording_id, error=str(exc), traceback=tb)
        _run(_set_status(recording_id, "FAILED",
                         error_message=f"Transcription error: {exc}"))
        return

    # ══ Stage 3 — NLP Analysis ═══════════════════════════════════════════════
    try:
        _run(_set_status(recording_id, "ANALYZING"))

        from app.services.nlp.pipeline import IntelligencePipeline
        nlp = IntelligencePipeline()

        segments = _run(_load_segments_for_nlp(transcript_id))
        segment_analyses: list[tuple[str, object]] = []
        total_confidence = 0.0
        low_confidence_segments = 0
        llm_required = False

        for seg in segments:
            text = (seg.get("text") or "").strip()
            if len(text) < 3:
                continue
            try:
                analysis = nlp.analyze_segment(
                    segment_id=seg["id"],
                    text=text,
                )
                segment_analyses.append((seg["id"], analysis))
                total_confidence += analysis.confidence
                if analysis.needs_llm_review:
                    low_confidence_segments += 1
            except Exception as seg_exc:
                # Isolate per-segment failures — don't abort the whole pipeline
                log.warning("nlp_segment_failed",
                            recording_id=recording_id,
                            seg_id=seg.get("id"),
                            error=str(seg_exc))

        if segment_analyses:
            avg_confidence = total_confidence / len(segment_analyses)
        else:
            # No segments could be analyzed — use a neutral fallback confidence
            avg_confidence = 0.70
            log.warning("nlp_no_segments_analyzed", recording_id=recording_id,
                        message="NLP produced 0 results; will attempt LLM-only analysis")
            llm_required = True   # Force LLM to cover for missing NLP

        log.info("nlp_ok", recording_id=recording_id,
                 segments=len(segment_analyses),
                 avg_confidence=round(avg_confidence, 3),
                 low_confidence_segments=low_confidence_segments)

    except Exception as exc:
        tb = traceback.format_exc()
        log.warning("nlp_stage_failed_falling_back",
                    recording_id=recording_id,
                    error=str(exc),
                    traceback=tb)
        # Do NOT mark FAILED — let LLM stage cover for the missing NLP.
        # This handles the case where torch/transformers not yet installed.
        segment_analyses = []
        avg_confidence = 0.60
        llm_required = True
        log.info("nlp_degraded_llm_only",
                 recording_id=recording_id,
                 message="NLP skipped due to error; proceeding with LLM-only analysis")

    # ══ Stage 4 — LLM Refinement (optional) ══════════════════════════════════
    llm_result     = None
    analysis_tier  = "ml_only"

    should_call_llm = (
        llm_required
        or avg_confidence < settings.llm_confidence_threshold
    )

    if should_call_llm:
        try:
            from app.services.llm.orchestrator import LLMOrchestrator
            full_text, num_spk = _run(_load_full_text(transcript_id))

            if full_text and len(full_text.strip()) > 10:
                llm_result = LLMOrchestrator(redis_client=None).analyze_transcript(
                    session_id=recording_id,
                    transcript_text=full_text,
                    company_name=company_name or "Unknown Company",
                    product_category=product_category or "Customer Feedback",
                    num_speakers=num_spk,
                    duration_seconds=float(audio_result.metadata.duration_seconds),
                )
                analysis_tier = "ml_llm" if llm_result else "ml_only"
                if llm_result:
                    log.info("llm_ok", recording_id=recording_id, model=llm_result.model_used)
                else:
                    log.warning(
                        "llm_unavailable_continuing_ml_only",
                        recording_id=recording_id,
                    )
            else:
                log.warning("llm_skipped_empty_transcript", recording_id=recording_id)

        except Exception as exc:
            # LLM failure is non-critical — fall through with ML-only results
            log.warning("llm_skipped", recording_id=recording_id, error=str(exc))

    # ══ Stage 5 — Persist Insights ════════════════════════════════════════════
    try:
        insight_id = _run(
            _persist_insights(
                recording_id=recording_id,
                transcript_id=transcript_id,
                segment_analyses=segment_analyses,
                llm_result=llm_result,
                analysis_tier=analysis_tier,
                avg_confidence=avg_confidence,
                company_name=company_name,
                product_category=product_category,
            )
        )
        _run(_set_status(recording_id, "ANALYZED"))
        log.info("pipeline_complete", recording_id=recording_id,
                 tier=analysis_tier, insight_id=insight_id)

    except Exception as exc:
        tb = traceback.format_exc()
        log.error("persist_failed", recording_id=recording_id, error=str(exc), traceback=tb)
        _run(_set_status(recording_id, "FAILED",
                         error_message=f"Failed to save insights: {exc}"))
