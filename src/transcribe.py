import json
import sys
from pathlib import Path

from faster_whisper import WhisperModel


def transcribe_video(video_path: str, output_path: str):
    video = Path(video_path)
    output = Path(output_path)

    if not video.exists():
        raise FileNotFoundError(
            f"Video not found: {video}"
        )

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    print(f"Transcribing: {video}")

    model = WhisperModel(
        "medium",
        device="cpu",
        compute_type="int8"
    )

    segments, info = model.transcribe(
        str(video),
        language="ne",
        task="transcribe",
        beam_size=5,
        temperature=0,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=True,
        initial_prompt=(
            "यो नेपालको संघीय संसदको औपचारिक बैठक हो। "
            "नेपाली भाषामा सभामुख, अध्यक्ष, सांसद, "
            "मन्त्री तथा सरकारी अधिकारीहरूले सम्बोधन "
            "गरिरहेका छन्।"
        )
    )

    transcript = {
        "video": str(video),
        "language": info.language,
        "language_probability": (
            info.language_probability
        ),
        "model": "medium",
        "segments": []
    }

    for segment in segments:
        transcript["segments"].append({
            "start": round(segment.start, 3),
            "end": round(segment.end, 3),
            "nepali": segment.text.strip()
        })

    with open(
        output,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            transcript,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"Transcript saved to: {output}"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python transcribe.py "
            "<video_path> <output_json>"
        )
        sys.exit(1)

    transcribe_video(
        sys.argv[1],
        sys.argv[2]
    )
