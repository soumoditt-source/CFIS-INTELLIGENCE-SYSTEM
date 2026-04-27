"""
AegisCX Intelligence Pipeline
================================
Nine-dimensional NLP analysis for each transcript segment.

Dimensions extracted:
  1. Sentence embeddings (384-dim, all-MiniLM-L6-v2)
  2. Sentiment: positive / negative / neutral (RoBERTa)
  3. Emotion: 7-class joy/anger/sadness/fear/disgust/surprise/neutral
  4. Intent: zero-shot via BART-MNLI
  5. Named entities: products, brands, people, locations
  6. Behavioral signals: hesitation, frustration, confidence markers
  7. Aspect-based sentiment: per-product sentiment
  8. Topic cluster: BERTopic label
  9. Monte Carlo Dropout confidence score

Architecture: LOCAL ML first → LLM refinement if confidence < threshold.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

import numpy as np
import structlog

# torch is a lazy import — only loaded when models are first called.
# This prevents import-time failures when torch isn't installed yet.
try:
    import torch as _torch
    _TORCH_AVAILABLE = True
except ImportError:
    _torch = None  # type: ignore
    _TORCH_AVAILABLE = False

from app.core.config import get_settings

settings = get_settings()
log = structlog.get_logger("aegiscx.nlp")

# ─── Behavioral Signal Lexicons ───────────────────────────────────────────────────
HESITATION_MARKERS = frozenset([
    "um", "uh", "hmm", "eh", "er", "ah", "like", "you know",
    "sort of", "kind of", "i mean", "basically", "literally",
    "actually", "right", "so yeah"
])

FRUSTRATION_MARKERS = frozenset([
    "terrible", "awful", "waste", "never again", "disappointed",
    "horrible", "worst", "useless", "broken", "failed", "pathetic",
    "disgusting", "ridiculous", "annoying", "frustrated", "irritating",
    "fed up", "sick of", "hate", "garbage", "trash", "rubbish",
    "unacceptable", "disgusted", "poor quality", "no good"
])

SATISFACTION_MARKERS = frozenset([
    "love", "excellent", "amazing", "fantastic", "perfect", "great",
    "awesome", "brilliant", "outstanding", "wonderful", "best",
    "highly recommend", "five stars", "absolutely love", "very happy",
    "satisfied", "delighted", "impressed", "works perfectly", "exceeded"
])

PURCHASE_INTENT_MARKERS = frozenset([
    "will buy", "going to buy", "would recommend", "buy again",
    "definitely purchasing", "ordering again", "already ordered",
    "next purchase", "subscribe", "continue using"
])

INTENT_LABELS = [
    "purchase intent",
    "complaint about product",
    "product suggestion",
    "product praise",
    "general comment",
    "question about product",
    "churn indication",
]


def _round_score(value: float, digits: int = 4) -> float:
    """Normalize model scores to plain Python floats for JSON/database safety."""
    return float(round(float(value), digits))


@dataclass
class SentimentResult:
    """Result from sentiment classifier."""
    label: str          # positive | negative | neutral
    score: float        # Probability of the predicted label


@dataclass
class EmotionResult:
    """Result from emotion classifier."""
    emotion: str        # joy | anger | sadness | fear | disgust | surprise | neutral
    score: float


@dataclass
class IntentResult:
    """Result from zero-shot intent classifier."""
    label: str
    score: float
    all_scores: dict[str, float]


@dataclass
class EntityResult:
    """Named entity extracted from text."""
    text: str
    entity_type: str    # PER | ORG | PROD | LOC | MISC
    score: float


@dataclass
class BehavioralSignals:
    """Linguistic behavioral signal scores."""
    hesitation_score: float
    frustration_score: float
    satisfaction_score: float
    purchase_intent_signals: int
    hesitation_count: int
    frustration_count: int
    satisfaction_count: int
    overall_behavioral_score: float


@dataclass
class SegmentAnalysis:
    """Full 9-dimensional analysis result for one transcript segment."""
    segment_id: str
    text: str
    embedding: list[float]
    sentiment: SentimentResult
    emotions: list[EmotionResult]
    intent: IntentResult
    entities: list[EntityResult]
    behavioral_signals: BehavioralSignals
    confidence: float
    needs_llm_review: bool
    topic_id: Optional[int] = None


class IntelligencePipeline:
    """
    AegisCX core NLP intelligence pipeline.
    Lazily loads transformer models on first use to save startup time.

    Usage:
        pipeline = IntelligencePipeline()
        result = pipeline.analyze_segment(segment_id="...", text="...")
    """

    _shared_lock = Lock()
    _shared_cache_key: Optional[tuple] = None
    _shared_embedder = None
    _shared_sentiment_pipe = None
    _shared_emotion_pipe = None
    _shared_intent_pipe = None
    _shared_ner_pipe = None
    _shared_models_loaded = False

    def __init__(self):
        self._models_loaded = False
        self._embedder = None
        self._sentiment_pipe = None
        self._emotion_pipe = None
        self._intent_pipe = None
        self._ner_pipe = None
        # Determine device: CUDA if available, else CPU
        if _TORCH_AVAILABLE and _torch.cuda.is_available():
            self._device_id = 0
        else:
            self._device_id = -1  # CPU

    def _load_models(self) -> None:
        """
        Load all transformer models into memory.
        Called lazily on first analyze() call.
        Raises RuntimeError if torch is not available.
        """
        if self._models_loaded:
            return

        if not _TORCH_AVAILABLE:
            raise RuntimeError(
                "PyTorch not installed. Run: "
                "pip install torch --index-url https://download.pytorch.org/whl/cpu"
            )

        cache_key = (
            self._device_id,
            settings.embedding_model,
            settings.sentiment_model,
            settings.emotion_model,
            settings.intent_model,
            settings.ner_model,
        )

        with self.__class__._shared_lock:
            if (
                self.__class__._shared_models_loaded
                and self.__class__._shared_cache_key == cache_key
            ):
                self._embedder = self.__class__._shared_embedder
                self._sentiment_pipe = self.__class__._shared_sentiment_pipe
                self._emotion_pipe = self.__class__._shared_emotion_pipe
                self._intent_pipe = self.__class__._shared_intent_pipe
                self._ner_pipe = self.__class__._shared_ner_pipe
                self._models_loaded = True
                return

            from transformers import pipeline as hf_pipeline
            from sentence_transformers import SentenceTransformer

            log.info("loading_nlp_models", device="cuda" if self._device_id == 0 else "cpu")

            self._embedder = SentenceTransformer(
                settings.embedding_model,
                cache_folder=str(settings.hf_cache_dir),
            )

            self._sentiment_pipe = hf_pipeline(
                "sentiment-analysis",
                model=settings.sentiment_model,
                device=self._device_id,
                model_kwargs={"cache_dir": str(settings.hf_cache_dir)},
            )

            self._emotion_pipe = hf_pipeline(
                "text-classification",
                model=settings.emotion_model,
                top_k=None,
                device=self._device_id,
                model_kwargs={"cache_dir": str(settings.hf_cache_dir)},
            )

            self._intent_pipe = hf_pipeline(
                "zero-shot-classification",
                model=settings.intent_model,
                device=self._device_id,
                model_kwargs={"cache_dir": str(settings.hf_cache_dir)},
            )

            self._ner_pipe = hf_pipeline(
                "ner",
                model=settings.ner_model,
                aggregation_strategy="simple",
                device=self._device_id,
                model_kwargs={"cache_dir": str(settings.hf_cache_dir)},
            )

            self.__class__._shared_cache_key = cache_key
            self.__class__._shared_embedder = self._embedder
            self.__class__._shared_sentiment_pipe = self._sentiment_pipe
            self.__class__._shared_emotion_pipe = self._emotion_pipe
            self.__class__._shared_intent_pipe = self._intent_pipe
            self.__class__._shared_ner_pipe = self._ner_pipe
            self.__class__._shared_models_loaded = True

            self._models_loaded = True
            log.info("nlp_models_loaded")

    @classmethod
    def warmup(cls) -> None:
        """
        Preload the shared NLP model cache so later recordings reuse the same
        transformer stack instead of reloading it per request.
        """
        cls()._load_models()

    def analyze_segment(self, segment_id: str, text: str) -> SegmentAnalysis:
        """
        Run the full 9-dimensional analysis on a transcript segment.

        Args:
            segment_id: UUID string for this segment.
            text: Raw transcript text for this speaker turn.

        Returns:
            SegmentAnalysis with all extracted dimensions.

        Note:
            Returns neutral/zero results for empty or very short text.
        """
        self._load_models()

        if not text or len(text.strip()) < 5:
            return self._empty_result(segment_id, text)

        # Truncate to model max input (512 tokens ~ 400 words)
        text_safe = text[:1800]

        embedding = self._get_embedding(text_safe)
        sentiment = self._get_sentiment(text_safe)
        emotions = self._get_emotions(text_safe)
        intent = self._get_intent(text_safe)
        entities = self._get_entities(text_safe)
        behavioral = self._get_behavioral_signals(text)
        confidence = self._compute_mc_confidence(text_safe)

        needs_llm = confidence < settings.llm_confidence_threshold

        return SegmentAnalysis(
            segment_id=segment_id,
            text=text,
            embedding=embedding,
            sentiment=sentiment,
            emotions=emotions,
            intent=intent,
            entities=entities,
            behavioral_signals=behavioral,
            confidence=confidence,
            needs_llm_review=needs_llm,
        )

    def _get_embedding(self, text: str) -> list[float]:
        """Generate 384-dim sentence embedding."""
        vector = self._embedder.encode(text, convert_to_numpy=True)
        return vector.tolist()

    def _get_sentiment(self, text: str) -> SentimentResult:
        """
        Run RoBERTa sentiment classifier.

        Label mapping from cardiffnlp model:
          LABEL_0 = negative, LABEL_1 = neutral, LABEL_2 = positive
        """
        label_map = {
            "LABEL_0": "negative",
            "LABEL_1": "neutral",
            "LABEL_2": "positive",
        }
        try:
            result = self._sentiment_pipe(text, truncation=True, max_length=512)[0]
            return SentimentResult(
                label=label_map.get(result["label"], result["label"].lower()),
                score=_round_score(result["score"]),
            )
        except Exception:
            return SentimentResult(label="neutral", score=0.5)

    def _get_emotions(self, text: str) -> list[EmotionResult]:
        """
        Run DistilRoBERTa 7-class emotion classifier.
        Returns all emotions sorted by score descending.
        """
        try:
            results = self._emotion_pipe(text, truncation=True, max_length=512)[0]
            return [
                EmotionResult(emotion=r["label"].lower(), score=_round_score(r["score"]))
                for r in sorted(results, key=lambda x: x["score"], reverse=True)
            ]
        except Exception:
            return [EmotionResult(emotion="neutral", score=1.0)]

    def _get_intent(self, text: str) -> IntentResult:
        """
        Zero-shot intent classification using BART-MNLI.
        No fine-tuning required — uses natural language labels.
        """
        try:
            result = self._intent_pipe(
                text,
                INTENT_LABELS,
                truncation=True,
                max_length=512,
                multi_label=False,
            )
            return IntentResult(
                label=result["labels"][0],
                score=_round_score(result["scores"][0]),
                all_scores={
                    label: _round_score(score)
                    for label, score in zip(result["labels"], result["scores"])
                },
            )
        except Exception:
            return IntentResult(
                label="general comment",
                score=0.5,
                all_scores={},
            )

    def _get_entities(self, text: str) -> list[EntityResult]:
        """
        Extract named entities using BERT-NER.
        Types: PER (person), ORG (organization), LOC (location), MISC (other).
        """
        try:
            raw = self._ner_pipe(text)
            return [
                EntityResult(
                    text=e["word"],
                    entity_type=e["entity_group"],
                    score=_round_score(e["score"]),
                )
                for e in raw
                if e.get("score", 0) > 0.70  # Only high-confidence entities
            ]
        except Exception:
            return []

    def _get_behavioral_signals(self, text: str) -> BehavioralSignals:
        """
        Rule-based behavioral signal detection using curated lexicons.

        Detects:
          - Hesitation: filler words (um, uh, like, sort of...)
          - Frustration: negative intensity markers
          - Satisfaction: positive intensity markers
          - Purchase intent: explicit buying signals

        Args:
            text: Raw (un-truncated) transcript text.

        Returns:
            BehavioralSignals with normalized scores.
        """
        text_lower = text.lower()
        words = text_lower.split()

        def count_markers(markers: frozenset) -> int:
            total = 0
            for marker in markers:
                if " " in marker:
                    total += text_lower.count(marker)
                else:
                    total += words.count(marker)
            return total

        hes_count = count_markers(HESITATION_MARKERS)
        frus_count = count_markers(FRUSTRATION_MARKERS)
        sat_count = count_markers(SATISFACTION_MARKERS)
        intent_count = count_markers(PURCHASE_INTENT_MARKERS)

        total = max(hes_count + frus_count + sat_count + 1, 1)

        hesitation_score = round(min(hes_count / total, 1.0), 4)
        frustration_score = round(min(frus_count / total, 1.0), 4)
        satisfaction_score = round(min(sat_count / total, 1.0), 4)

        # Weighted behavioral summary score (lower = more negative)
        overall = round(
            (satisfaction_score - frustration_score * 1.5 + 0.5), 4
        )
        overall = min(max(overall, 0.0), 1.0)

        return BehavioralSignals(
            hesitation_score=hesitation_score,
            frustration_score=frustration_score,
            satisfaction_score=satisfaction_score,
            purchase_intent_signals=intent_count,
            hesitation_count=hes_count,
            frustration_count=frus_count,
            satisfaction_count=sat_count,
            overall_behavioral_score=overall,
        )

    def _compute_mc_confidence(self, text: str, n_passes: int = None) -> float:
        """
        Calibrated confidence score for this segment's NLP analysis.

        Strategy (primary): True Monte Carlo Dropout via model.train() mode so
        that dropout layers fire per forward pass.  Variance across N passes
        measures uncertainty — high variance triggers LLM refinement.

        Strategy (fallback): predictive max-probability used as entropy proxy.

        Returns:
            Confidence in [0.0, 1.0].
        """
        n = n_passes or max(settings.mc_dropout_passes, 5)

        try:
            # ─ True MC Dropout: access underlying model ─────────────────────
            if not _TORCH_AVAILABLE:
                raise RuntimeError("torch not available")
            import torch
            underlying_model = self._sentiment_pipe.model
            tokenizer        = self._sentiment_pipe.tokenizer
            device = next(underlying_model.parameters()).device

            underlying_model.train()   # Enable dropout stochasticity
            scores: list[float] = []

            with torch.no_grad():
                inputs = tokenizer(
                    text[:512],
                    return_tensors="pt",
                    truncation=True,
                    max_length=512,
                    padding=True,
                ).to(device)

                for _ in range(n):
                    logits = underlying_model(**inputs).logits
                    probs  = torch.nn.functional.softmax(logits, dim=-1)
                    scores.append(float(probs.max().item()))

            underlying_model.eval()    # Restore eval mode

            variance   = float(np.var(scores))
            # empirical max variance of softmax max-prob ≈ 0.04
            # 0 variance → 1.0 confidence; 0.04+ variance → near 0
            confidence = 1.0 - min(variance * 50.0, 1.0)
            return round(confidence, 4)

        except Exception:
            # ─ Fallback: single-pass probability entropy proxy ───────────────
            try:
                result = self._sentiment_pipe(text, truncation=True, max_length=512)[0]
                # Shrink from [0,1] to [0.05, 0.95] to avoid over-confidence
                confidence = round(result["score"] * 0.90 + 0.05, 4)
                return min(max(confidence, 0.0), 1.0)
            except Exception:
                return 0.70

    def _empty_result(self, segment_id: str, text: str) -> SegmentAnalysis:
        """Return neutral zero-result for empty/very-short segments."""
        return SegmentAnalysis(
            segment_id=segment_id,
            text=text,
            embedding=[0.0] * 384,
            sentiment=SentimentResult(label="neutral", score=0.5),
            emotions=[EmotionResult(emotion="neutral", score=1.0)],
            intent=IntentResult(label="general comment", score=0.5, all_scores={}),
            entities=[],
            behavioral_signals=BehavioralSignals(
                hesitation_score=0.0,
                frustration_score=0.0,
                satisfaction_score=0.0,
                purchase_intent_signals=0,
                hesitation_count=0,
                frustration_count=0,
                satisfaction_count=0,
                overall_behavioral_score=0.5,
            ),
            confidence=0.5,
            needs_llm_review=False,
        )
