import json
import subprocess
import sys
from pathlib import Path


def run(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError("Assembly command failed.")


def assemble(story, index, kind, pieces_dir, output_dir):
    pieces = []
    for part, _piece in enumerate(story.get("pieces", []), 1):
        path = Path(pieces_dir) / f"{kind}_{index:02d}_{part:02d}.mp4"
        if not path.exists():
            raise FileNotFoundError(path)
        pieces.append(path)

    if not pieces:
        raise RuntimeError("Story has no pieces.")

    work = Path(output_dir)
    work.mkdir(parents=True, exist_ok=True)
    listing = work / f"{kind}_{index:02d}.txt"
    listing.write_text("\n".join(f"file '{p.resolve()}'" for p in pieces), encoding="utf-8")
    target = work / f"{kind}_{index:02d}.mp4"

    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(target)])
    return target


def main(selection_path, pieces_dir, output_dir):
    data = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    for kind, key in (("long", "long_stories"), ("short", "short_stories")):
        for index, story in enumerate(data.get(key, []), 1):
            assemble(story, index, kind, pieces_dir, output_dir)
    print("Story assembly complete.")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python src/assemble_stories.py <selection_json> <pieces_dir> <output_dir>")
    main(*sys.argv[1:])
