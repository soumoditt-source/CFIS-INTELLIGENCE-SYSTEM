"""
AegisCX reports and admin routes.

Reports:
  GET /reports/{id}/json - Full structured analysis report
  GET /reports/{id}/pdf  - PDF report download

Admin (requires admin role):
  GET  /admin/jobs        - All processing jobs + status
  POST /admin/corrections - Submit human correction for RLHF
  GET  /admin/users       - List company users
"""

from datetime import datetime, timezone
from html import escape
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.models import (
    HumanCorrection,
    Insight,
    Recording,
    Transcript,
    TranscriptSegment,
    User,
)
import structlog

router = APIRouter()
REPORT_WARNING_HEADER = "X-AegisCX-Report-Warning"
log = structlog.get_logger("aegiscx.reports")


class CorrectionRequest(BaseModel):
    insight_id: str
    field_name: str
    original_value: dict
    corrected_value: dict
    reason: Optional[str] = None


@router.get("/{recording_id}/json")
async def get_full_report(
    recording_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Full structured analysis report as JSON.
    Combines recording metadata, transcript, and all AI insights.
    """
    recording_result = await db.execute(
        select(Recording).where(Recording.id == recording_id)
    )
    recording = recording_result.scalar_one_or_none()
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    company_id = current_user.get("company_id", current_user["user_id"])
    if recording.company_id != company_id and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    if recording.status != "ANALYZED":
        raise HTTPException(
            status_code=425, detail=f"Analysis not ready: {recording.status}"
        )

    transcript_result = await db.execute(
        select(Transcript).where(Transcript.recording_id == recording_id)
    )
    transcript = transcript_result.scalar_one_or_none()

    transcript_segments = []
    if transcript:
        segments_result = await db.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.transcript_id == transcript.id)
            .order_by(TranscriptSegment.segment_index)
        )
        transcript_segments = [
            {
                "segment_index": seg.segment_index,
                "speaker_label": seg.speaker_label,
                "start_time": seg.start_time,
                "end_time": seg.end_time,
                "text": seg.text,
                "word_count": seg.word_count,
            }
            for seg in segments_result.scalars().all()
        ]

    insight_result = await db.execute(
        select(Insight).where(Insight.recording_id == recording_id)
    )
    insight = insight_result.scalar_one_or_none()

    full_analysis = insight.full_analysis if insight else {}
    llm_result = full_analysis.get("llm_result", {}) if isinstance(full_analysis, dict) else {}
    global_metrics = (
        llm_result.get("global_metrics_7_scale", {})
        if isinstance(llm_result, dict)
        else {}
    )

    return {
        "report_id": recording_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recording": {
            "id": recording.id,
            "filename": recording.original_filename,
            "duration_seconds": recording.duration_seconds,
            "format": recording.format,
            "uploaded_at": recording.created_at.isoformat(),
        },
        "transcript": {
            "full_text": transcript.full_text if transcript else None,
            "verbatim_conversation": transcript.full_text if transcript else None,
            "word_count": transcript.word_count if transcript else None,
            "num_speakers": transcript.num_speakers if transcript else None,
            "language": transcript.language if transcript else "en",
            "model": transcript.stt_model if transcript else None,
            "segments": transcript_segments,
        },
        "intelligence": {
            "executive_summary": insight.executive_summary if insight else None,
            "overall_sentiment": insight.overall_sentiment if insight else None,
            "sentiment_score": insight.sentiment_score if insight else None,
            "dominant_emotion": insight.dominant_emotion if insight else None,
            "customer_intent": insight.customer_intent if insight else None,
            "intent_confidence": insight.intent_confidence if insight else None,
            "product_mentions": insight.product_mentions if insight else [],
            "behavioral_signals": insight.behavioral_signals if insight else {},
            "emotion_arc": insight.emotion_arc if insight else [],
            "confidence_score": insight.confidence_score if insight else None,
            "analysis_tier": insight.analysis_tier if insight else None,
            "requires_human_review": insight.requires_human_review if insight else False,
            "llm_model": insight.llm_model if insight else None,
            "global_metrics_7_scale": global_metrics,
            "full_analysis": full_analysis,
        },
    }


@router.get("/{recording_id}/pdf")
async def download_pdf_report(
    recording_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate and download a formatted PDF report for a recording.
    Uses WeasyPrint for high-quality PDF output when available.
    """
    full_report = await get_full_report(recording_id, current_user, db)

    html_content = _generate_report_html(full_report)

    try:
        from weasyprint import HTML

        pdf_bytes = HTML(string=html_content).write_pdf()

        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="aegiscx_report_{recording_id[:8]}.pdf"'
                ),
                "Content-Length": str(len(pdf_bytes)),
                "X-AegisCX-Report-Format": "pdf",
            },
        )
    except Exception as exc:
        # WeasyPrint can be importable while still missing native runtime
        # libraries on Windows. Fall back to HTML instead of returning 500.
        log.warning("report_pdf_fallback_html", recording_id=recording_id, error=str(exc))
        return Response(
            content=html_content,
            media_type="text/html",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="aegiscx_report_{recording_id[:8]}.html"'
                ),
                "X-AegisCX-Report-Format": "html",
                REPORT_WARNING_HEADER: (
                    "Native PDF runtime unavailable; returned HTML report fallback."
                ),
            },
        )


def _generate_report_html(report: dict) -> str:
    """Generate styled HTML report from analysis data."""
    rec = report.get("recording", {})
    tr = report.get("transcript", {})
    intel = report.get("intelligence", {})

    full_json = intel.get("full_analysis", {})
    llm_res = full_json.get("llm_result", {}) if isinstance(full_json, dict) else {}
    metrics = (
        llm_res.get("global_metrics_7_scale", {})
        if isinstance(llm_res, dict)
        else {}
    )
    segments = (
        llm_res.get("segment_by_segment_analysis", [])
        if isinstance(llm_res, dict)
        else []
    )

    generated = escape(str(report.get("generated_at", ""))[:10])
    sentiment = intel.get("overall_sentiment", "neutral")
    sentiment_color = {
        "positive": "#10b981",
        "negative": "#ef4444",
        "neutral": "#6b7280",
        "mixed": "#f59e0b",
        "extracted": "#8b5cf6",
    }.get(sentiment, "#6b7280")

    scale_html = ""
    for metric_name, score in metrics.items():
        clean_name = metric_name.replace("_", " ").title()
        width = min(max((float(score) / 7.0) * 100, 0), 100)
        scale_html += f"""
        <div style="margin-bottom: 12px; font-size: 13px;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
            <span style="font-weight: 600; color: #374151;">{escape(clean_name)}</span>
            <span style="color: #6b7280;">{score}/7</span>
          </div>
          <div style="background: #e5e7eb; border-radius: 4px; height: 8px; width: 100%; overflow: hidden;">
            <div style="background: #4f46e5; height: 100%; width: {width}%;"></div>
          </div>
        </div>
        """

    transcript_html = ""
    for seg in tr.get("segments", []):
        speaker = escape(seg.get("speaker_label") or "Speaker")
        start_time = float(seg.get("start_time", 0) or 0)
        end_time = float(seg.get("end_time", 0) or 0)
        text = escape(seg.get("text") or "")
        transcript_html += f"""
        <div style="padding: 12px 0; border-bottom: 1px solid #e5e7eb;">
          <div style="font-size: 12px; color: #64748b; margin-bottom: 6px;">
            <strong style="color: #0f172a;">{speaker}</strong>
            <span>({start_time:.1f}s - {end_time:.1f}s)</span>
          </div>
          <div style="font-size: 14px; color: #334155; line-height: 1.6;">{text}</div>
        </div>
        """

    if not transcript_html and tr.get("full_text"):
        transcript_html = f"""
        <div style="font-size: 14px; color: #334155; line-height: 1.7; white-space: pre-wrap;">
          {escape(tr.get("full_text", ""))}
        </div>
        """

    timeline_html = ""
    for seg in segments:
        spk = escape(seg.get("speaker", "Unknown"))
        ts = escape(str(seg.get("timestamp", "0:00")))
        reason = escape(seg.get("reasoning", ""))
        params = seg.get("twenty_parameters", {})

        flags = []
        if params.get("churn_risk_score", 0) > 7:
            flags.append(
                '<span style="color:red;font-size:10px;border:1px solid red;padding:1px 4px;border-radius:4px">HIGH CHURN RISK</span>'
            )
        if params.get("upsell_opportunity", False):
            flags.append(
                '<span style="color:green;font-size:10px;border:1px solid green;padding:1px 4px;border-radius:4px">UPSELL</span>'
            )
        if params.get("frustration_level", 0) > 7:
            flags.append(
                '<span style="color:orange;font-size:10px;border:1px solid orange;padding:1px 4px;border-radius:4px">FRUSTRATED</span>'
            )

        timeline_html += f"""
        <div style="border-left: 2px solid #cbd5e1; padding-left: 16px; margin-bottom: 24px; position: relative;">
            <div style="position: absolute; left: -5px; top: 0; width: 8px; height: 8px; border-radius: 50%; background: #4f46e5;"></div>
            <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">{ts} | <strong style="color: #0f172a;">{spk}</strong> {"&nbsp;".join(flags)}</div>
            <p style="margin: 0 0 8px 0; font-size: 14px; color: #334155;">{reason}</p>
            <div style="display:flex; flex-wrap: wrap; gap: 6px;">
               <span style="background:#f1f5f9; padding: 2px 6px; border-radius:4px; font-size:10px; color:#475569">Intent: {escape(str(params.get("intent", "N/A")))}</span>
               <span style="background:#f1f5f9; padding: 2px 6px; border-radius:4px; font-size:10px; color:#475569">Emotion: {escape(str(params.get("emotion", "N/A")))}</span>
               <span style="background:#f1f5f9; padding: 2px 6px; border-radius:4px; font-size:10px; color:#475569">Loyalty: {escape(str(params.get("brand_loyalty_signal", "N/A")))}</span>
               <span style="background:#f1f5f9; padding: 2px 6px; border-radius:4px; font-size:10px; color:#475569">Actionability: {escape(str(params.get("actionability", "N/A")))}</span>
            </div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CFIS Intelligence Report</title>
<style>
  body {{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:40px;color:#111827;}}
  .header {{background:linear-gradient(135deg,#0f172a,#4338ca);color:white;padding:32px;border-radius:12px;margin-bottom:32px;}}
  .header h1 {{margin:0;font-size:28px;letter-spacing:-0.5px;}}
  .header p {{margin:8px 0 0;opacity:0.8;font-size:14px;}}
  .badge {{display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600;color:white;background:{sentiment_color};}}
  .section {{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:24px;margin-bottom:20px;}}
  .section h2 {{margin:0 0 16px;font-size:16px;color:#374151;display:flex;align-items:center;gap:8px;}}
  .summary {{background:#f8fafc;border-left:4px solid #3b82f6;border-radius:4px 8px 8px 4px;padding:16px;font-size:14px;line-height:1.7;color:#1e293b;}}
  .grid {{display:grid;grid-template-columns:1fr 1fr;gap:24px;}}
  footer {{text-align:center;margin-top:48px;font-size:12px;color:#9ca3af;}}
</style>
</head>
<body>
<div class="header">
  <h1>CFIS Intelligence Report</h1>
  <p>Recording: {escape(rec.get("filename", "Unknown"))} | Generated: {generated} | {rec.get("duration_seconds", 0):.0f}s duration</p>
  <div style="margin-top:12px;">
    <span class="badge">CFIS MULTI-AGENT VERIFIED</span>
    &nbsp;
    <span style="background:rgba(255,255,255,0.15);padding:4px 12px;border-radius:20px;font-size:12px;">
    Model: {escape(str(llm_res.get("model_used", "Local-ML")).upper())}
    </span>
  </div>
</div>

<div class="section">
  <h2>Executive Summary</h2>
  <div class="summary">{escape(intel.get("executive_summary", "No summary available."))}</div>
</div>

<div class="section">
  <h2>Verbatim Transcript</h2>
  {transcript_html if transcript_html else "<p style='font-size:13px;color:#64748b'>Transcript not available.</p>"}
</div>

<div class="grid">
  <div class="section">
    <h2>Foundation Metrics (7-Point Scale)</h2>
    {scale_html if scale_html else "<p style='font-size:13px;color:#64748b'>No scale metrics computed.</p>"}
  </div>
  <div class="section">
    <h2>Session Processing</h2>
    <p style="font-size:13px;color:#475569;margin-bottom:8px"><strong>Speakers:</strong> {tr.get("num_speakers", 1)}</p>
    <p style="font-size:13px;color:#475569;margin-bottom:8px"><strong>Word Count:</strong> {tr.get("word_count", 0):,}</p>
    <p style="font-size:13px;color:#475569;margin-bottom:8px"><strong>Deep Parameters Extracted:</strong> 20 / Segment</p>
    <p style="font-size:13px;color:#475569;margin-bottom:8px"><strong>Requires Human Review:</strong> {intel.get("requires_human_review", False)}</p>
  </div>
</div>

<div class="section">
  <h2>Segment-by-Segment Deep Behavioral Timeline</h2>
  {timeline_html if timeline_html else "<p style='font-size:13px;color:#64748b'>No segment reasoning available.</p>"}
</div>

<footer>
  Customer Feedback Intelligence System (CFIS) | Report ID: {escape(str(report.get("report_id", "")))} | {generated}
</footer>
</body></html>"""


admin = APIRouter()


@admin.get("/jobs")
async def list_all_jobs(
    page: int = 1,
    per_page: int = 50,
    status_filter: Optional[str] = None,
    current_user: dict = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Admin: list all processing jobs across all companies."""
    from sqlalchemy import func

    query = select(Recording)
    if status_filter:
        query = query.where(Recording.status == status_filter.upper())

    count_q = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_q.scalar_one()

    result = await db.execute(
        query.order_by(desc(Recording.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    recordings = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [
            {
                "id": r.id,
                "filename": r.original_filename,
                "status": r.status,
                "company_id": r.company_id,
                "created_at": r.created_at.isoformat(),
                "error": r.error_message,
                "duration": r.duration_seconds,
            }
            for r in recordings
        ],
    }


@admin.post("/corrections", status_code=status.HTTP_201_CREATED)
async def submit_correction(
    body: CorrectionRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a human correction for AI predictions.
    Corrections are stored for weekly model fine-tuning.
    """
    result = await db.execute(select(Insight).where(Insight.id == body.insight_id))
    insight = result.scalar_one_or_none()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")

    correction = HumanCorrection(
        insight_id=body.insight_id,
        reviewer_id=current_user["user_id"],
        field_name=body.field_name,
        original_value=body.original_value,
        corrected_value=body.corrected_value,
        reason=body.reason,
    )
    db.add(correction)

    insight.requires_human_review = False
    await db.commit()

    return {"status": "correction_saved", "correction_id": correction.id}


@admin.get("/users")
async def list_users(
    current_user: dict = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Admin: list all users in the company."""
    company_id = current_user.get("company_id", current_user["user_id"])
    result = await db.execute(select(User).where(User.company_id == company_id))
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "last_login": u.last_login.isoformat() if u.last_login else None,
        }
        for u in users
    ]
