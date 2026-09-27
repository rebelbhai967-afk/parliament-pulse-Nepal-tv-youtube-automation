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
    print("Running:")
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


def parse_srt_time(value):
    match = re.match(
        r"(\d+):(\d+):(\d+),(\d+)",
        value.strip()
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


def format_srt_time(seconds):
    seconds = max(
        0,
        float(seconds)
    )

    hours = int(
        seconds // 3600
    )

    minutes = int(
        (seconds % 3600) // 60
    )

    secs = int(
        seconds % 60
    )

    milliseconds = int(
        round(
            (seconds - int(seconds))
            * 1000
        )
    )

    if milliseconds >= 1000:
        secs += 1
        milliseconds = 0

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d},"
        f"{milliseconds:03d}"
    )


def create_clip_srt(
    source_srt,
    output_srt,
    clip_start,
    clip_end
):
    source = Path(source_srt)

    if not source.exists():
        return False

    text = source.read_text(
        encoding="utf-8"
    )

    blocks = re.split(
        r"\n\s*\n",
        text.strip()
    )

    output_blocks = []
    subtitle_number = 1

    for block in blocks:

        lines = block.splitlines()

        if len(lines) < 3:
            continue

        timing_line = None

        for line in lines:
            if "-->" in line:
                timing_line = line
                break

        if not timing_line:
            continue

        parts = timing_line.split(
            "-->"
        )

        if len(parts) != 2:
            continue

        start = parse_srt_time(
            parts[0]
        )

        end = parse_srt_time(
            parts[1]
        )

        subtitle_text = []

        timing_found = False

        for line in lines:
            if "-->" in line:
                timing_found = True
                continue

            if not timing_found:
                continue

            if line.strip().isdigit():
                continue

            if line.strip():
                subtitle_text.append(
                    line.strip()
                )

        if not subtitle_text:
            continue

        # Ignore subtitles completely outside
        # the selected clip.
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

        output_blocks.append(
            "\n".join([
                str(subtitle_number),
                (
                    f"{format_srt_time(new_start)}"
                    f" --> "
                    f"{format_srt_time(new_end)}"
                ),
                "\n".join(subtitle_text),
            ])
        )

        subtitle_number += 1

    if not output_blocks:
        return False

    output = Path(output_srt)

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output.write_text(
        "\n\n".join(output_blocks)
        + "\n",
        encoding="utf-8"
    )

    return True


def subtitle_filter(subtitle_path):
    path = str(
        Path(subtitle_path).resolve()
    )

    path = path.replace(
        "\\",
        "/"
    )

    path = path.replace(
        ":",
        "\\:"
    )

    path = path.replace(
        "'",
        "\\'"
    )

    return (
        f"subtitles='{path}':"
        "force_style="
        "'FontName=DejaVu Sans,"
        "FontSize=20,"
        "Bold=1,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BorderStyle=1,"
        "Outline=3,"
        "Shadow=1,"
        "Alignment=2,"
        "MarginV=150'"
    )


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

    clip_start = float(
        candidate["start"]
    )

    clip_end = float(
        candidate["end"]
    )

    duration = (
        clip_end - clip_start
    )

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

    # Search for generated English subtitles.
    subtitle_candidates = [
        Path("data/test_video_subtitles.srt"),
        Path("data/subtitles.srt"),
    ]

    source_srt = None

    for item in subtitle_candidates:
        if item.exists():
            source_srt = item
            break

    clip_srt = (
        output
        / f"clip_{candidate_number:02d}_subtitles.srt"
    )

    subtitles_available = False

    if source_srt:
        subtitles_available = create_clip_srt(
            source_srt,
            clip_srt,
            clip_start,
            clip_end
        )

    if vertical:

        base_filter = (
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )

        # Branding area.
        brand_x = 35
        brand_y = 35

        brand_text_y = 245

        cta_y = height - 100

    else:

        base_filter = (
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:"
            "(ow-iw)/2:(oh-ih)/2"
        )

        brand_x = 55
        brand_y = 45

        brand_text_y = 255

        cta_y = height - 95

    filters = []

    filters.append(
        base_filter
    )

    # Cover the original Parliament logo
    # in its known top-left region.
    if not vertical:

        filters.append(
            "drawbox="
            "x=55:"
            "y=40:"
            "w=285:"
            "h=245:"
            "color=white@0.92:"
            "t=fill"
        )

    # Small PPN TV branding text.
    filters.append(
        "drawtext="
        "fontcolor=black:"
        "fontsize=25:"
        "fontweight=bold:"
        "text='PARLIAMENT PULSE NEPAL TV':"
        f"x={brand_x}:"
        f"y={brand_text_y}"
    )

    # Bottom engagement bar.
    filters.append(
        "drawtext="
        "fontcolor=white:"
        "fontsize=28:"
        "fontweight=bold:"
        "text='LIKE  |  COMMENT  |  SHARE':"
        "x=(w-text_w)/2:"
        f"y={cta_y}:"
        "box=1:"
        "boxcolor=black@0.68:"
        "boxborderw=14"
    )

    # English subtitles.
    if subtitles_available:

        filters.append(
            subtitle_filter(
                clip_srt
            )
        )

    video_filter = ",".join(
        filters
    )

    filename = (
        f"clip_{candidate_number:02d}_"
        f"{platform}.mp4"
    )

    output_file = (
        output / filename
    )

    if logo.exists():

        print(
            f"Using PPN logo: {logo}"
        )

        filter_complex = (
            f"[0:v]"
            f"{video_filter}"
            "[base];"

            f"[1:v]"
            "scale=190:-1"
            "[logo];"

            "[base][logo]"
            f"overlay={brand_x}:"
            f"{brand_y}"
            "[final]"
        )

        command = [
            "ffmpeg",
            "-y",

            "-ss",
            str(clip_start),

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
            "22",

            "-c:a",
            "aac",

            "-b:a",
            "128k",

            "-movflags",
            "+faststart",

            str(output_file),
        ]

    else:

        print(
            "WARNING:"
        )
        print(
            "assets/logo.png not found."
        )

        command = [
            "ffmpeg",
            "-y",

            "-ss",
            str(clip_start),

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
            "22",

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
        "================================"
    )
    print(
        "PARLIAMENT PULSE CLIP CREATED"
    )
    print(
        "================================"
    )
    print(
        f"Platform   : {platform}"
    )
    print(
        f"Start      : {clip_start}s"
    )
    print(
        f"End        : {clip_end}s"
    )
    print(
        f"Duration   : {duration:.2f}s"
    )
    print(
        f"CTA        : {cta}"
    )
    print(
        f"Logo       : {logo.exists()}"
    )
    print(
        f"Subtitles  : {subtitles_available}"
    )
    print(
        f"Output     : {output_file}"
    )
    print(
        "================================"
    )

    return output_file


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

        print("")
        print("Platforms:")

        for platform in PLATFORMS:
            print(
                f"  {platform}"
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
        video_path=video_path,
        analysis_path=analysis_path,
        output_dir=output_dir,
        platform=platform,
        candidate_number=candidate_number
    )
