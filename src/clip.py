import json
import subprocess
import sys
from pathlib import Path


SUPPORTED_PLATFORMS = {
    "youtube": {
        "width": 1920,
        "height": 1080,
        "cta": "Subscribe",
    },
    "youtube_shorts": {
        "width": 1080,
        "height": 1920,
        "cta": "Subscribe",
    },
    "facebook": {
        "width": 1080,
        "height": 1920,
        "cta": "Follow",
    },
    "instagram": {
        "width": 1080,
        "height": 1920,
        "cta": "Follow",
    },
    "tiktok": {
        "width": 1080,
        "height": 1920,
        "cta": "Follow",
    },
}


def run_command(command):
    print("")
    print("Running:")
    print(" ".join(str(item) for item in command))

    subprocess.run(
        command,
        check=True
    )


def get_candidates(analysis_path):
    with open(
        analysis_path,
        "r",
        encoding="utf-8"
    ) as file:
        analysis = json.load(file)

    candidates = analysis.get(
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
    logo_path=None
):
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(
            f"Unsupported platform: {platform}"
        )

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

    output.mkdir(
        parents=True,
        exist_ok=True
    )

    candidates = get_candidates(
        analysis
    )

    if candidate_number < 1:
        raise ValueError(
            "candidate_number must be >= 1"
        )

    if candidate_number > len(candidates):
        raise ValueError(
            f"Candidate {candidate_number} "
            f"does not exist. "
            f"Available: {len(candidates)}"
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

    settings = SUPPORTED_PLATFORMS[
        platform
    ]

    width = settings["width"]
    height = settings["height"]
    cta = settings["cta"]

    filename = (
        f"clip_{candidate_number:02d}_"
        f"{platform}.mp4"
    )

    output_file = output / filename

    filters = []

    # Scale and crop video to platform format.
    filters.append(
        "scale="
        f"{width}:{height}:"
        "force_original_aspect_ratio=increase"
    )

    filters.append(
        f"crop={width}:{height}"
    )

    # Add logo if available.
    if logo_path:
        logo = Path(logo_path)

        if logo.exists():
            print(
                f"Using logo: {logo}"
            )

            filter_complex = (
                f"[0:v]"
                f"scale={width}:{height}:"
                "force_original_aspect_ratio=increase,"
                f"crop={width}:{height}"
                "[base];"
                f"movie={logo}"
                f",scale=220:-1"
                "[logo];"
                "[base][logo]"
                "overlay="
                f"W-w-40:40"
                "[video]"
            )

            command = [
                "ffmpeg",
                "-y",
                "-ss",
                str(start),
                "-i",
                str(video),
                "-t",
                str(duration),
                "-filter_complex",
                filter_complex,
                "-map",
                "[video]",
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

            run_command(command)

            print("")
            print(
                f"Created: {output_file}"
            )
            print(
                f"Platform: {platform}"
            )
            print(
                f"CTA: {cta}"
            )

            return output_file

    # Fallback without logo.
    video_filter = ",".join(filters)

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start),
        "-i",
        str(video),
        "-t",
        str(duration),
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

    run_command(command)

    print("")
    print(
        f"Created: {output_file}"
    )
    print(
        f"Platform: {platform}"
    )
    print(
        f"CTA: {cta}"
    )

    return output_file


if __name__ == "__main__":

    if len(sys.argv) not in [5, 6]:
        print(
            "Usage:"
        )
        print(
            "python clip.py "
            "<video> "
            "<analysis_json> "
            "<output_dir> "
            "<platform> "
            "[candidate_number]"
        )
        print("")
        print(
            "Platforms:"
        )

        for platform in SUPPORTED_PLATFORMS:
            print(
                f"  - {platform}"
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

    logo = Path(
        "assets/logo.png"
    )

    logo_path = (
        str(logo)
        if logo.exists()
        else None
    )

    create_clip(
        video_path=video_path,
        analysis_path=analysis_path,
        output_dir=output_dir,
        platform=platform,
        candidate_number=candidate_number,
        logo_path=logo_path
    )
