import json
import subprocess
import sys
from pathlib import Path


PLATFORMS = {
    "youtube": {
        "width": 1920,
        "height": 1080,
    },
    "youtube_shorts": {
        "width": 1080,
        "height": 1920,
    },
    "facebook": {
        "width": 1080,
        "height": 1920,
    },
    "instagram": {
        "width": 1080,
        "height": 1920,
    },
    "tiktok": {
        "width": 1080,
        "height": 1920,
    },
}


def run_command(command):
    print("")
    print("Running:")
    print(" ".join(command))
    print("")

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with code "
            f"{result.returncode}"
        )


def load_analysis(path):
    analysis_file = Path(path)

    if not analysis_file.exists():
        raise FileNotFoundError(
            f"Analysis file not found: "
            f"{analysis_file}"
        )

    with open(
        analysis_file,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def seconds_to_srt_time(seconds):
    seconds = max(
        0,
        float(seconds)
    )

    hours = int(seconds // 3600)

    minutes = int(
        (seconds % 3600) // 60
    )

    secs = int(seconds % 60)

    millis = int(
        round(
            (seconds - int(seconds))
            * 1000
        )
    )

    if millis >= 1000:
        secs += 1
        millis = 0

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d},"
        f"{millis:03d}"
    )


def srt_time_to_seconds(value):
    value = value.strip()

    time_part, millis = value.split(",")

    hours, minutes, seconds = map(
        int,
        time_part.split(":")
    )

    return (
        hours * 3600
        + minutes * 60
        + seconds
        + int(millis) / 1000
    )


def load_subtitles():
    possible_files = [
        Path(
            "data/test_video_subtitles.srt"
        ),
        Path(
            "data/subtitles.srt"
        ),
    ]

    for subtitle_file in possible_files:
        if subtitle_file.exists():
            print(
                f"Using subtitles: "
                f"{subtitle_file}"
            )
            return subtitle_file

    print(
        "No subtitle file found."
    )

    return None


def make_clip_subtitles(
    subtitle_file,
    clip_start,
    clip_end,
    output_file,
):
    if not subtitle_file:
        return False

    with open(
        subtitle_file,
        "r",
        encoding="utf-8",
    ) as file:
        content = file.read()

    blocks = content.split(
        "\n\n"
    )

    output_blocks = []

    index = 1

    for block in blocks:
        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip()
        ]

        if len(lines) < 3:
            continue

        try:
            times = lines[1]

            start_text, end_text = (
                times.split("-->")
            )

            start = srt_time_to_seconds(
                start_text
            )

            end = srt_time_to_seconds(
                end_text
            )

        except Exception:
            continue

        if end <= clip_start:
            continue

        if start >= clip_end:
            continue

        new_start = max(
            start,
            clip_start
        ) - clip_start

        new_end = min(
            end,
            clip_end
        ) - clip_start

        if new_end <= new_start:
            continue

        text = "\n".join(
            lines[2:]
        )

        output_blocks.append(
            (
                index,
                new_start,
                new_end,
                text
            )
        )

        index += 1

    if not output_blocks:
        return False

    with open(
        output_file,
        "w",
        encoding="utf-8",
    ) as file:

        for (
            index,
            start,
            end,
            text
        ) in output_blocks:

            file.write(
                f"{index}\n"
            )

            file.write(
                f"{seconds_to_srt_time(start)}"
                f" --> "
                f"{seconds_to_srt_time(end)}\n"
            )

            file.write(
                f"{text}\n\n"
            )

    print(
        f"Created clip subtitles: "
        f"{output_file}"
    )

    return True


def escape_subtitle_path(path):
    value = str(
        path.resolve()
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
    video_file,
    analysis_file,
    output_dir,
    platform,
    content_number,
):
    if platform not in PLATFORMS:
        raise ValueError(
            f"Unsupported platform: "
            f"{platform}"
        )

    if content_number == 1:
        content_type = "long_video"

    elif content_number == 2:
        content_type = "short_video"

    else:
        raise ValueError(
            "Content number must be "
            "1 or 2."
        )

    video_path = Path(
        video_file
    )

    output = Path(
        output_dir
    )

    output.mkdir(
        parents=True,
        exist_ok=True
    )

    if not video_path.exists():
        raise FileNotFoundError(
            f"Video not found: "
            f"{video_path}"
        )

    analysis = load_analysis(
        analysis_file
    )

    selected = analysis.get(
        content_type
    )

    print("")
    print(
        "===================================="
    )
    print(
        f"Creating {content_type}"
    )
    print(
        f"Platform: {platform}"
    )
    print(
        "===================================="
    )

    if not selected:
        print("")
        print(
            f"No {content_type} was selected."
        )
        print(
            "Skipping clip creation."
        )
        print("")
        return None

    start = float(
        selected["start"]
    )

    end = float(
        selected["end"]
    )

    if end <= start:
        raise RuntimeError(
            "Invalid clip timing."
        )

    duration = end - start

    settings = PLATFORMS[
        platform
    ]

    width = settings["width"]
    height = settings["height"]

    subtitle_source = load_subtitles()

    clip_subtitle = (
        output
        / f"{content_type}_subtitles.srt"
    )

    has_subtitles = make_clip_subtitles(
        subtitle_source,
        start,
        end,
        clip_subtitle,
    )

    safe_platform = platform.replace(
        "_",
        "-"
    )

    output_file = (
        output
        / f"{safe_platform}_{content_type}.mp4"
    )

    # ------------------------------------------------
    # VIDEO FORMAT
    # ------------------------------------------------

    if platform == "youtube":

        video_filter = (
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:"
            "(ow-iw)/2:"
            "(oh-ih)/2,"
            "setsar=1"
        )

    else:

        video_filter = (
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            "setsar=1"
        )

    # ------------------------------------------------
    # BRANDING
    # ------------------------------------------------

    drawtext = (
        "drawtext="
        "fontfile=/usr/share/fonts/truetype/"
        "dejavu/DejaVuSans-Bold.ttf:"
        "text='PARLIAMENT PULSE NEPAL TV':"
        "fontcolor=white:"
        "fontsize=34:"
        "box=1:"
        "boxcolor=black@0.65:"
        "boxborderw=12:"
        "x=40:"
        "y=h-105"
    )

    engagement = (
        "drawtext="
        "fontfile=/usr/share/fonts/truetype/"
        "dejavu/DejaVuSans-Bold.ttf:"
        "text='LIKE  |  COMMENT  |  SHARE':"
        "fontcolor=white:"
        "fontsize=28:"
        "box=1:"
        "boxcolor=black@0.55:"
        "boxborderw=8:"
        "x=40:"
        "y=h-55"
    )

    video_filter += (
        ","
        + drawtext
        + ","
        + engagement
    )

    # ------------------------------------------------
    # SUBTITLES
    # ------------------------------------------------

    if has_subtitles:

        subtitle_path = (
            escape_subtitle_path(
                clip_subtitle
            )
        )

        video_filter += (
            ",subtitles="
            f"'{subtitle_path}'"
            ":force_style="
            "'FontName=DejaVu Sans,"
            "FontSize=22,"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "Outline=2,"
            "Shadow=1,"
            "Alignment=2,"
            "MarginV=70'"
        )

    # ------------------------------------------------
    # LOGO
    # ------------------------------------------------

    logo_file = Path(
        "assets/logo.png"
    )

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start),
        "-i",
        str(video_path),
        "-t",
        str(duration),
    ]

    if logo_file.exists():

        command.extend(
            [
                "-i",
                str(logo_file),
            ]
        )

        filter_complex = (
            f"[0:v]{video_filter}[base];"
            "[1:v]"
            "scale=260:-1[logo];"
            "[base][logo]"
            "overlay=40:35"
            "[v]"
        )

        command.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                "[v]",
                "-map",
                "0:a?",
            ]
        )

    else:

        print(
            "Warning: "
            "assets/logo.png not found."
        )

        command.extend(
            [
                "-vf",
                video_filter,
                "-map",
                "0:v",
                "-map",
                "0:a?",
            ]
        )

    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_file),
        ]
    )

    run_command(
        command
    )

    if not output_file.exists():
        raise RuntimeError(
            "Output video was not created."
        )

    size = output_file.stat().st_size

    if size < 10000:
        raise RuntimeError(
            "Output video is unexpectedly small."
        )

    print("")
    print(
        "CLIP CREATED SUCCESSFULLY"
    )
    print(
        f"Type: {content_type}"
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
        f"Output: {output_file}"
    )
    print(
        f"Size: {size / (1024 * 1024):.2f} MB"
    )

    return output_file


if __name__ == "__main__":

    if len(sys.argv) != 6:

        print("Usage:")
        print(
            "python clip.py "
            "<video> "
            "<analysis_json> "
            "<output_dir> "
            "<platform> "
            "<content_number>"
        )

        print("")
        print(
            "content_number:"
        )
        print(
            "1 = long_video"
        )
        print(
            "2 = short_video"
        )

        sys.exit(1)

    video_file = sys.argv[1]
    analysis_file = sys.argv[2]
    output_dir = sys.argv[3]
    platform = sys.argv[4]
    content_number = int(
        sys.argv[5]
    )

    create_clip(
        video_file,
        analysis_file,
        output_dir,
        platform,
        content_number,
    )
