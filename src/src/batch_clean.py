import json
import re
import sys
from pathlib import Path


def clean_text(text):
    text = str(text).strip()
    text = re.sub(r"\s+", " ", text)

    # Remove repeated punctuation
    text = re.sub(r"([।!?])\1+", r"\1", text)

    # Remove exact consecutive duplicate words
    words = text.split()
    cleaned_words = []

    for word in words:
        if not cleaned_words or word != cleaned_words[-1]:
            cleaned_words.append(word)

    return " ".join(cleaned_words)


def clean_transcript(input_path, output_path):
    input_file = Path(input_path)
    output_file = Path(output_path)

    with open(input_file, "r", encoding="utf-8") as file:
        data = json.load(file)

    cleaned_segments = []

    for segment in data.get("segments", []):
        text = clean_text(segment.get("nepali", ""))

        if not text:
            continue

        cleaned_segments.append({
            "start": segment.get("start", 0),
            "end": segment.get("end", 0),
            "nepali": text
        })

    cleaned_data = {
        "video": data.get("video"),
        "language": data.get("language", "ne"),
        "language_probability": data.get("language_probability"),
        "model": data.get("model"),
        "segments": cleaned_segments
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(
            cleaned_data,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(f"Cleaned: {input_file}")
    print(f"Saved:   {output_file}")
    print(f"Segments: {len(cleaned_segments)}")


def clean_directory(input_dir, output_dir):
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    output_path.mkdir(parents=True, exist_ok=True)

    transcript_files = sorted(
        input_path.glob("video_*.json")
    )

    if not transcript_files:
        raise RuntimeError(
            f"No transcript files found in {input_path}"
        )

    print("")
    print("====================================")
    print("BATCH TRANSCRIPT CLEANING")
    print("====================================")
    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    print(f"Files:  {len(transcript_files)}")

    successful = 0

    for index, transcript_file in enumerate(
        transcript_files,
        start=1
    ):
        output_file = output_path / transcript_file.name

        print("")
        print("------------------------------------")
        print(
            f"TRANSCRIPT {index}/{len(transcript_files)}"
        )
        print(f"File: {transcript_file.name}")
        print("------------------------------------")

        try:
            clean_transcript(
                transcript_file,
                output_file
            )
            successful += 1
        except Exception as error:
            print(f"Cleaning failed: {error}")

    summary = {
        "input_directory": str(input_path),
        "output_directory": str(output_path),
        "total_files": len(transcript_files),
        "successful": successful
    }

    summary_file = output_path / "cleaning_summary.json"

    with open(
        summary_file,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            summary,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("")
    print("====================================")
    print("CLEANING SUMMARY")
    print("====================================")
    print(f"Total:      {len(transcript_files)}")
    print(f"Successful: {successful}")
    print(f"Summary:    {summary_file}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage:")
        print(
            "python src/batch_clean.py "
            "<input_transcript_directory> "
            "<output_directory>"
        )
        sys.exit(1)

    input_dir = sys.argv[1]
    output_dir = sys.argv[2]

    clean_directory(
        input_dir,
        output_dir
    )
