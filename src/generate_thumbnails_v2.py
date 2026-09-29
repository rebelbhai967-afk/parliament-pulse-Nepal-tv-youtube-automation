import json
import subprocess
import sys
from pathlib import Path


def main(metadata_dir, masters_dir, output_dir):
    meta_dir = Path(metadata_dir)
    masters = Path(masters_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for kind, vertical in (("long", "false"), ("short", "true")):
        items = json.loads((meta_dir / f"{kind}_metadata.json").read_text(encoding="utf-8"))
        for item in items:
            index = int(item["index"])
            video = masters / f"{kind}_{index:02d}.mp4"
            if not video.exists():
                raise FileNotFoundError(video)
            target = out / f"{kind}_{index:02d}.jpg"
            subprocess.run([
                "python", "src/thumbnail.py", str(video), item["title"], "0", str(target), vertical
            ], check=True)
    print("V2 thumbnails created.")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python src/generate_thumbnails_v2.py <metadata_dir> <masters_dir> <output_dir>")
    main(*sys.argv[1:])
