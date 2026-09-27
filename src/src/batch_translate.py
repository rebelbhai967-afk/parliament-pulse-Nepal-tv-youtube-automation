import json
import sys
import time
from pathlib import Path

from deep_translator import GoogleTranslator


def format_srt_time(seconds):
    seconds = max(0, float(seconds))

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))

    if millis >= 1000:
        secs += 1
        millis -= 1000

    if secs >= 60:
        minutes += 1
        secs -= 60

    if minutes >= 60:
        hours += 1
        minutes -= 60

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d},"
        f"{millis:03d}"
    )


def translate_text(translator, text):
    text = str(text).strip()

    if not text:
        return ""

    try:
        return translator.translate(text)
    except Exception as error:
        print(f"Translation failed: {error}")
        return text


def create_story_subtitles(
    transcript_path,
    story,
    output_path
):
    transcript_file = Path(transcript_path)

    if not transcript_file.exists():
        raise FileNotFoundError(
            f"Transcript not found: {transcript_file}"
        )

    with open(
        transcript_file,
        "r",
        encoding="utf-8"
    ) as file:
        data = json.load(file)

    story_start = float(
        story.get("start", 0)
    )

    story_end = float(
        story.get("end", 0)
    )

    if story_end <= story_start:
        raise ValueError(
            "Invalid story timestamps."
        )

    translator = GoogleTranslator(
        source="ne",
        target="en"
    )

    output = Path(output_path)
    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    subtitle_index = 1

    with open(
        output,
        "w",
        encoding="utf-8"
    ) as file:

        for segment in data.get(
            "segments",
            []
        ):
            start = float(
                segment.get("start", 0)
            )

            end = float(
                segment.get("end", 0)
            )

            nepali = str(
                segment.get(
                    "nepali",
                    ""
                )
            ).strip()

            if not nepali:
                continue

            # Ignore segments outside selected story.
            if end <= story_start:
                continue

            if start >= story_end:
                continue

            # Keep subtitle inside selected story.
            actual_start = max(
                start,
                story_start
            )

            actual_end = min(
                end,
                story_end
            )

            # Convert absolute Parliament timestamp
            # into timestamp relative to the generated clip.
            relative_start = (
                actual_start - story_start
            )

            relative_end = (
                actual_end - story_start
            )

            if relative_end <= relative_start:
                continue

            english = translate_text(
                translator,
                nepali
            )

            if not english:
                continue

            file.write(
                f"{subtitle_index}\n"
            )

            file.write(
                f"{format_srt_time(relative_start)} "
                f"--> "
                f"{format_srt_time(relative_end)}\n"
            )

            file.write(
                f"{english}\n\n"
            )

            subtitle_index += 1

            time.sleep(0.15)

    print("")
    print("====================================")
    print("ENGLISH STORY SUBTITLES CREATED")
    print("====================================")
    print(f"Transcript: {transcript_file}")
    print(f"Output:     {output}")
    print(f"Story start: {story_start:.2f}")
    print(f"Story end:   {story_end:.2f}")
    print(
        f"Entries:     "
        f"{subtitle_index - 1}"
    )


def find_transcript(story, transcript_dir):
    if not story:
        return None

    transcript = story.get(
        "transcript"
    )

    if transcript:
        path = Path(transcript)

        if path.exists():
            return path

    video = story.get("video")

    if video:
        video_path = Path(video)

        candidate = (
            Path(transcript_dir)
            / f"{video_path.stem}.json"
        )

        if candidate.exists():
            return candidate

    return None


def translate_selected_stories(
    selection_file,
    transcript_dir,
    output_dir
):
    with open(
        selection_file,
        "r",
        encoding="utf-8"
    ) as file:
        selection = json.load(file)

    output = Path(output_dir)
    output.mkdir(
        parents=True,
        exist_ok=True
    )

    long_story = selection.get(
        "long_video"
    )

    short_story = selection.get(
        "short_video"
    )

    print("")
    print("====================================")
    print("DAILY ENGLISH SUBTITLE GENERATION")
    print("====================================")

    # ----------------------------------------
    # LONG
    # ----------------------------------------

    if long_story:
        transcript = find_transcript(
            long_story,
            transcript_dir
        )

        if not transcript:
            raise RuntimeError(
                "Long story transcript not found."
            )

        create_story_subtitles(
            transcript,
            long_story,
            output / "long_subtitles.srt"
        )

    # ----------------------------------------
    # SHORT
    # ----------------------------------------

    if short_story:
        transcript = find_transcript(
            short_story,
            transcript_dir
        )

        if not transcript:
            raise RuntimeError(
                "Short story transcript not found."
            )

        create_story_subtitles(
            transcript,
            short_story,
            output / "short_subtitles.srt"
        )

    print("")
    print("SUBTITLE GENERATION COMPLETE")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage:")
        print(
            "python src/batch_translate.py "
            "<daily_selection.json> "
            "<transcript_directory> "
            "<output_directory>"
        )
        sys.exit(1)

    translate_selected_stories(
        sys.argv[1],
        sys.argv[2],
        sys.argv[3]
    )
