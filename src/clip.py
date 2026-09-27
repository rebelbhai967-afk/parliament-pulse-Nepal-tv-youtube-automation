import json
import re
import subprocess
import sys
from pathlib import Path


FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BRAND = "PARLIAMENT PULSE NEPAL TV"


def run_command(command):
    print("")
    print("Running:")
    print(" ".join(str(x) for x in command))
    print("")

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed with exit code {result.returncode}"
        )


def load_analysis(analysis_path):
    with open(
        analysis_path,
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)


def get_selected_story(analysis, content_number):
    if str(content_number) == "1":
        return analysis.get("long_video")

    if str(content_number) == "2":
        return analysis.get("short_video")

    raise ValueError(
        "content_number must be 1 (long) or 2 (short)"
    )


def get_source_video(story, default_video):
    if not story:
        return None

    video = story.get("video")

    if video:
        video_path = Path(video)

        if video_path.exists():
            return video_path

    return Path(default_video)


def get_story_times(story):
    if not story:
        return None, None

    start = story.get("start")
    end = story.get("end")

    if start is None or end is None:
        return None, None

    start = float(start)
    end = float(end)

    if end <= start:
        return None, None

    return start, end


def format_srt_time(seconds):
    seconds = max(0, float(seconds))

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    millis = int(
        round(
            (seconds - int(seconds)) * 1000
        )
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


def parse_srt_time(value):
    value = value.strip().replace(".", ",")

    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError(
            f"Invalid SRT timestamp: {value}"
        )

    hours = int(parts[0])
    minutes = int(parts[1])

    seconds_part = parts[2]
    seconds, millis = seconds_part.split(",")

    return (
        hours * 3600
        + minutes * 60
        + int(seconds)
        + int(millis) / 1000
    )


def parse_srt(srt_path):
    """
    Parse an SRT file into:
    [(start_seconds, end_seconds, text), ...]
    """

    path = Path(srt_path)

    with open(
        path,
        "r",
        encoding="utf-8-sig"
    ) as file:
        content = file.read()

    blocks = re.split(
        r"\n\s*\n",
        content.strip()
    )

    subtitles = []

    for block in blocks:
        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip()
        ]

        if len(lines) < 3:
            continue

        timing_index = None

        for index, line in enumerate(lines):
            if "-->" in line:
                timing_index = index
                break

        if timing_index is None:
            continue

        start_text, end_text = [
            item.strip()
            for item in lines[timing_index].split("-->", 1)
        ]

        try:
            start = parse_srt_time(start_text)
            end = parse_srt_time(
                end_text.split(" ", 1)[0]
            )
        except ValueError:
            continue

        text = " ".join(
            lines[timing_index + 1:]
        ).strip()

        if not text or end <= start:
            continue

        subtitles.append(
            (start, end, text)
        )

    return subtitles


def create_story_subtitles_from_json(
    story,
    transcript_path,
    output_path
):
    """
    Create clip-relative subtitles from a transcript JSON.

    This is retained as a fallback for Nepali transcripts.
    """

    transcript_file = Path(transcript_path)
    output_file = Path(output_path)

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if not transcript_file.exists():
        print(
            f"Transcript not found: {transcript_file}"
        )
        return False

    with open(
        transcript_file,
        "r",
        encoding="utf-8"
    ) as file:
        transcript = json.load(file)

    clip_start, clip_end = get_story_times(story)

    if clip_start is None:
        return False

    subtitles = []

    for segment in transcript.get("segments", []):
        start = float(
            segment.get("start", 0)
        )
        end = float(
            segment.get("end", 0)
        )

        text = str(
            segment.get("english")
            or segment.get("nepali")
            or ""
        ).strip()

        if not text:
            continue

        if end <= clip_start:
            continue

        if start >= clip_end:
            continue

        subtitle_start = max(
            0,
            start - clip_start
        )

        subtitle_end = min(
            clip_end,
            end
        ) - clip_start

        if subtitle_end <= subtitle_start:
            continue

        subtitles.append(
            (
                subtitle_start,
                subtitle_end,
                text
            )
        )

    return write_srt(
        subtitles,
        output_file
    )


def create_story_subtitles_from_srt(
    story,
    srt_path,
    output_path
):
    """
    Take full-video translated SRT subtitles,
    keep only the selected story range, and shift
    timestamps so they start at 00:00 for the clip.
    """

    srt_file = Path(srt_path)
    output_file = Path(output_path)

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if not srt_file.exists():
        print(
            f"SRT not found: {srt_file}"
        )
        return False

    clip_start, clip_end = get_story_times(story)

    if clip_start is None:
        return False

    subtitles = []

    for start, end, text in parse_srt(
        srt_file
    ):
        if end <= clip_start:
            continue

        if start >= clip_end:
            continue

        subtitle_start = max(
            0,
            start - clip_start
        )

        subtitle_end = min(
            clip_end,
            end
        ) - clip_start

        if subtitle_end <= subtitle_start:
            continue

        subtitles.append(
            (
                subtitle_start,
                subtitle_end,
                text
            )
        )

    return write_srt(
        subtitles,
        output_file
    )


def write_srt(subtitles, output_file):
    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:
        for index, (
            start,
            end,
            text
        ) in enumerate(
            subtitles,
            start=1
        ):
            file.write(
                f"{index}\n"
            )

            file.write(
                f"{format_srt_time(start)} --> "
                f"{format_srt_time(end)}\n"
            )

            file.write(
                f"{text}\n\n"
            )

    print(
        f"Created subtitles: {output_file}"
    )

    print(
        f"Subtitle entries: {len(subtitles)}"
    )

    return True


def escape_drawtext(text):
    return (
        text
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def escape_filter_path(path):
    return (
        str(path)
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def create_clip(
    video_path,
    story,
    subtitle_path,
    output_path,
    platform,
    logo_path=None
):
    if not story:
        print(
            "Selected story does not exist. "
            "Skipping."
        )
        return False

    start, end = get_story_times(story)

    if start is None:
        print(
            "Invalid story timestamps. "
            "Skipping."
        )
        return False

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

    filters = []

    brand_text = escape_drawtext(BRAND)

    filters.append(
        "drawtext="
        f"fontfile={FONT}:"
        f"text='{brand_text}':"
        "fontsize=34:"
        "x=40:"
        "y=35:"
        "borderw=2:"
        "bordercolor=black:"
        "fontcolor=white"
    )

    if platform in {
        "youtube_shorts",
        "facebook_reels",
        "instagram_reels",
        "tiktok"
    }:
        filters.insert(
            0,
            "scale=1080:1920:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1920"
        )

    else:
        filters.insert(
            0,
            "scale=1920:1080:"
            "force_original_aspect_ratio=decrease,"
            "pad=1920:1080:"
            "(ow-iw)/2:"
            "(oh-ih)/2"
        )

    if subtitle_path:
        subtitle = Path(subtitle_path)

        if subtitle.exists():
            subtitle_file = escape_filter_path(
                subtitle
            )

            subtitle_filter = (
                "subtitles="
                f"'{subtitle_file}':"
                "force_style="
                "'FontName=DejaVu Sans,"
                "FontSize=22,"
                "PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H00000000,"
                "Outline=2,"
                "Shadow=1,"
                "Alignment=2,"
                "MarginV=120'"
            )

            filters.append(
                subtitle_filter
            )

    filters.append(
        "drawtext="
        f"fontfile={FONT}:"
        "text='LIKE | COMMENT | SHARE':"
        "fontsize=28:"
        "x=(w-text_w)/2:"
        "y=h-70:"
        "borderw=2:"
        "bordercolor=black:"
        "fontcolor=white"
    )

    if (
        logo_path
        and Path(logo_path).exists()
    ):
        logo = Path(logo_path)

        filter_complex = (
            "[1:v]"
            "scale=260:-1"
            "[logo];"
            "[0:v]"
            + ",".join(filters)
            + "[base];"
            "[base][logo]"
            "overlay=40:35"
            "[vout]"
        )

        command = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-t",
            str(end - start),
            "-i",
            str(video),
            "-i",
            str(logo),
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output)
        ]

    else:
        video_filter = ",".join(filters)

        command = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-t",
            str(end - start),
            "-i",
            str(video),
            "-vf",
            video_filter,
            "-map",
            "0:v",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output)
        ]

    run_command(command)

    if not output.exists():
        raise RuntimeError(
            f"Output was not created: {output}"
        )

    size = output.stat().st_size

    if size < 10000:
        raise RuntimeError(
            f"Output file is unexpectedly small: "
            f"{size} bytes"
        )

    print("")
    print("====================================")
    print("CLIP CREATED")
    print("====================================")
    print(f"Platform: {platform}")
    print(f"Video:    {video}")
    print(f"Start:    {start:.2f}")
    print(f"End:      {end:.2f}")
    print(f"Output:   {output}")
    print(
        f"Size:     "
        f"{size / (1024 * 1024):.2f} MB"
    )

    return True


def main():
    if len(sys.argv) < 7:
        print(
            "Usage:"
        )

        print(
            "python src/clip.py "
            "<default_video> "
            "<analysis_json> "
            "<output_dir> "
            "<platform> "
            "<content_number> "
            "<subtitle_source>"
        )

        sys.exit(1)

    default_video = sys.argv[1]
    analysis_path = sys.argv[2]
    output_dir = Path(sys.argv[3])
    platform = sys.argv[4]
    content_number = sys.argv[5]
    subtitle_source = Path(sys.argv[6])

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    analysis = load_analysis(
        analysis_path
    )

    story = get_selected_story(
        analysis,
        content_number
    )

    if not story:
        print(
            "No selected story found. "
            "Skipping clip creation."
        )
        return

    selected_video = get_source_video(
        story,
        default_video
    )

    if not selected_video.exists():
        raise FileNotFoundError(
            f"Selected video not found: "
            f"{selected_video}"
        )

    subtitle_path = (
        output_dir
        / "story_subtitles.srt"
    )

    if subtitle_source.suffix.lower() == ".srt":
        create_story_subtitles_from_srt(
            story,
            subtitle_source,
            subtitle_path
        )
    else:
        create_story_subtitles_from_json(
            story,
            subtitle_source,
            subtitle_path
        )

    logo_path = Path(
        "assets/logo.png"
    )

    platform_names = {
        "youtube": "youtube_long.mp4",
        "youtube_shorts": "youtube_short.mp4",
        "facebook": "facebook_long.mp4",
        "facebook_reels": "facebook_reel.mp4",
        "instagram": "instagram_long.mp4",
        "instagram_reels": "instagram_reel.mp4",
        "tiktok": "tiktok_long.mp4"
    }

    filename = platform_names.get(
        platform,
        f"{platform}.mp4"
    )

    output_file = (
        output_dir / filename
    )

    create_clip(
        selected_video,
        story,
        subtitle_path,
        output_file,
        platform,
        logo_path
    )


if __name__ == "__main__":
    main()
