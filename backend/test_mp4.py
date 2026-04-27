from pathlib import Path
from uuid import uuid4

import ffmpeg


def test_ffmpeg_can_extract_audio_from_sample_mp4():
    root = Path(__file__).resolve().parent
    input_path = root / "dummy_with_audio.mp4"
    output_dir = root / "data" / "test_outputs"
    output_path = output_dir / f"dummy_with_audio_{uuid4().hex}.wav"

    output_dir.mkdir(parents=True, exist_ok=True)

    (
        ffmpeg
        .input(str(input_path))
        .output(
            str(output_path),
            ar=16000,
            ac=1,
            acodec="pcm_s16le",
        )
        .overwrite_output()
        .run(quiet=True)
    )

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    try:
        output_path.unlink(missing_ok=True)
    except PermissionError:
        # Windows can keep the file handle around briefly after ffmpeg exits.
        pass
