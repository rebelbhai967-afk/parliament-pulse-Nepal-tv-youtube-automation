import json
import subprocess
import sys
from pathlib import Path

def run(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError("Video render command failed.")

def render_segment(piece, subtitle_dir, output, kind, start, duration):
    source = Path(piece["video"])
    srt = Path(subtitle_dir) / f"{source.stem}.srt"
    output.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(duration)]
    filters = []
    if kind == "short":
        # Fill the vertical frame instead of letterboxing a 16:9 Parliament
        # recording with large black bars. Keep the central speaker area.
        filters += ["scale=-2:1920:force_original_aspect_ratio=increase", "crop=1080:1920:(iw-1080)/2:0"]
    else:
        filters += ["scale=1920:1080:force_original_aspect_ratio=decrease", "pad=1920:1080:(ow-iw)/2:(oh-ih)/2"]
    if srt.exists():
        filters.append(f"subtitles={srt.resolve()}:force_style='FontName=DejaVu Sans,FontSize=22,Outline=2,Shadow=1,Alignment=2,MarginV=120'")
    command += ["-vf", ",".join(filters), "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-c:a", "aac", "-b:a", "128k", str(output)]
    run(command)

def concat_two(first, second, output):
    listing = output.parent / f"{output.stem}_concat.txt"
    listing.write_text(f"file '{first.resolve()}'\nfile '{second.resolve()}'\n", encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(output)])

def render_piece(piece, subtitle_dir, output, kind):
    start = float(piece["start"])
    end = float(piece["end"])
    if end <= start:
        raise ValueError("Invalid story piece duration.")

    # Professional cold open: use original Parliament audio from the strongest
    # transcript-grounded moment, then continue from the exact point where the
    # cold open ends so the opening does not repeat.
    hook_start = float(piece.get("hook_start", start))
    hook_end = float(piece.get("hook_end", min(start + 8.0, end)))
    main_start = float(piece.get("main_start", hook_end))
    hook_duration = hook_end - hook_start
    main_duration = end - main_start
    output.parent.mkdir(parents=True, exist_ok=True)

    if hook_duration < 1.0 or main_duration < 1.0:
        render_segment(piece, subtitle_dir, output, kind, start, end - start)
        return

    hook_file = output.with_name(output.stem + "_hook.mp4")
    main_file = output.with_name(output.stem + "_main.mp4")
    render_segment(piece, subtitle_dir, hook_file, kind, hook_start, hook_duration)
    render_segment(piece, subtitle_dir, main_file, kind, main_start, main_duration)
    concat_two(hook_file, main_file, output)

def main(selection_path, subtitle_dir, output_dir):
    data = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    out = Path(output_dir)
    work = out / ".pieces"
    work.mkdir(parents=True, exist_ok=True)

    for kind, key in (("long", "long_stories"), ("short", "short_stories")):
        for index, story in enumerate(data.get(key, []), 1):
            for part, piece in enumerate(story.get("pieces", []), 1):
                render_piece(piece, subtitle_dir, work / f"{kind}_{index:02d}_{part:02d}.mp4", kind)
            print(f"Prepared {kind} story {index}")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python src/render_stories.py <selection_json> <subtitle_dir> <output_dir>")
    main(sys.argv[1], sys.argv[2], sys.argv[3])
