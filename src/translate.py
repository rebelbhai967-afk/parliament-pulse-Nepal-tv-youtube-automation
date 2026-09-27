import json
import sys
import time
from pathlib import Path

from deep_translator import GoogleTranslator


def format_time(seconds):
    seconds = float(seconds)

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))

    if millis >= 1000:
        secs += 1
        millis = 0

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d},"
        f"{millis:03d}"
    )


def translate_text(text, translator):
    if not text.strip():
        return ""

    try:
        return translator.translate(
            text
        ).strip()
    except Exception as error:
        print(
            f"Translation failed: {error}"
        )
        return text


def create_srt(
    transcript_path,
    output_path
):
    input_file = Path(
        transcript_path
    )

    output_file = Path(
        output_path
    )

    if not input_file.exists():
        raise FileNotFoundError(
            f"Transcript not found: {input_file}"
        )

    with open(
        input_file,
        "r",
        encoding="utf-8"
    ) as file:
        transcript = json.load(file)

    segments = transcript.get(
        "segments",
        []
    )

    if not segments:
        raise RuntimeError(
            "No transcript segments found."
        )

    translator = GoogleTranslator(
        source="ne",
        target="en"
    )

    subtitles = []

    print(
        f"Translating {len(segments)} segments..."
    )

    for index, segment in enumerate(
        segments,
        start=1
    ):
        nepali = segment.get(
            "nepali",
            ""
        ).strip()

        if not nepali:
            continue

        print(
            f"Translating {index}/{len(segments)}"
        )

        english = translate_text(
            nepali,
            translator
        )

        subtitles.append({
            "index": len(subtitles) + 1,
            "start": segment.get(
                "start",
                0
            ),
            "end": segment.get(
                "end",
                0
            ),
            "nepali": nepali,
            "english": english
        })

        time.sleep(0.2)

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:

        for subtitle in subtitles:

            file.write(
                f"{subtitle['index']}\n"
            )

            file.write(
                f"{format_time(subtitle['start'])}"
                f" --> "
                f"{format_time(subtitle['end'])}\n"
            )

            file.write(
                f"{subtitle['english']}\n\n"
            )

    print("")
    print(
        f"English subtitles saved to: "
        f"{output_file}"
    )


if __name__ == "__main__":

    if len(sys.argv) != 3:
        print(
            "Usage:"
        )
        print(
            "python translate.py "
            "<transcript_json> "
            "<output_srt>"
        )
        sys.exit(1)

    create_srt(
        sys.argv[1],
        sys.argv[2]
    )
