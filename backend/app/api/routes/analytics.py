"""
AegisCX Analytics Routes
===========================
Company-wide aggregated intelligence endpoints.

  GET /analytics/overview      — KPI summary cards
  GET /analytics/sentiment     — Sentiment trend over time
  GET /analytics/emotions      — Emotion distribution
  GET /analytics/products      — Product-level feedback aggregates
  GET /analytics/intents       — Intent breakdown
  GET /analytics/customers     — Customer segment clusters
  GET /analytics/behavioral    — Behavioral signals aggregate
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, cast, Date, String, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Recording, Insight, SegmentInsight
from app.services.llm.orchestrator import LLMOrchestrator

router = APIRouter()


# ─── Response Schemas ────────────────────────────────────────────────────────────

class TextAnalysisRequest(BaseModel):
    text: str
    company_name: Optional[str] = None
    product_category: Optional[str] = None

class OverviewResponse(BaseModel):
    total_recordings: int
    analyzed_recordings: int
    pending_recordings: int
    failed_recordings: int
    avg_sentiment_score: float
    avg_confidence_score: float
    positive_sessions: int
    negative_sessions: int
    neutral_sessions: int
    reviews_needed: int
    total_duration_minutes: float


class SentimentTrendPoint(BaseModel):
    date: str
    positive: int
    negative: int
    neutral: int
    avg_score: float


class EmotionDistItem(BaseModel):
    emotion: str
    count: int
    percentage: float


class ProductFeedbackItem(BaseModel):
    product_name: str
    total_mentions: int
    positive_mentions: int
    negative_mentions: int
    neutral_mentions: int
    sentiment_ratio: float


class IntentBreakdown(BaseModel):
    intent: str
    count: int
    percentage: float
    avg_confidence: float


class CustomerSegment(BaseModel):
    cluster_id: int
    label: str
    count: int
    avg_sentiment: float
    dominant_intent: str


# ─── Endpoints ──────────────────────────────────────────────────────────────────
@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    days: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Dashboard KPI overview for the last N days.
    Returns aggregate counts and averages across all company recordings.
    """
    company_id = current_user.get("company_id", current_user["user_id"])
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Recording counts by status
    status_result = await db.execute(
        select(Recording.status, func.count(Recording.id).label("cnt"))
        .where(Recording.company_id == company_id)
        .where(Recording.created_at >= since)
        .group_by(Recording.status)
    )
    status_counts = {row.status: row.cnt for row in status_result}

    total = sum(status_counts.values())
    analyzed = status_counts.get("ANALYZED", 0)

    # Insight aggregates
    insight_result = await db.execute(
        select(
            func.avg(Insight.sentiment_score).label("avg_sentiment"),
            func.avg(Insight.confidence_score).label("avg_confidence"),
            func.count(Insight.id).filter(Insight.overall_sentiment == "positive").label("pos"),
            func.count(Insight.id).filter(Insight.overall_sentiment == "negative").label("neg"),
            func.count(Insight.id).filter(Insight.overall_sentiment == "neutral").label("neu"),
            func.count(Insight.id).filter(Insight.overall_sentiment == "mixed").label("mix"),
            func.count(Insight.id).filter(Insight.requires_human_review == True).label("review"),
        )
        .join(Recording, Recording.id == Insight.recording_id)
        .where(Recording.company_id == company_id)
        .where(Recording.created_at >= since)
    )
    agg = insight_result.one()

    # Total duration
    dur_result = await db.execute(
        select(func.sum(Recording.duration_seconds))
        .where(Recording.company_id == company_id)
        .where(Recording.created_at >= since)
    )
    total_duration = dur_result.scalar_one() or 0.0

    return OverviewResponse(
        total_recordings=total,
        analyzed_recordings=analyzed,
        pending_recordings=total - analyzed - status_counts.get("FAILED", 0),
        failed_recordings=status_counts.get("FAILED", 0),
        avg_sentiment_score=round(float(agg.avg_sentiment or 0.5), 3),
        avg_confidence_score=round(float(agg.avg_confidence or 0.5), 3),
        positive_sessions=agg.pos or 0,
        negative_sessions=agg.neg or 0,
        neutral_sessions=(agg.neu or 0) + (agg.mix or 0),
        reviews_needed=agg.review or 0,
        total_duration_minutes=round(total_duration / 60, 1),
    )


@router.get("/sentiment", response_model=list[SentimentTrendPoint])
async def get_sentiment_trend(
    days: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Daily sentiment trend over the last N days.
    Returns counts of positive/negative/neutral per day.
    """
    company_id = current_user.get("company_id", current_user["user_id"])
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Raw SQL to bypass SQLAlchemy's type processor which fails on SQLite date casting
    query = text("""
        SELECT 
            strftime('%Y-%m-%d', r.created_at) as day,
            COUNT(i.id) FILTER (WHERE i.overall_sentiment = 'positive') as pos,
            COUNT(i.id) FILTER (WHERE i.overall_sentiment = 'negative') as neg,
            COUNT(i.id) FILTER (WHERE i.overall_sentiment IN ('neutral', 'mixed')) as neu,
            AVG(i.sentiment_score) as avg_score
        FROM recordings r
        JOIN insights i ON r.id = i.recording_id
        WHERE r.company_id = :company_id
          AND r.created_at >= :since
        GROUP BY strftime('%Y-%m-%d', r.created_at)
        ORDER BY day ASC
    """)

    result = await db.execute(query, {"company_id": company_id, "since": since})
    
    points = []
    for row in result:
        points.append(SentimentTrendPoint(
            date=str(row[0]),
            positive=int(row[1] or 0),
            negative=int(row[2] or 0),
            neutral=int(row[3] or 0),
            avg_score=round(float(row[4] or 0.5), 3),
        ))
    
    return points


@router.get("/products", response_model=list[ProductFeedbackItem])
async def get_product_analytics(
    days: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Product-level feedback aggregates.
    Extracts product mentions from the JSONB product_mentions field.
    Returns sorted by total mentions (most mentioned first).
    """
    company_id = current_user.get("company_id", current_user["user_id"])
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Fetch all insights with product mentions in range
    result = await db.execute(
        select(Insight.product_mentions)
        .join(Recording, Recording.id == Insight.recording_id)
        .where(Recording.company_id == company_id)
        .where(Recording.created_at >= since)
        .where(Insight.product_mentions.isnot(None))
    )

    # Aggregate in Python (JSONB array processing)
    product_map: dict[str, dict] = {}

    for row in result:
        mentions = row.product_mentions or []
        for mention in mentions:
            name = str(mention.get("product_name", "Unknown")).strip()
            if not name:
                continue
            if name not in product_map:
                product_map[name] = {"total": 0, "pos": 0, "neg": 0, "neu": 0}

            sentiment = mention.get("sentiment", "neutral")
            product_map[name]["total"] += 1
            if sentiment == "positive":
                product_map[name]["pos"] += 1
            elif sentiment == "negative":
                product_map[name]["neg"] += 1
            else:
                product_map[name]["neu"] += 1

    items = []
    for name, counts in sorted(
        product_map.items(), key=lambda x: x[1]["total"], reverse=True
    )[:25]:  # Top 25 products
        total = counts["total"]
        items.append(ProductFeedbackItem(
            product_name=name,
            total_mentions=total,
            positive_mentions=counts["pos"],
            negative_mentions=counts["neg"],
            neutral_mentions=counts["neu"],
            sentiment_ratio=round(counts["pos"] / total, 3) if total > 0 else 0.5,
        ))

    return items


@router.get("/intents", response_model=list[IntentBreakdown])
async def get_intent_breakdown(
    days: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Intent distribution across all analyzed sessions."""
    company_id = current_user.get("company_id", current_user["user_id"])
    since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(
            Insight.customer_intent,
            func.count(Insight.id).label("cnt"),
            func.avg(Insight.intent_confidence).label("avg_conf"),
        )
        .join(Recording, Recording.id == Insight.recording_id)
        .where(Recording.company_id == company_id)
        .where(Recording.created_at >= since)
        .where(Insight.customer_intent.isnot(None))
        .group_by(Insight.customer_intent)
        .order_by(func.count(Insight.id).desc())
    )

    rows = result.all()
    total = sum(r.cnt for r in rows) or 1

    return [
        IntentBreakdown(
            intent=row.customer_intent,
            count=row.cnt,
            percentage=round(row.cnt / total * 100, 1),
            avg_confidence=round(float(row.avg_conf or 0.0), 3),
        )
        for row in rows
    ]


@router.get("/behavioral", response_model=dict)
async def get_behavioral_aggregate(
    days: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Aggregated behavioral signal distribution.
    Returns avg hesitation, frustration, satisfaction levels.
    """
    company_id = current_user.get("company_id", current_user["user_id"])
    since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(Insight.behavioral_signals)
        .join(Recording, Recording.id == Insight.recording_id)
        .where(Recording.company_id == company_id)
        .where(Recording.created_at >= since)
        .where(Insight.behavioral_signals.isnot(None))
    )

    hes_total, frus_total, sat_total, count = 0.0, 0.0, 0.0, 0

    for row in result:
        signals = row.behavioral_signals or {}
        llm_scale = signals.get("llm_7_scale", {}) if isinstance(signals, dict) else {}
        hes_total += float(
            signals.get("hesitation_level_score", signals.get("hesitation_score", 0)) or 0
        )
        frus_total += float(
            signals.get("frustration_level_score", signals.get("frustration_score", 0)) or 0
        )
        sat_total += float(
            signals.get(
                "satisfaction_level_score",
                signals.get(
                    "satisfaction_score",
                    (float(llm_scale.get("customer_satisfaction", 0)) / 7.0 if llm_scale else 0),
                ),
            ) or 0
        )
        count += 1

    if count == 0:
        return {"avg_hesitation": 0.0, "avg_frustration": 0.0,
                "avg_satisfaction": 0.5, "sample_size": 0}

    return {
        "avg_hesitation": round(hes_total / count, 3),
        "avg_frustration": round(frus_total / count, 3),
        "avg_satisfaction": round(sat_total / count, 3),
        "sample_size": count,
    }


@router.post("/analyze_text")
async def analyze_text(
    request: TextAnalysisRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Directly analyze a block of text using the LLM orchestrator.
    The orchestrator is synchronous, so we offload it to a thread.
    """
    if not request.text or not request.text.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Text cannot be empty")

    session_id = str(uuid.uuid4())
    orchestrator = LLMOrchestrator()

    result = await asyncio.to_thread(
        orchestrator.analyze_transcript,
        session_id,
        request.text,
        request.company_name or "Direct Analysis",
        request.product_category or "General",
        "direct_text",
        1,
        0.0,
    )

    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="LLM analysis failed — check API keys in .env")

    # Convert dataclass to dict for JSON serialisation
    return {
        "session_id": result.session_id,
        "executive_summary": result.executive_summary,
        "global_metrics_7_scale": result.global_metrics_7_scale,
        "segment_by_segment_analysis": result.segment_by_segment_analysis,
        "model_used": result.model_used,
        "latency_ms": result.latency_ms,
    }
