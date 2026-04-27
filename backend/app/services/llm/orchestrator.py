"""
AegisCX LLM Orchestrator
===========================
Manages all LLM API calls with:
  - P.T.C.F. (Persona·Task·Context·Format) structured prompts
  - Primary: Google Gemini Pro
  - Fallback: OpenAI GPT-4o
  - Redis caching (avoid duplicate API calls, cut costs)
  - Retry with exponential backoff (tenacity)
  - Cost tier tracking: ml_only | ml_llm | full_llm
  - Structured JSON output parsing with validation

Called only when ML pipeline confidence < LLM_CONFIDENCE_THRESHOLD.
"""

import json
import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from app.core.config import get_settings

settings = get_settings()
log = structlog.get_logger("aegiscx.llm")

# ─── Master Analysis Prompt (PTCF format) ────────────────────────────────────────
_ANALYSIS_PROMPT_TEMPLATE = """
[PERSONA]
You are AegisCX Intelligence Engine — a world-class behavioral analyst, customer intelligence expert, and product feedback specialist. You analyze customer feedback recordings for consumer goods companies to extract actionable business intelligence. You are methodical, objective, evidence-based, and you never speculate beyond what the transcript directly supports.

[TASK]
Analyze the following customer feedback transcript and extract a comprehensive, structured intelligence report. Every claim MUST be directly grounded in the transcript text. If evidence is insufficient for any field, set it to null. Prefer dense, context-rich phrasing over verbose repetition.

[CONTEXT]
Company: {company_name}
Product Category: {product_category}
Recording Type: {recording_type}
Date: {date}
Duration: {duration_seconds} seconds
Number of Speakers: {num_speakers}

Transcript (speaker-diarized, with timestamps):
{transcript_text}

[FORMAT]
Return ONLY valid JSON. No markdown, no explanation. Exact schema:

{{
  "session_id": "{session_id}",
  "system_scratchpad": "1-2 sentence evidence note summarizing the strongest behavioral and product cues. Do not expose chain-of-thought.",
  "executive_summary": "Two compact paragraphs, 5-8 sentences total. Explain what happened, what the customer felt, what product or service drivers mattered, and what the company should care about next.",
  "global_metrics_7_scale": {{
    "customer_satisfaction": 0,
    "agent_empathy": 0,
    "issue_resolution_efficiency": 0,
    "product_sentiment": 0,
    "brand_trust": 0,
    "communication_clarity": 0,
    "overall_experience": 0
  }},
  "segment_by_segment_analysis": [
    {{
      "segment_index": 0,
      "speaker": "Customer/Agent",
      "timestamp": "0:00-0:10",
      "twenty_parameters": {{
        "sentiment": "positive|negative|neutral",
        "emotion": "joy|anger|sadness|fear|disgust|surprise|neutral",
        "intent": "purchase|complaint|suggestion|inquiry|churn|neutral",
        "hesitation_level": 0.0,
        "frustration_level": 0.0,
        "satisfaction_level": 0.0,
        "sarcasm_probability": 0.0,
        "urgency_level": 0.0,
        "empathy_required": false,
        "resolution_status": "open|progress|resolved|none",
        "brand_loyalty_signal": "low|medium|high",
        "purchase_intent": true,
        "churn_risk_score": 0.0,
        "upsell_opportunity": true,
        "competitor_comparison": "none|brand_x",
        "actionability": "low|medium|high",
        "feature_request_detected": false,
        "bug_report_detected": false,
        "demographic_signal": "none|student|parent|retiree|etc",
        "conflict_level": 0.0
      }},
      "reasoning": "One compact sentence explaining the evidence for this segment's scores."
    }}
  ]
}}
"""


@dataclass
class LLMAnalysisResult:
    """Structured result from CFIS LLM analysis."""
    session_id: str
    system_scratchpad: str
    executive_summary: str
    global_metrics_7_scale: dict
    segment_by_segment_analysis: list
    model_used: str
    latency_ms: float
    from_cache: bool


class LLMOrchestrator:
    """
    Manages all LLM calls for AegisCX with cost optimization and reliability.

    Routing strategy:
      1. Check Redis cache → return cached result (free, instant)
      2. Try Gemini Pro (primary — cheapest cost/quality ratio)
      3. Fall back to GPT-4o if Gemini fails

    Usage:
        orchestrator = LLMOrchestrator(redis_client)
        result = orchestrator.analyze_transcript(...)
    """

    def __init__(self, redis_client=None):
        """
        Args:
            redis_client: Optional Redis client for response caching.
        """
        self._redis = redis_client
        self._gemini_client = None
        self._gemini_model_name = settings.llm_primary_model
        self._openai_client = None
        self._init_clients()

    def _resolve_gemini_model_name(self, available_models: set[str]) -> str:
        """Resolve stale or shorthand Gemini model names to a live model."""
        configured = (settings.llm_primary_model or "").strip()
        candidates = []
        if configured:
            candidates.append(configured)
            if configured.startswith("models/"):
                candidates.append(configured.split("/", 1)[1])
            else:
                candidates.append(f"models/{configured}")

        preferred = [
            "models/gemini-2.5-flash",
            "models/gemini-2.5-pro",
            "models/gemini-2.0-flash",
            "models/gemini-flash-latest",
            "models/gemini-pro-latest",
        ]
        candidates.extend(model for model in preferred if model not in candidates)

        if available_models:
            for candidate in candidates:
                if candidate in available_models:
                    return candidate

        return configured if configured.startswith("models/") else f"models/{configured}"

    def _init_clients(self) -> None:
        """Initialize LLM API clients if keys are configured."""
        if settings.google_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.google_api_key)
                available_models = {
                    model.name
                    for model in genai.list_models()
                    if "generateContent" in getattr(model, "supported_generation_methods", [])
                }
                self._gemini_model_name = self._resolve_gemini_model_name(available_models)
                self._gemini_client = genai.GenerativeModel(self._gemini_model_name)
                log.info(
                    "gemini_client_initialized",
                    model=self._gemini_model_name,
                    configured_model=settings.llm_primary_model,
                )
            except Exception as e:
                log.warning("gemini_init_failed", error=str(e))

        if settings.mistral_api_key:
            try:
                from app.services.llm.mistral_agent import MistralAgent
                self._mistral_client = MistralAgent(api_key=settings.mistral_api_key)
                if self._mistral_client.is_ready:
                    log.info("mistral_client_initialized", model="mistral-small-latest")
            except Exception as e:
                log.warning("mistral_init_failed", error=str(e))

        if settings.openai_api_key:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=settings.openai_api_key)
                log.info("openai_client_initialized", model=settings.llm_fallback_model)
            except Exception as e:
                log.warning("openai_init_failed", error=str(e))

    def analyze_transcript(
        self,
        session_id: str,
        transcript_text: str,
        company_name: str = "Unknown Company",
        product_category: str = "Consumer Goods",
        recording_type: str = "customer_feedback",
        num_speakers: int = 2,
        duration_seconds: float = 0.0,
    ) -> Optional[LLMAnalysisResult]:
        """
        Run full LLM analysis on a transcript using PTCF prompt.

        Args:
            session_id: Recording UUID.
            transcript_text: Full diarized transcript text.
            company_name: Client company name for context.
            product_category: Product category (e.g., "FMCG - Health & Wellness").
            recording_type: Type of recording (survey/interview/call).
            num_speakers: Number of detected speakers.
            duration_seconds: Recording duration.

        Returns:
            LLMAnalysisResult or None if both providers fail and no cache.
        """
        # Step 1: Check cache
        cache_key = self._get_cache_key(session_id, transcript_text)
        cached = self._get_cached_result(cache_key)
        if cached:
            log.info("llm_cache_hit", session_id=session_id)
            return cached

        # Step 2: Build prompt
        prompt = _ANALYSIS_PROMPT_TEMPLATE.format(
            company_name=company_name,
            product_category=product_category,
            recording_type=recording_type,
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            duration_seconds=int(duration_seconds),
            num_speakers=num_speakers,
            transcript_text=self._truncate_transcript(transcript_text),
            session_id=session_id,
        )

        # Step 3: Try Gemini → fallback to Mistral → fallback to OpenAI
        start = time.perf_counter()
        raw_json: Optional[str] = None
        model_used = "none"

        if self._gemini_client:
            try:
                raw_json = self._call_gemini(prompt)
                model_used = self._gemini_model_name
            except Exception as e:
                log.warning("gemini_call_failed", error=str(e),
                            session_id=session_id, message="Trying Mistral fallback")

        if raw_json is None and getattr(self, '_mistral_client', None):
            try:
                raw_json = self._mistral_client.call(prompt)
                model_used = "mistral"
            except Exception as e:
                log.warning("mistral_call_failed", error=str(e),
                            session_id=session_id, message="Trying OpenAI fallback")

        if raw_json is None and self._openai_client:
            try:
                raw_json = self._call_openai(prompt)
                model_used = settings.llm_fallback_model
            except Exception as e:
                log.error("openai_call_failed", error=str(e), session_id=session_id)

        latency_ms = round((time.perf_counter() - start) * 1000, 1)

        if raw_json is None:
            log.error("all_llm_providers_failed", session_id=session_id)
            return None

        # Step 4: Parse and validate JSON
        parsed = self._parse_llm_response(raw_json, session_id)
        if parsed is None:
            return None

        result = LLMAnalysisResult(
            **parsed,
            model_used=model_used,
            latency_ms=latency_ms,
            from_cache=False,
        )

        # Step 5: Cache result
        self._cache_result(cache_key, result)

        log.info("llm_analysis_complete", session_id=session_id,
                 model=model_used, latency_ms=latency_ms)

        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    def _call_gemini(self, prompt: str) -> str:
        """
        Call Google Gemini Pro with retry logic.

        Args:
            prompt: Formatted PTCF prompt string.

        Returns:
            Raw JSON string response.

        Raises:
            Exception: If Gemini API call fails after retries.
        """
        response = self._gemini_client.generate_content(
            prompt,
            generation_config={
                "temperature": 0.1,        # Near-deterministic for structured output
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 4096,
                "response_mime_type": "application/json",
            }
        )
        return response.text

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    def _call_openai(self, prompt: str) -> str:
        """
        Call OpenAI GPT-4o with retry logic.

        Args:
            prompt: Formatted PTCF prompt string.

        Returns:
            Raw JSON string response.

        Raises:
            Exception: If OpenAI API call fails after retries.
        """
        response = self._openai_client.chat.completions.create(
            model=settings.llm_fallback_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are AegisCX, an expert customer intelligence analyst. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=4096,
        )
        return response.choices[0].message.content

    def _parse_llm_response(
        self, raw_json: str, session_id: str
    ) -> Optional[dict]:
        """
        Parse and validate LLM JSON response.

        Args:
            raw_json: Raw string from LLM.
            session_id: For logging.

        Returns:
            Parsed dict or None if invalid.
        """
        try:
            text = raw_json.strip()
            # Remove ```json and ``` wrapping if present anywhere
            if "```" in text:
                # Find the first ``` and split
                parts = text.split("```")
                # Usually there's ```json at the start of the payload, so it's parts[1]
                if len(parts) >= 3:
                    text = parts[1]
                    if text.strip().lower().startswith("json"):
                        text = text.strip()[4:].strip()
                else:
                    text = text.replace("```json", "").replace("```", "").strip()
            
            # Additional safety: Find first { and last } to extract JSON blob
            start_idx = text.find("{")
            end_idx = text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                text = text[start_idx:end_idx+1]


            data = json.loads(text)

            # Validate required fields
            required = [
                "executive_summary", "global_metrics_7_scale", "segment_by_segment_analysis"
            ]
            missing = [f for f in required if f not in data]
            if missing:
                log.warning("llm_response_missing_fields",
                            session_id=session_id, fields=missing)

            # Ensure session_id matches
            data["session_id"] = session_id

            # Defaults for optional fields
            data.setdefault("system_scratchpad", "")
            data.setdefault("executive_summary", "")
            data.setdefault("global_metrics_7_scale", {})
            data.setdefault("segment_by_segment_analysis", [])

            return data

        except json.JSONDecodeError as e:
            log.error("llm_json_parse_failed", session_id=session_id, error=str(e))
            return None

    def _truncate_transcript(self, text: str, max_chars: int = 12000) -> str:
        """
        Truncate long transcripts to fit LLM context window.
        Keeps the first 60% and last 40% for narrative balance.

        Args:
            text: Full transcript text.
            max_chars: Maximum character count.

        Returns:
            Truncated transcript with ellipsis if shortened.
        """
        if len(text) <= max_chars:
            return text

        first_part = text[:int(max_chars * 0.6)]
        last_part = text[-(int(max_chars * 0.4)):]
        return f"{first_part}\n\n[... transcript truncated for brevity ...]\n\n{last_part}"

    def _get_cache_key(self, session_id: str, transcript: str) -> str:
        """Generate a deterministic cache key from session + transcript hash."""
        content_hash = hashlib.md5(
            (session_id + transcript[:500]).encode("utf-8")
        ).hexdigest()
        return f"aegiscx:llm:{session_id}:{content_hash}"

    def _get_cached_result(self, cache_key: str) -> Optional[LLMAnalysisResult]:
        """Retrieve cached LLM result from Redis if available."""
        if not self._redis:
            return None
        try:
            raw = self._redis.get(cache_key)
            if raw:
                data = json.loads(raw)
                data["from_cache"] = True
                return LLMAnalysisResult(**data)
        except Exception:
            pass
        return None

    def _cache_result(self, cache_key: str, result: LLMAnalysisResult) -> None:
        """Cache LLM result in Redis with TTL."""
        if not self._redis:
            return
        try:
            self._redis.setex(
                cache_key,
                settings.llm_cache_ttl_seconds,
                json.dumps(result.__dict__),
            )
        except Exception:
            pass  # Caching failure is non-critical
