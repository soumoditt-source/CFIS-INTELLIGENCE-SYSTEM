"""
AegisCX SQLAlchemy Models
===========================
Agnostic database schema for all AegisCX entities.
Supports both PostgreSQL (JSONB/UUID) and SQLite (JSON/String).
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

# ─── Agnostic Types ────────────────────────────────────────────────────────────

def _uuid() -> str:
    """Generate a new UUID4 as string."""
    return str(uuid.uuid4())

def _now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)

# We use mapped_column(String(36)) for IDs to ensure SQLite compatibility
# while allowing PostgreSQL to treat them as UUID strings.

# ─── Companies ──────────────────────────────────────────────────────────────────
class Company(Base):
    """
    Multi-tenant company accounts.
    """
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    subscription_tier: Mapped[str] = mapped_column(
        String(50), default="free"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    users: Mapped[list["User"]] = relationship(back_populates="company")
    recordings: Mapped[list["Recording"]] = relationship(back_populates="company")
    customer_profiles: Mapped[list["CustomerProfile"]] = relationship(
        back_populates="company"
    )


# ─── Users ──────────────────────────────────────────────────────────────────────
class User(Base):
    """
    Platform users with role-based access control.
    """
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50), default="analyst"
    )
    company_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("companies.id"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    company: Mapped[Optional[Company]] = relationship(back_populates="users")
    recordings: Mapped[list["Recording"]] = relationship(back_populates="user")
    corrections: Mapped[list["HumanCorrection"]] = relationship(back_populates="reviewer")


# ─── Recordings ─────────────────────────────────────────────────────────────────
class Recording(Base):
    """
    Tracks every uploaded audio/video file.
    """
    __tablename__ = "recordings"

    STATUS_PENDING = "PENDING"
    STATUS_AUDIO_READY = "AUDIO_READY"
    STATUS_TRANSCRIBED = "TRANSCRIBED"
    STATUS_ANALYZED = "ANALYZED"
    STATUS_FAILED = "FAILED"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True, nullable=False
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id"), index=True, nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    wav_path: Mapped[Optional[str]] = mapped_column(String(1000))
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)
    format: Mapped[Optional[str]] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="recordings")
    company: Mapped[Company] = relationship(back_populates="recordings")
    transcript: Mapped[Optional["Transcript"]] = relationship(
        back_populates="recording", uselist=False
    )
    insight: Mapped[Optional["Insight"]] = relationship(
        back_populates="recording", uselist=False
    )


# ─── Transcripts ────────────────────────────────────────────────────────────────
class Transcript(Base):
    """
    Stores the full transcribed text with metadata.
    """
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    recording_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recordings.id"), unique=True, nullable=False
    )
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[Optional[int]] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(20), default="en")
    num_speakers: Mapped[Optional[int]] = mapped_column(Integer)
    stt_model: Mapped[str] = mapped_column(String(100), default="whisperx-medium")
    stt_confidence: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    recording: Mapped[Recording] = relationship(back_populates="transcript")
    segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="transcript", order_by="TranscriptSegment.segment_index"
    )


# ─── Transcript Segments ─────────────────────────────────────────────────────────
class TranscriptSegment(Base):
    """
    Per-speaker-turn transcript segments.
    """
    __tablename__ = "transcript_segments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    transcript_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transcripts.id"), index=True, nullable=False
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_label: Mapped[Optional[str]] = mapped_column(String(50))
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[Optional[int]] = mapped_column(Integer)
    words: Mapped[Optional[dict]] = mapped_column(JSON)

    transcript: Mapped[Transcript] = relationship(back_populates="segments")
    segment_insight: Mapped[Optional["SegmentInsight"]] = relationship(
        back_populates="segment", uselist=False
    )


# ─── Insights ────────────────────────────────────────────────────────────────────
class Insight(Base):
    """
    Full AI analysis results.
    """
    __tablename__ = "insights"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    recording_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recordings.id"), unique=True, nullable=False
    )

    overall_sentiment: Mapped[Optional[str]] = mapped_column(String(20))
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float)
    dominant_emotion: Mapped[Optional[str]] = mapped_column(String(50))
    customer_intent: Mapped[Optional[str]] = mapped_column(String(100))
    intent_confidence: Mapped[Optional[float]] = mapped_column(Float)

    emotion_arc: Mapped[Optional[dict]] = mapped_column(JSON)
    product_mentions: Mapped[Optional[dict]] = mapped_column(JSON)
    behavioral_signals: Mapped[Optional[dict]] = mapped_column(JSON)
    full_analysis: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    executive_summary: Mapped[Optional[str]] = mapped_column(Text)

    confidence_score: Mapped[Optional[float]] = mapped_column(Float)
    analysis_tier: Mapped[str] = mapped_column(
        String(20), default="ml_only"
    )
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[Optional[str]] = mapped_column(Text)

    llm_model: Mapped[Optional[str]] = mapped_column(String(100))
    ml_models_used: Mapped[Optional[dict]] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    recording: Mapped[Recording] = relationship(back_populates="insight")
    segment_insights: Mapped[list["SegmentInsight"]] = relationship(
        back_populates="insight"
    )
    corrections: Mapped[list["HumanCorrection"]] = relationship(
        back_populates="insight"
    )


# ─── Segment Insights ────────────────────────────────────────────────────────────
class SegmentInsight(Base):
    """
    Per-segment NLP analysis results.
    """
    __tablename__ = "segment_insights"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    insight_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("insights.id"), index=True, nullable=False
    )
    segment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transcript_segments.id"), unique=True, nullable=False
    )
    sentiment: Mapped[Optional[dict]] = mapped_column(JSON)
    emotions: Mapped[Optional[dict]] = mapped_column(JSON)
    intent: Mapped[Optional[dict]] = mapped_column(JSON)
    entities: Mapped[Optional[dict]] = mapped_column(JSON)
    behavioral_signals: Mapped[Optional[dict]] = mapped_column(JSON)
    
    twenty_parameters_analysis: Mapped[Optional[dict]] = mapped_column(JSON)
    
    embedding_id: Mapped[Optional[str]] = mapped_column(String(255))
    topic_id: Mapped[Optional[int]] = mapped_column(Integer)
    confidence: Mapped[Optional[float]] = mapped_column(Float)

    insight: Mapped[Insight] = relationship(back_populates="segment_insights")
    segment: Mapped[TranscriptSegment] = relationship(back_populates="segment_insight")


# ─── Human Corrections ───────────────────────────────────────────────────────────
class HumanCorrection(Base):
    """
    RLHF training data.
    """
    __tablename__ = "human_corrections"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    insight_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("insights.id"), index=True, nullable=False
    )
    reviewer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    original_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    corrected_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    reward_signal: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )

    insight: Mapped[Insight] = relationship(back_populates="corrections")
    reviewer: Mapped[User] = relationship(back_populates="corrections")


# ─── Customer Profiles ───────────────────────────────────────────────────────────
class CustomerProfile(Base):
    """
    Longitudinal customer memory.
    """
    __tablename__ = "customer_profiles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id"), index=True, nullable=False
    )
    customer_identifier: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    profile_data: Mapped[dict] = mapped_column(JSON, default=dict)
    sessions_count: Mapped[int] = mapped_column(Integer, default=0)
    cluster_id: Mapped[Optional[int]] = mapped_column(Integer)
    sentiment_history: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("company_id", "customer_identifier", name="uq_customer_per_company"),
    )

    company: Mapped[Company] = relationship(back_populates="customer_profiles")
