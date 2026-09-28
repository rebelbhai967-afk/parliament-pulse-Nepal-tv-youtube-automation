import subprocess
import sys
from pathlib import Path


def run(command):
    print("Running:", " ".join(command))
    result = subprocess.run(command, text=True)
    if result.returncode != 0:
        raise RuntimeError("FFmpeg thumbnail generation failed.")


def split_text(text, width=34):
    words = str(text or "").split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "\n".join(lines[:3])


def make_thumbnail(video, title, output, start, vertical=False):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    text_file = output.with_suffix(".txt")
    text_file.write_text(split_text(title), encoding="utf-8")

    font_result = subprocess.run(
        ["bash", "-lc", "fc-match -f '%{file}' 'Noto Sans Devanagari:style=Bold' | head -n 1"],
        capture_output=True,
        text=True,
    )
    font = font_result.stdout.strip()
    if not font:
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    escaped_font = font.replace("\\", "\\\\").replace(":", "\\:")
    escaped_text = str(text_file).replace("\\", "\\\\").replace(":", "\\:")

    if vertical:
        size = "1080:1920"
        box_y = "h-520"
        text_y = "h-490"
        font_size = 54
    else:
        size = "1280:720"
        box_y = "h-250"
        text_y = "h-220"
        font_size = 44

    vf = (
        f"scale={size}:force_original_aspect_ratio=increase,"
        f"crop={size},"
        f"drawtext=fontfile='{escaped_font}':"
        f"textfile='{escaped_text}':"
        f"fontsize={font_size}:"
        f"fontcolor=white:"
        f"borderw=3:"
        f"bordercolor=black:"
        f"x=(w-text_w)/2:"
        f"y={text_y}:"
        f"line_spacing=10"
    )

    run([
        "ffmpeg", "-y",
        "-ss", str(max(0, float(start))),
        "-i", str(video),
        "-frames:v", "1",
        "-vf", vf,
        "-q:v", "2",
        str(output),
    ])

    if not output.exists() or output.stat().st_size < 5000:
        raise RuntimeError(f"Thumbnail was not created correctly: {output}")

    text_file.unlink(missing_ok=True)
    print(f"Created thumbnail: {output}")


def main():
    if len(sys.argv) != 7:
        print(
            "Usage: python src/thumbnail.py "
            "<video> <title> <start> <long_output> <short_output> <vertical>"
        )
        sys.exit(1)

    video = sys.argv[1]
    title = sys.argv[2]
    start = float(sys.argv[3])
    long_output = sys.argv[4]
    short_output = sys.argv[5]
    vertical = sys.argv[6].lower() == "true"

    make_thumbnail(video, title, long_output, start, False)
    make_thumbnail(video, title, short_output, start, True)


if __name__ == "__main__":
    main()
