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
    millis = int(
        round((seconds - int(seconds)) * 1000)
    )

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
        print(
            f"Translation failed: {error}"
        )
        return text


def translate_transcript(
    transcript_path,
    output_path
):
    transcript_file = Path(
        transcript_path
    )
    output_file = Path(
        output_path
    )

    with open(
        transcript_file,
        "r",
        encoding="utf-8"
    ) as file:
        data = json.load(file)

    translator = GoogleTranslator(
        source="ne",
        target="en"
    )

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    subtitle_index = 1

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:

        for segment in data.get(
            "segments",
            []
        ):
            start = segment.get(
                "start",
                0
            )
            end = segment.get(
                "end",
                0
            )

            nepali = str(
                segment.get(
                    "nepali",
                    ""
                )
            ).strip()

            if not nepali:
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
                f"{format_srt_time(start)} "
                f"--> "
                f"{format_srt_time(end)}\n"
            )

            file.write(
                f"{english}\n\n"
            )

            subtitle_index += 1

            # Avoid sending requests too quickly.
            time.sleep(0.15)

    print("")
    print(
        f"English subtitles created: "
        f"{output_file}"
    )
    print(
        f"Subtitle entries: "
        f"{subtitle_index - 1}"
    )


def find_transcript_for_story(
    story,
    default_dir
):
    if not story:
        return None

    transcript = story.get(
        "transcript"
    )

    if transcript:
        path = Path(transcript)

        if path.exists():
            return path

    video = story.get(
        "video"
    )

    if video:
        video_path = Path(video)

        candidate = (
            Path(default_dir)
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
    selection_path = Path(
        selection_file
    )
    output_path = Path(
        output_dir
    )

    output_path.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        selection_path,
        "r",
        encoding="utf-8"
    ) as file:
        selection = json.load(file)

    long_story = selection.get(
        "long_video"
    )

    short_story = selection.get(
        "short_video"
    )

    print("")
    print("====================================")
    print("SELECTED STORY TRANSLATION")
    print("====================================")

    # ----------------------------------------
    # LONG
    # ----------------------------------------

    if long_story:
        long_transcript = (
            find_transcript_for_story(
                long_story,
                transcript_dir
            )
        )

        if not long_transcript:
            raise RuntimeError(
                "Long story transcript "
                "could not be found."
            )

        print("")
        print("LONG VIDEO")
        print("------------------------------------")
        print(
            f"Transcript: "
            f"{long_transcript}"
        )

        translate_transcript(
            long_transcript,
            output_path
            / "long_subtitles.srt"
        )

    # ----------------------------------------
    # SHORT
    # ----------------------------------------

    if short_story:
        short_transcript = (
            find_transcript_for_story(
                short_story,
                transcript_dir
            )
        )

        if not short_transcript:
            raise RuntimeError(
                "Short story transcript "
                "could not be found."
            )

        print("")
        print("SHORT / REEL")
        print("------------------------------------")
        print(
            f"Transcript: "
            f"{short_transcript}"
        )

        translate_transcript(
            short_transcript,
            output_path
            / "short_subtitles.srt"
        )

    print("")
    print("====================================")
    print("TRANSLATION COMPLETE")
    print("====================================")


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

    selection_file = sys.argv[1]
    transcript_dir = sys.argv[2]
    output_dir = sys.argv[3]

    translate_selected_stories(
        selection_file,
        transcript_dir,
        output_dir
    )
