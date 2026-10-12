import json
import re
import subprocess
import sys
from pathlib import Path


TIMESTAMP = re.compile(r"^(\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2},\d{3})(.*)$")


def run(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError("Video render command failed.")


def to_seconds(value):
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0


def to_timestamp(seconds):
    millis = max(0, int(round(seconds * 1000)))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    whole_seconds, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{millis:03d}"


def make_segment_subtitles(source_srt, target_srt, source_start, duration):
    """Clip source-timeline SRT cues to a rendered segment and rebase them to t=0."""
    if not source_srt.exists():
        return False
    raw = source_srt.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\n\s*\n", raw.strip())
    rendered = []
    segment_end = source_start + duration
    for block in blocks:
        lines = block.splitlines()
        time_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_index is None:
            continue
        match = TIMESTAMP.match(lines[time_index].strip())
        if not match:
            continue
        cue_start = to_seconds(match.group(1))
        cue_end = to_seconds(match.group(2))
        clipped_start = max(cue_start, source_start)
        clipped_end = min(cue_end, segment_end)
        if clipped_end <= clipped_start:
            continue
        text_lines = lines[time_index + 1:]
        if not text_lines:
            continue
        start_local = clipped_start - source_start
        end_local = clipped_end - source_start
        rendered.append(
            f"{len(rendered) + 1}\n{to_timestamp(start_local)} --> {to_timestamp(end_local)}\n"
            + "\n".join(text_lines)
        )
    if not rendered:
        return False
    target_srt.write_text("\n\n".join(rendered) + "\n", encoding="utf-8")
    return True


def ffmpeg_filter_path(path):
    # libass filter options need colons and apostrophes escaped; paths are
    # absolute so a relative path containing punctuation cannot be misread.
    return str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def render_segment(piece, subtitle_dir, output, kind, start, duration):
    source = Path(piece["video"])
    source_srt = Path(subtitle_dir) / f"{source.stem}.srt"
    output.parent.mkdir(parents=True, exist_ok=True)
    local_srt = output.with_suffix(".segment.srt")
    has_local_subtitles = make_segment_subtitles(source_srt, local_srt, start, duration)
    command = ["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(duration)]
    filters = []
    if kind == "short":
        # Keep the complete original 16:9 frame visible over a blurred background.
        filters += [
            "split=2[bg][fg]",
            "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=18:8[bg]",
            "[fg]scale=1080:-2[fg]",
            "[bg][fg]overlay=0:(H-h)/2"
        ]
    else:
        filters += ["scale=1920:1080:force_original_aspect_ratio=decrease", "pad=1920:1080:(ow-iw)/2:(oh-ih)/2"]
    if has_local_subtitles:
        filters.append(
            f"subtitles='{ffmpeg_filter_path(local_srt)}':force_style="
            "'FontName=DejaVu Sans,FontSize=14,Outline=1,Shadow=0,Alignment=2,MarginV=90,WrapStyle=2'"
        )
    command += ["-vf", ",".join(filters), "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-c:a", "aac", "-b:a", "128k", str(output)]
    try:
        run(command)
    finally:
        if local_srt.exists():
            local_srt.unlink()


def concat_two(first, second, output):
    listing = output.parent / f"{output.stem}_concat.txt"
    listing.write_text(f"file '{first.resolve()}'\nfile '{second.resolve()}'\n", encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(output)])


def render_piece(piece, subtitle_dir, output, kind):
    start = float(piece["start"])
    end = float(piece["end"])
    if end <= start:
        raise ValueError("Invalid story piece duration.")

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
