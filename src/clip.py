import json
import re
import subprocess
import sys
from pathlib import Path


PLATFORMS = {
    "youtube": {
        "width": 1920,
        "height": 1080,
        "cta": "SUBSCRIBE",
        "vertical": False,
    },
    "youtube_shorts": {
        "width": 1080,
        "height": 1920,
        "cta": "SUBSCRIBE",
        "vertical": True,
    },
    "facebook": {
        "width": 1080,
        "height": 1920,
        "cta": "FOLLOW",
        "vertical": True,
    },
    "instagram": {
        "width": 1080,
        "height": 1920,
        "cta": "FOLLOW",
        "vertical": True,
    },
    "tiktok": {
        "width": 1080,
        "height": 1920,
        "cta": "FOLLOW",
        "vertical": True,
    },
}


def run_command(command):
    print("")
    print("Running FFmpeg:")
    print(" ".join(str(x) for x in command))
    print("")

    subprocess.run(
        command,
        check=True
    )


def load_analysis(path):
    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:
        data = json.load(file)

    candidates = data.get(
        "candidates",
        []
    )

    if not candidates:
        raise RuntimeError(
            "No clip candidates found."
        )

    return candidates


def srt_time_to_seconds(value):
    value = value.strip()

    match = re.match(
        r"(\d+):(\d+):(\d+),(\d+)",
        value
    )

    if not match:
        return 0.0

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    milliseconds = int(match.group(4))

    return (
        hours * 3600
        + minutes * 60
        + seconds
        + milliseconds / 1000
    )


def seconds_to_srt_time(seconds):
    seconds = max(
        0.0,
        float(seconds)
    )

    hours = int(
        seconds // 3600
    )

    minutes = int(
        (seconds % 3600) // 60
    )

    whole_seconds = int(
        seconds % 60
    )

    milliseconds = int(
        round(
            (seconds - int(seconds))
            * 1000
        )
    )

    if milliseconds >= 1000:
        whole_seconds += 1
        milliseconds = 0

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{whole_seconds:02d},"
        f"{milliseconds:03d}"
    )


def make_clip_subtitles(
    source_srt,
    output_srt,
    clip_start,
    clip_end
):
    source = Path(source_srt)

    if not source.exists():
        return False

    content = source.read_text(
        encoding="utf-8"
    )

    blocks = re.split(
        r"\n\s*\n",
        content.strip()
    )

    result = []
    number = 1

    for block in blocks:

        lines = block.splitlines()

        timing_index = None

        for i, line in enumerate(lines):
            if "-->" in line:
                timing_index = i
                break

        if timing_index is None:
            continue

        timing = lines[timing_index]

        parts = timing.split(
            "-->"
        )

        if len(parts) != 2:
            continue

        start = srt_time_to_seconds(
            parts[0]
        )

        end = srt_time_to_seconds(
            parts[1]
        )

        subtitle_lines = lines[
            timing_index + 1:
        ]

        subtitle_text = "\n".join(
            line.strip()
            for line in subtitle_lines
            if line.strip()
            and not line.strip().isdigit()
        )

        if not subtitle_text:
            continue

        if end <= clip_start:
            continue

        if start >= clip_end:
            continue

        new_start = max(
            0,
            start - clip_start
        )

        new_end = min(
            clip_end - clip_start,
            end - clip_start
        )

        if new_end <= new_start:
            continue

        result.append(
            "\n".join([
                str(number),
                (
                    seconds_to_srt_time(
                        new_start
                    )
                    + " --> "
                    + seconds_to_srt_time(
                        new_end
                    )
                ),
                subtitle_text,
            ])
        )

        number += 1

    if not result:
        return False

    output = Path(output_srt)

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output.write_text(
        "\n\n".join(result)
        + "\n",
        encoding="utf-8"
    )

    return True


def escape_subtitle_path(path):
    value = str(
        Path(path).resolve()
    )

    value = value.replace(
        "\\",
        "/"
    )

    value = value.replace(
        ":",
        "\\:"
    )

    value = value.replace(
        "'",
        "\\'"
    )

    return value


def create_clip(
    video_path,
    analysis_path,
    output_dir,
    platform,
    candidate_number=1
):
    video = Path(video_path)
    analysis = Path(analysis_path)
    output = Path(output_dir)

    if not video.exists():
        raise FileNotFoundError(
            f"Video not found: {video}"
        )

    if not analysis.exists():
        raise FileNotFoundError(
            f"Analysis not found: {analysis}"
        )

    if platform not in PLATFORMS:
        raise ValueError(
            f"Unsupported platform: {platform}"
        )

    candidates = load_analysis(
        analysis
    )

    if (
        candidate_number < 1
        or candidate_number > len(candidates)
    ):
        raise ValueError(
            f"Invalid candidate number: "
            f"{candidate_number}"
        )

    candidate = candidates[
        candidate_number - 1
    ]

    start = float(
        candidate["start"]
    )

    end = float(
        candidate["end"]
    )

    duration = end - start

    if duration <= 0:
        raise RuntimeError(
            "Invalid clip duration."
        )

    settings = PLATFORMS[
        platform
    ]

    width = settings["width"]
    height = settings["height"]
    cta = settings["cta"]
    vertical = settings["vertical"]

    output.mkdir(
        parents=True,
        exist_ok=True
    )

    logo = Path(
        "assets/logo.png"
    )

    # Find English subtitle file.
    subtitle_sources = [
        Path(
            "data/test_video_subtitles.srt"
        ),
        Path(
            "data/subtitles.srt"
        ),
    ]

    source_srt = None

    for subtitle in subtitle_sources:
        if subtitle.exists():
            source_srt = subtitle
            break

    clip_srt = (
        output
        / f"clip_{candidate_number:02d}_subtitles.srt"
    )

    subtitles_available = False

    if source_srt:
        subtitles_available = make_clip_subtitles(
            source_srt,
            clip_srt,
            start,
            end
        )

    filters = []

    # Video sizing.
    if vertical:
        filters.append(
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=increase"
        )

        filters.append(
            f"crop={width}:{height}"
        )

    else:
        filters.append(
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=decrease"
        )

        filters.append(
            f"pad={width}:{height}:"
            "(ow-iw)/2:(oh-ih)/2"
        )

    # Cover official logo area on YouTube 16:9.
    if not vertical:
        filters.append(
            "drawbox="
            "x=45:"
            "y=35:"
            "w=310:"
            "h=245:"
            "color=white@0.94:"
            "t=fill"
        )

    # PPN text.
    filters.append(
        "drawtext="
        "fontcolor=black:"
        "fontsize=25:"
        "text='PARLIAMENT PULSE NEPAL TV':"
        "x=40:"
        "y=245"
    )

    # Engagement bar.
    filters.append(
        "drawtext="
        "fontcolor=white:"
        "fontsize=27:"
        f"text='LIKE  |  COMMENT  |  SHARE  |  {cta}':"
        "x=(w-text_w)/2:"
        "y=h-75:"
        "box=1:"
        "boxcolor=black@0.70:"
        "boxborderw=12"
    )

    # English subtitles.
    if subtitles_available:
        subtitle_path = escape_subtitle_path(
            clip_srt
        )

        filters.append(
            f"subtitles='{subtitle_path}':"
            "force_style="
            "'FontName=DejaVu Sans,"
            "FontSize=18,"
            "Bold=1,"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "Outline=3,"
            "Shadow=1,"
            "Alignment=2,"
            "MarginV=125'"
        )

    video_filter = ",".join(
        filters
    )

    output_file = (
        output
        / (
            f"clip_{candidate_number:02d}_"
            f"{platform}.mp4"
        )
    )

    # With logo.
    if logo.exists():

        filter_complex = (
            f"[0:v]"
            f"{video_filter}"
            "[base];"
            "[1:v]"
            "scale=190:-1"
            "[logo];"
            "[base][logo]"
            "overlay=40:35"
            "[final]"
        )

        command = [
            "ffmpeg",
            "-y",

            "-ss",
            str(start),

            "-t",
            str(duration),

            "-i",
            str(video),

            "-i",
            str(logo),

            "-filter_complex",
            filter_complex,

            "-map",
            "[final]",

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
            "128k",

            "-movflags",
            "+faststart",

            str(output_file),
        ]

    else:

        command = [
            "ffmpeg",
            "-y",

            "-ss",
            str(start),

            "-t",
            str(duration),

            "-i",
            str(video),

            "-vf",
            video_filter,

            "-map",
            "0:v:0",

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
            "128k",

            "-movflags",
            "+faststart",

            str(output_file),
        ]

    run_command(
        command
    )

    print("")
    print(
        "=============================="
    )
    print(
        "CLIP CREATED SUCCESSFULLY"
    )
    print(
        "=============================="
    )
    print(
        f"Platform: {platform}"
    )
    print(
        f"Start: {start}s"
    )
    print(
        f"End: {end}s"
    )
    print(
        f"Duration: {duration:.2f}s"
    )
    print(
        f"Logo: {logo.exists()}"
    )
    print(
        f"English subtitles: "
        f"{subtitles_available}"
    )
    print(
        f"Output: {output_file}"
    )
    print(
        "=============================="
    )


if __name__ == "__main__":

    if len(sys.argv) not in [5, 6]:
        print(
            "Usage:"
        )
        print(
            "python src/clip.py "
            "<video> "
            "<analysis_json> "
            "<output_dir> "
            "<platform> "
            "[candidate_number]"
        )

        sys.exit(1)

    video_path = sys.argv[1]
    analysis_path = sys.argv[2]
    output_dir = sys.argv[3]
    platform = sys.argv[4]

    candidate_number = 1

    if len(sys.argv) == 6:
        candidate_number = int(
            sys.argv[5]
        )

    create_clip(
        video_path,
        analysis_path,
        output_dir,
        platform,
        candidate_number
    )
