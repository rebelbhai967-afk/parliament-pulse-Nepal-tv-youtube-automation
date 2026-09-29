import json
import subprocess
import sys
from pathlib import Path


def run(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError("Video render command failed.")


def render_piece(piece, subtitle_dir, output):
    start = float(piece["start"])
    duration = float(piece["end"]) - start
    if duration <= 0:
        raise ValueError("Invalid story piece duration.")

    source = Path(piece["video"])
    srt = Path(subtitle_dir) / f"{source.stem}.srt"
    output.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg", "-y", "-ss", str(start), "-i", str(source),
        "-t", str(duration),
    ]
    if srt.exists():
        command += ["-vf", f"subtitles={srt.resolve()}:force_style='FontName=DejaVu Sans,FontSize=22,Outline=2,Shadow=1,Alignment=2,MarginV=120'"]
    command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-c:a", "aac", "-b:a", "128k", str(output)]
    run(command)


def main(selection_path, subtitle_dir, output_dir):
    data = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    out = Path(output_dir)
    work = out / ".pieces"
    work.mkdir(parents=True, exist_ok=True)

    for kind, key in (("long", "long_stories"), ("short", "short_stories")):
        for index, story in enumerate(data.get(key, []), 1):
            for part, piece in enumerate(story.get("pieces", []), 1):
                render_piece(piece, subtitle_dir, work / f"{kind}_{index:02d}_{part:02d}.mp4")
            print(f"Prepared {kind} story {index}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python src/render_stories.py <selection_json> <subtitle_dir> <output_dir>")
    main(sys.argv[1], sys.argv[2], sys.argv[3])
