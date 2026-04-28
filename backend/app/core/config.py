"""
AegisCX Configuration Module
=============================
Centralized settings management using Pydantic BaseSettings.
All settings are loaded from environment variables / .env file.
Type-safe configuration with validation.

Build Log: backend/logs/build_log.jsonl
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application configuration.
    All values loaded from environment / .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Application ─────────────────────────────────────────
    app_name: str = Field(default="AegisCX", description="Application name")
    app_version: str = Field(default="1.0.0", description="Semantic version")
    environment: str = Field(default="development", description="deployment environment: development|staging|production")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    use_celery: bool = Field(default=False, description="Set True to use Celery/Redis; False uses inline BackgroundTasks")
    cors_origins: Any = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origins"
    )

    @field_validator("cors_origins", "allowed_extensions", mode="before")
    @classmethod
    def parse_list(cls, v):
        """Accept either a JSON array or a comma-separated string."""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                try:
                    import json
                    return json.loads(v)
                except Exception:
                    pass
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("debug", "use_celery", mode="before")
    @classmethod
    def parse_boolish(cls, v):
        """Accept common non-boolean env values used in Windows/dev shells."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "development", "dev"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "production", "prod"}:
                return False
        return v

    # ─── Security ────────────────────────────────────────────
    secret_key: str = Field(
        default="CHANGE-ME-min-32-chars-random-string",
        description="JWT signing secret key"
    )
    access_token_expire_minutes: int = Field(default=30)
    refresh_token_expire_days: int = Field(default=7)

    # ─── Database ────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://aegiscx:aegiscx_secret_password@localhost:5432/aegiscx_db"
    )
    database_url_sync: str = Field(
        default="postgresql://aegiscx:aegiscx_secret_password@localhost:5432/aegiscx_db"
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """
        Fix Render's postgres:// prefix and ensure asyncpg is used with SSL in production.
        """
        if not v:
            return v
            
        # 1. Standardize prefix
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql://", 1)
        
        # 2. Add asyncpg driver
        if "postgresql" in v and "+asyncpg" not in v:
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
            
        # 3. Add SSL requirement for production PostgreSQL if not already present
        # Render's internal URL might not need it, but External certainly does.
        # asyncpg uses 'ssl=require', whereas psycopg uses 'sslmode=require'
        if "postgresql" in v and "?" not in v:
            v += "?ssl=require"
            
        return v

    @field_validator("database_url_sync", mode="before")
    @classmethod
    def validate_database_url_sync(cls, v: str, info: Any) -> str:
        """
        Derive sync URL from database_url if not provided.
        """
        if v and "localhost" not in v:
            return v
            
        # Try to derive from database_url if possible
        db_url = info.data.get("database_url")
        if db_url and "postgresql" in db_url:
            # Strip +asyncpg and replace with nothing
            sync_url = db_url.replace("+asyncpg", "")
            # Ensure it has postgresql:// (sometimes it might have postgresql+asyncpg://)
            if sync_url.startswith("postgres://"):
                 sync_url = sync_url.replace("postgres://", "postgresql://", 1)
            return sync_url
            
        return v

    # ─── Redis ───────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/1")
    llm_cache_ttl_seconds: int = Field(default=3600)

    # ─── File Storage ────────────────────────────────────────
    data_dir: Path = Field(default=Path("./data"))
    raw_audio_dir: Path = Field(default=Path("./data/raw"))
    processed_audio_dir: Path = Field(default=Path("./data/processed"))
    chromadb_dir: Path = Field(default=Path("./data/chromadb"))
    log_dir: Path = Field(default=Path("./logs"))
    max_file_size_gb: float = Field(default=1.0, description="Maximum upload file size in GB")
    allowed_extensions: Any = Field(
        default=["mp3", "mp4", "wav", "m4a", "webm", "ogg", "flac", "mpeg"]
    )

    # ─── Whisper (STT) ───────────────────────────────────────
    whisper_model_size: str = Field(default="base", description="tiny|base|small|medium|large-v2|large-v3")
    whisper_device: str = Field(default="cpu", description="cuda|cpu")
    whisper_compute_type: str = Field(default="int8", description="float16|int8|float32")

    # ─── HuggingFace ─────────────────────────────────────────
    hf_token: Optional[str] = Field(default=None, description="HuggingFace access token for pyannote")
    hf_cache_dir: Path = Field(default=Path("./models/hf_cache"))

    # ─── LLM APIs ────────────────────────────────────────────
    google_api_key: Optional[str] = Field(default=None)
    mistral_api_key: Optional[str] = Field(default=None)
    openai_api_key: Optional[str] = Field(default=None)
    llm_confidence_threshold: float = Field(default=0.75, description="Below this → use LLM refinement")
    llm_primary_model: str = Field(default="models/gemini-2.5-flash")
    llm_fallback_model: str = Field(default="gpt-4o")

    # ─── ML Models ───────────────────────────────────────────
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    sentiment_model: str = Field(default="cardiffnlp/twitter-roberta-base-sentiment-latest")
    emotion_model: str = Field(default="j-hartmann/emotion-english-distilroberta-base")
    intent_model: str = Field(default="valhalla/distilbart-mnli-12-1")
    ner_model: str = Field(default="dslim/bert-base-NER")
    mc_dropout_passes: int = Field(default=10, description="Monte Carlo Dropout forward passes for uncertainty")
    bertopic_min_topic_size: int = Field(default=5)

    # ─── Processing ──────────────────────────────────────────
    audio_chunk_duration: int = Field(default=30, description="Audio chunk size in seconds")
    audio_chunk_overlap: int = Field(default=5, description="Chunk overlap in seconds")
    max_concurrent_jobs: int = Field(default=5)
    job_timeout_seconds: int = Field(default=3600)

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Ensure secret key is sufficiently long for security."""
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment name."""
        aliases = {
            "dev": "development",
            "debug": "development",
            "stage": "staging",
            "stg": "staging",
            "prod": "production",
            "release": "production",
        }
        v = aliases.get(v, v)
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    @property
    def max_file_size_bytes(self) -> int:
        """Compute max file size in bytes from GB setting."""
        return int(self.max_file_size_gb * 1024 ** 3)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def ensure_directories(self) -> None:
        """Create all required data directories if they don't exist."""
        dirs = [
            self.data_dir,
            self.raw_audio_dir,
            self.processed_audio_dir,
            self.chromadb_dir,
            self.log_dir,
            self.hf_cache_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.
    Uses LRU cache so the .env file is only read once.
    """
    settings = Settings()
    settings.ensure_directories()
    return settings
