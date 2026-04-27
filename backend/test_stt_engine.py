import asyncio
import sys
from pathlib import Path
from pprint import pprint
import time

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_stt_engine.py <path_to_audio_or_video_file>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"Error: File not found -> {input_path}")
        sys.exit(1)

    print(f"Testing End-to-End Speech Intelligence Pipeline on: {input_path.name}")
    print("=" * 60)

    # Need to run in an established backend context to load env vars and settings
    try:
        from app.services.audio.processor import AudioProcessor
        from app.services.stt.engine import STTEngine
        from app.core.config import get_settings
    except ImportError as e:
        print(f"Import Error: {e}")
        print("Make sure you run this script from the 'backend' directory with the active virtual environment.")
        sys.exit(1)

    recording_id = "test-eval-" + str(int(time.time()))

    print("\n[STEP 1] INITIALIZING AUDIO PROCESSOR...")
    processor = AudioProcessor()

    print(f"\n[STEP 2] PROCESSING AUDIO -> Chunking, Resampling, Noise Reduction...")
    try:
        processed_audio = processor.process(recording_id=recording_id, input_path=input_path)
        print(f"  -> SUCCESS! Created {len(processed_audio.chunks)} chunks.")
        print(f"  -> Processed audio saved to: {processed_audio.wav_path}")
        print(f"  -> Metadata Info: {processed_audio.metadata}")
    except Exception as e:
        print(f"  -> ERROR during audio processing: {e}")
        sys.exit(1)

    print("\n[STEP 3] INITIALIZING STT ENGINE (Faster-Whisper / WhisperX)...")
    try:
        stt_engine = STTEngine()
        # Ensure model gets loaded before we count the transcription time
        stt_engine._load_models()
        print(f"  -> SUCCESS! Loaded Model: {'WhisperX' if stt_engine._whisperx_available else 'faster-whisper'}")
    except Exception as e:
        print(f"  -> ERROR initializing STT engine: {e}")
        sys.exit(1)

    print(f"\n[STEP 4] TRANSCRIBING AUDIO CHUNKS WITH MULTILINGUAL AUTO-DETECT...")
    try:
        start_time = time.time()
        # Num speakers will be auto-handled or ignored for faster-whisper base
        result = stt_engine.transcribe(recording_id=recording_id, chunks=processed_audio.chunks)
        duration = time.time() - start_time

        print("\n" + "=" * 60)
        print("TRANSCRIPTION RESULTS:")
        print("=" * 60)
        print(f"Language Detected : {result.language} (English code usually means translated or processed internally via auto)")
        print(f"Engine Used       : {result.stt_model_used}")
        print(f"Total Words       : {result.word_count}")
        print(f"Transcription Time: {duration:.2f} seconds")
        print("\n[FULL TEXT]")
        print("-" * 60)
        print(result.full_text)
        print("-" * 60)

        # Print out first 3 dynamic segments to show timestamps and confidence
        print("\n[SEGMENT ANALYSIS (Top 3)]")
        for i, seg in enumerate(result.segments[:3]):
            print(f"  [{seg.start:.2f}s - {seg.end:.2f}s] {seg.speaker}: {seg.text}")
            
    except Exception as e:
        print(f"  -> ERROR transcribing audio: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
