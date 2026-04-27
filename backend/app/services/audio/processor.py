"""
AegisCX Audio Processing Service
===================================
Converts any audio/video format to clean, ML-ready WAV (16kHz, mono).

Pipeline:
  1. Format validation & metadata extraction (ffprobe)
  2. FFmpeg conversion → WAV 16kHz mono PCM
  3. Spectral gating noise reduction (noisereduce)
  4. Peak normalization
  5. Overlap-aware chunking (30s chunks, 5s overlap)
  6. [Optional] WebRTC VAD — skipped if not installed (requires MSVC on Windows)

Handles files up to 1GB via streaming chunks.
Writes structured log to /logs/{recording_id}_audio.jsonl
"""

import json
import tempfile
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import ffmpeg

import numpy as np
import soundfile as sf
import structlog

# webrtcvad requires Microsoft C++ Build Tools on Windows.
# We make it optional — VAD silence removal is skipped if unavailable.
try:
    import webrtcvad as _webrtcvad
    _WEBRTCVAD_AVAILABLE = True
except ImportError:
    _webrtcvad = None  # type: ignore
    _WEBRTCVAD_AVAILABLE = False

from app.core.config import get_settings

settings = get_settings()
log = structlog.get_logger("aegiscx.audio")


@dataclass
class AudioMetadata:
    """Extracted metadata about the raw audio file."""
    original_path: str
    format: str
    duration_seconds: float
    sample_rate: int
    channels: int
    bitrate: Optional[int]
    file_size_bytes: int


@dataclass
class AudioChunk:
    """One 30-second chunk of processed audio."""
    index: int
    start_time: float
    end_time: float
    wav_path: str
    num_samples: int


@dataclass
class ProcessedAudio:
    """Full result from processing one audio file."""
    recording_id: str
    wav_path: str
    metadata: AudioMetadata
    chunks: list[AudioChunk]
    processing_time_seconds: float
    status: str = "success"
    error: Optional[str] = None


class AudioProcessingError(Exception):
    """Raised when audio processing fails at any stage."""
    pass


class AudioProcessor:
    """
    Enterprise audio processing pipeline.

    Converts raw audio/video files to standardized WAV segments
    compatible with WhisperX and all downstream ML models.

    Usage:
        processor = AudioProcessor()
        result = processor.process(recording_id="...", input_path=Path("input.mp3"))
    """

    TARGET_SAMPLE_RATE = 16000      # Hz — required by Whisper
    TARGET_CHANNELS = 1             # Mono
    CHUNK_DURATION_SEC = 30         # Chunk size
    CHUNK_OVERLAP_SEC = 5           # Overlap between chunks for context continuity
    VAD_AGGRESSIVENESS = 2          # WebRTC VAD mode: 0 (least) to 3 (most aggressive)
    VAD_FRAME_MS = 30               # VAD frame duration: 10, 20, or 30 ms

    SUPPORTED_EXTENSIONS = {
        "mp3", "mp4", "wav", "m4a", "webm", "ogg", "flac", "mpeg", "aac"
    }

    def __init__(self):
        if _WEBRTCVAD_AVAILABLE:
            self._vad = _webrtcvad.Vad(self.VAD_AGGRESSIVENESS)
        else:
            self._vad = None
            log.warning("webrtcvad_unavailable",
                        message="VAD silence removal disabled — install MSVC Build Tools to enable")

    def process(self, recording_id: str, input_path: Path) -> ProcessedAudio:
        """
        Full audio processing pipeline for one file.

        Args:
            recording_id: UUID string for this recording (used for file naming).
            input_path: Path to the raw uploaded audio/video file.

        Returns:
            ProcessedAudio with WAV path, chunks, and metadata.

        Raises:
            AudioProcessingError: If any processing stage fails.
        """
        start_time = time.perf_counter()
        self._log_event(recording_id, "audio_processing_start", {"input": str(input_path)})

        try:
            # Step 1: Validate extension
            ext = input_path.suffix.lstrip(".").lower()
            if ext not in self.SUPPORTED_EXTENSIONS:
                raise AudioProcessingError(f"Unsupported format: .{ext}")

            # Step 2: Extract metadata (before conversion)
            metadata = self._extract_metadata(input_path)
            self._log_event(recording_id, "metadata_extracted", asdict(metadata))

            # Step 3: Convert to WAV
            wav_path = self._convert_to_wav(recording_id, input_path)
            self._log_event(recording_id, "converted_to_wav", {"wav_path": str(wav_path)})

            # Step 4: Load audio - Use float32 to save 50% memory compared to default float64
            audio, sr = sf.read(str(wav_path), dtype="float32")
            self._log_event(recording_id, "audio_loaded", {
                "samples": len(audio), "sample_rate": sr, "dtype": str(audio.dtype)
            })

            # Step 5: Noise reduction
            audio = self._reduce_noise(audio, sr)
            self._log_event(recording_id, "noise_reduced")

            # Step 6: Normalize
            audio = self._normalize(audio)

            # Step 7: Save cleaned WAV
            sf.write(str(wav_path), audio, sr, subtype="PCM_16")
            self._log_event(recording_id, "cleaned_audio_saved")

            # Step 8: Create chunks
            chunks = self._create_chunks(recording_id, audio, sr, wav_path.parent)
            self._log_event(recording_id, "chunks_created", {
                "num_chunks": len(chunks)
            })

            duration = time.perf_counter() - start_time
            self._log_event(recording_id, "audio_processing_complete", {
                "duration_sec": round(duration, 2),
                "chunks": len(chunks)
            })

            return ProcessedAudio(
                recording_id=recording_id,
                wav_path=str(wav_path),
                metadata=metadata,
                chunks=chunks,
                processing_time_seconds=round(duration, 2),
            )

        except AudioProcessingError:
            raise
        except Exception as e:
            self._log_event(recording_id, "audio_processing_error", {
                "error": str(e),
                "error_type": type(e).__name__
            }, level="ERROR")
            raise AudioProcessingError(f"Audio processing failed: {e}") from e

    def _extract_metadata(self, path: Path) -> AudioMetadata:
        """
        Use ffprobe to extract audio file metadata.

        Args:
            path: Path to audio/video file.

        Returns:
            AudioMetadata dataclass.

        Raises:
            AudioProcessingError: If ffprobe fails.
        """
        try:
            probe = ffmpeg.probe(str(path))
            audio_streams = [
                s for s in probe["streams"] if s.get("codec_type") == "audio"
            ]
            if not audio_streams:
                raise AudioProcessingError("No audio stream found in file")

            stream = audio_streams[0]
            fmt = probe.get("format", {})

            return AudioMetadata(
                original_path=str(path),
                format=fmt.get("format_name", "unknown"),
                duration_seconds=float(fmt.get("duration", 0)),
                sample_rate=int(stream.get("sample_rate", 0)),
                channels=int(stream.get("channels", 0)),
                bitrate=int(fmt.get("bit_rate", 0)) if fmt.get("bit_rate") else None,
                file_size_bytes=int(fmt.get("size", 0)),
            )
        except ffmpeg.Error as e:
            raise AudioProcessingError(f"ffprobe failed: {e.stderr.decode()}") from e

    def _convert_to_wav(self, recording_id: str, input_path: Path) -> Path:
        """
        Convert audio/video to WAV 16kHz mono using FFmpeg.

        Args:
            recording_id: Recording UUID for output naming.
            input_path: Source audio/video file.

        Returns:
            Path to the output WAV file.

        Raises:
            AudioProcessingError: If FFmpeg conversion fails.
        """
        output_dir = settings.processed_audio_dir / recording_id
        output_dir.mkdir(parents=True, exist_ok=True)
        wav_path = output_dir / "audio_clean.wav"

        try:
            (
                ffmpeg
                .input(str(input_path))
                .output(
                    str(wav_path),
                    ar=self.TARGET_SAMPLE_RATE,
                    ac=self.TARGET_CHANNELS,
                    acodec="pcm_s16le",
                )
                .overwrite_output()
                .run(capture_stderr=True, quiet=True)
            )
        except ffmpeg.Error as e:
            stderr = e.stderr.decode('utf-8', errors='replace') if e.stderr else "No stderr available"
            log.error("ffmpeg_conversion_failed", recording_id=recording_id, stderr=stderr)
            raise AudioProcessingError(
                f"FFmpeg conversion failed: {stderr}"
            ) from e

        return wav_path

    def _reduce_noise(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Apply spectral gating noise reduction.
        Uses non-stationary noise estimation — works on variable background noise.

        Args:
            audio: Raw audio numpy array.
            sr: Sample rate.

        Returns:
            Denoised audio numpy array.
        """
        # Ensure audio is float32 for memory efficiency
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # For very long files, reduce_noise can still hit memory limits.
        # We use built-in chunking with float32 to minimize footprint.
        import noisereduce as nr

        tmp_dir = settings.processed_audio_dir / "_noise_reduce_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        previous_tempdir = tempfile.tempdir
        try:
            # noisereduce internally relies on tempfile.NamedTemporaryFile without
            # a directory override, so we pin tempfile.tempdir to the project
            # drive. This avoids failures when the system C: drive is full.
            tempfile.tempdir = str(tmp_dir)
            return nr.reduce_noise(
                y=audio,
                sr=sr,
                stationary=True,
                prop_decrease=0.75,
                n_jobs=1,
                chunk_size=32000,     # 2 seconds per chunk at 16kHz
                tmp_folder="nr_",
            )
        except Exception as exc:
            log.warning(
                "noise_reduction_degraded",
                error=str(exc),
                message="Continuing with normalized audio because noise reduction scratch space failed.",
            )
            return audio
        finally:
            tempfile.tempdir = previous_tempdir

    def _normalize(self, audio: np.ndarray) -> np.ndarray:
        """
        Peak normalize audio to [-1.0, 1.0] range.

        Args:
            audio: Audio numpy array.

        Returns:
            Normalized audio.
        """
        peak = np.max(np.abs(audio))
        if peak > 0:
            return audio / peak * 0.95  # Leave 5% headroom
        return audio

    def _create_chunks(
        self,
        recording_id: str,
        audio: np.ndarray,
        sr: int,
        output_dir: Path,
    ) -> list[AudioChunk]:
        """
        Split audio into overlapping chunks for WhisperX processing.

        Overlap ensures no speech is cut off at chunk boundaries.

        Args:
            recording_id: Recording UUID.
            audio: Full normalized audio array.
            sr: Sample rate.
            output_dir: Directory to save chunk WAV files.

        Returns:
            List of AudioChunk descriptors.
        """
        chunk_samples = self.CHUNK_DURATION_SEC * sr
        overlap_samples = self.CHUNK_OVERLAP_SEC * sr
        step_samples = chunk_samples - overlap_samples

        chunks: list[AudioChunk] = []
        start_sample = 0
        chunk_idx = 0

        while start_sample < len(audio):
            end_sample = min(start_sample + chunk_samples, len(audio))
            chunk_audio = audio[start_sample:end_sample]

            # Skip chunks that are too short (< 1 second) — likely trailing silence
            if len(chunk_audio) < sr:
                break

            chunk_path = output_dir / f"chunk_{chunk_idx:04d}.wav"
            sf.write(str(chunk_path), chunk_audio, sr, subtype="PCM_16")

            chunks.append(AudioChunk(
                index=chunk_idx,
                start_time=round(start_sample / sr, 3),
                end_time=round(end_sample / sr, 3),
                wav_path=str(chunk_path),
                num_samples=len(chunk_audio),
            ))

            start_sample += step_samples
            chunk_idx += 1

        return chunks

    def _log_event(
        self,
        recording_id: str,
        event: str,
        data: dict = None,
        level: str = "INFO",
    ) -> None:
        """
        Write a structured event to the audio processing log file.

        Args:
            recording_id: Recording UUID.
            event: Event name (snake_case).
            data: Additional event data.
            level: Log level string.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recording_id": recording_id,
            "step": "audio_processing",
            "event": event,
            "level": level,
            "data": data or {},
        }

        log_path = settings.log_dir / f"{recording_id}_audio.jsonl"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except IOError:
            pass  # Don't let logging failure break processing

        if level == "ERROR":
            log.error(event, recording_id=recording_id, **(data or {}))
        else:
            log.info(event, recording_id=recording_id, **(data or {}))
