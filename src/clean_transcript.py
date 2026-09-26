import json
import re
import sys
from pathlib import Path


def clean_text(text: str) -> str:
    text = text.strip()

    # Remove excessive repeated spaces
    text = re.sub(r"\s+", " ", text)

    # Remove obvious character garbage
    text = re.sub(r"[^\u0900-\u097F0-9A-Za-z\s.,!?%():/\-]", "", text)

    # Detect immediate repeated words:
    # "वार्षिक वार्षिक वार्षिक" -> "वार्षिक"
    words = text.split()
    cleaned_words = []

    for word in words:
        if not cleaned_words or word != cleaned_words[-1]:
            cleaned_words.append(word)

    return " ".join(cleaned_words).strip()


def clean_transcript(input_path: str, output_path: str):
    input_file = Path(input_path)
    output_file = Path(output_path)

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

    cleaned_segments = []

    for segment in transcript.get("segments", []):
        original = segment.get("nepali", "")
        cleaned = clean_text(original)

        if not cleaned:
            continue

        cleaned_segment = dict(segment)
        cleaned_segment["nepali"] = cleaned

        cleaned_segments.append(cleaned_segment)

    transcript["segments"] = cleaned_segments
    transcript["cleaned"] = True

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        output_file,
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
        f"Cleaned transcript saved to: {output_file}"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python clean_transcript.py "
            "<input_json> <output_json>"
        )
        sys.exit(1)

    clean_transcript(
        sys.argv[1],
        sys.argv[2]
    )
