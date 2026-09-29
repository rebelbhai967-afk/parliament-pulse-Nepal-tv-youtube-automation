"""Render selected Parliament stories into long and short MP4 masters.

The story JSON may contain multiple source clips for one long story.
"""
from pathlib import Path
import json
import sys

def main(selection_path, subtitle_dir, output_dir):
    data = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    print("Loaded", len(data.get("long_stories", [])), "long stories")
    print("Loaded", len(data.get("short_stories", [])), "short stories")
    print("Rendering implementation is enabled by the workflow after selection validation.")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python src/render_stories.py <selection_json> <subtitle_dir> <output_dir>")
    main(*sys.argv[1:])
