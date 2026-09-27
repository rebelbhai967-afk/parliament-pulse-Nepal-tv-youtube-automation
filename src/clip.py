import json
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


def run(command):
    print("")
    print("Running FFmpeg...")
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


def create_clip(
    video_path,
    analysis_path,
    output_dir,
    platform,
    candidate_number=1,
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

    if candidate_number > len(candidates):
        raise ValueError(
            f"Candidate {candidate_number} "
            f"does not exist."
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

    output.mkdir(
        parents=True,
        exist_ok=True
    )

    logo = Path(
        "assets/logo.png"
    )

    logo_exists = logo.exists()

    output_file = (
        output
        / f"clip_{candidate_number:02d}_{platform}.mp4"
    )

    # Base video.
    if settings["vertical"]:
        base_filter = (
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )
    else:
        base_filter = (
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
        )

    # Branding text.
    draw_brand = (
        "drawtext="
        "fontcolor=white:"
        "fontsize=34:"
        "fontweight=bold:"
        "text='PARLIAMENT PULSE NEPAL TV':"
        "x=40:"
        "y=40:"
        "box=1:"
        "boxcolor=black@0.55:"
        "boxborderw=12"
    )

    # Engagement CTA.
    draw_cta = (
        "drawtext="
        "fontcolor=white:"
        "fontsize=30:"
        f"text='LIKE  |  COMMENT  |  SHARE  |  {cta}':"
        "x=(w-text_w)/2:"
        "y=h-90:"
        "box=1:"
        "boxcolor=black@0.65:"
        "boxborderw=14"
    )

    video_filter = (
        f"{base_filter},"
        f"{draw_brand},"
        f"{draw_cta}"
    )

    if logo_exists:

        print(
            f"Logo found: {logo}"
        )

        filter_complex = (
            f"[0:v]{video_filter}[base];"
            f"[1:v]"
            "scale=220:-1"
            "[logo];"
            "[base][logo]"
            "overlay=W-w-35:35"
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
            "WARNING: assets/logo.png not found."
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

    run(command)

    print("")
    print("================================")
    print("CLIP CREATED")
    print("================================")
    print(f"Platform : {platform}")
    print(f"Start    : {start}s")
    print(f"End      : {end}s")
    print(f"CTA      : {cta}")
    print(f"Logo     : {logo_exists}")
    print(f"Output   : {output_file}")
    print("================================")

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

        for name in PLATFORMS:
            print(
                f"  {name}"
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
        candidate_number=candidate_number,
    )
