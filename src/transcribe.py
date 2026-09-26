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
        "large-v3-turbo",
        device="cpu",
        compute_type="int8"
    )

    segments, info = model.transcribe(
        str(video),
        language="ne",
        task="transcribe",
        beam_size=5,
        best_of=5,
        temperature=0,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=True,
        initial_prompt=(
            "यो नेपालको संघीय संसदको औपचारिक बैठक हो। "
            "नेपाली भाषामा सभामुख, अध्यक्ष, सांसद, "
            "मन्त्री तथा सरकारी अधिकारीहरूले सम्बोधन "
            "गरिरहेका छन्। "
            "सम्भव भएसम्म स्पष्ट र शुद्ध नेपाली शब्द "
            "प्रयोग गर्नुहोस्।"
        )
    )

    transcript = {
        "video": str(video),
        "language": info.language,
        "language_probability": (
            info.language_probability
        ),
        "model": "large-v3-turbo",
        "segments": []
    }

    for segment in segments:
        text = segment.text.strip()

        if not text:
            continue

        transcript["segments"].append({
            "start": round(segment.start, 3),
            "end": round(segment.end, 3),
            "nepali": text
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
