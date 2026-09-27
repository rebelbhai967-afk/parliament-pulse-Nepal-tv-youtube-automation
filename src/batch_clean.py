import json
import re
import sys
from pathlib import Path


def clean_text(text):
    text = str(text).strip()

    # Normalize whitespace.
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    # Remove spaces before punctuation.
    text = re.sub(
        r"\s+([।,!?;:])",
        r"\1",
        text
    )

    return text


def remove_consecutive_duplicates(text):
    words = text.split()

    if not words:
        return ""

    cleaned = [words[0]]

    for word in words[1:]:
        if word != cleaned[-1]:
            cleaned.append(word)

    return " ".join(cleaned)


def clean_transcript(input_file, output_file):
    input_path = Path(input_file)
    output_path = Path(output_file)

    with open(
        input_path,
        "r",
        encoding="utf-8"
    ) as file:
        data = json.load(file)

    cleaned_segments = []

    for segment in data.get("segments", []):
        text = segment.get("nepali", "")

        text = clean_text(text)

        text = remove_consecutive_duplicates(
            text
        )

        if not text:
            continue

        cleaned_segments.append({
            "start": float(
                segment.get("start", 0)
            ),
            "end": float(
                segment.get("end", 0)
            ),
            "nepali": text
        })

    result = dict(data)

    result["segments"] = cleaned_segments
    result["cleaned"] = True

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(f"Cleaned: {input_path}")
    print(f"Output:  {output_path}")
    print(
        f"Segments: "
        f"{len(cleaned_segments)}"
    )


def clean_directory(input_dir, output_dir):
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    output_path.mkdir(
        parents=True,
        exist_ok=True
    )

    transcript_files = sorted(
        input_path.glob("video_*.json")
    )

    if not transcript_files:
        raise RuntimeError(
            "No video transcript files found."
        )

    print("")
    print("====================================")
    print("BATCH TRANSCRIPT CLEANING")
    print("====================================")
    print(
        f"Input files: "
        f"{len(transcript_files)}"
    )

    successful = 0
    failed = 0

    for index, input_file in enumerate(
        transcript_files,
        start=1
    ):
        output_file = (
            output_path / input_file.name
        )

        print("")
        print(
            f"FILE {index}/"
            f"{len(transcript_files)}"
        )

        try:
            clean_transcript(
                input_file,
                output_file
            )

            successful += 1

        except Exception as error:
            failed += 1

            print(
                f"Cleaning failed: {error}"
            )

    print("")
    print("====================================")
    print("CLEANING SUMMARY")
    print("====================================")
    print(
        f"Total:      {len(transcript_files)}"
    )
    print(
        f"Successful: {successful}"
    )
    print(
        f"Failed:     {failed}"
    )

    if successful == 0:
        raise RuntimeError(
            "No transcripts were cleaned."
        )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage:")
        print(
            "python src/batch_clean.py "
            "<input_directory> "
            "<output_directory>"
        )
        sys.exit(1)

    clean_directory(
        sys.argv[1],
        sys.argv[2]
    )
