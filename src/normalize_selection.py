import json
import sys
from pathlib import Path

from editorial_hooks import enrich_piece


def clean(value):
    return " ".join(str(value or "").split()).strip()


def normalize_piece(piece):
    transcript = piece.get("transcript")
    if not transcript:
        return piece
    path = Path(transcript)
    if not path.exists():
        return piece

    data = json.loads(path.read_text(encoding="utf-8"))
    start = float(piece.get("start", 0))
    end = float(piece.get("end", start))
    segments = [
        s for s in data.get("segments", [])
        if float(s.get("end", 0)) > start and float(s.get("start", 0)) < end
    ]
    text = clean(" ".join(clean(s.get("nepali")) for s in segments))
    if text:
        piece["text"] = text
        piece["hook_text"] = clean(" ".join(clean(s.get("nepali")) for s in segments[:2]))
        piece["score"] = max(float(piece.get("score", 0)), 0)
    return enrich_piece(piece)


def main(selection_path, output_path):
    data = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    for kind in ("long_stories", "short_stories"):
        for story in data.get(kind, []):
            pieces = [normalize_piece(dict(p)) for p in story.get("pieces", [])]
            story["pieces"] = pieces
            story["topic_text"] = clean(" ".join(p.get("text", "") for p in pieces))
            story["duration"] = round(sum(float(p.get("end", 0)) - float(p.get("start", 0)) for p in pieces), 3)
            hooks = [p.get("hook") for p in pieces if p.get("hook")]
            if hooks:
                story["opening_hook"] = hooks[0]
                story["hook_strategy"] = hooks[0].get("strategy", "strongest_available")
    Path(output_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Selection normalized against the exact rendered transcript windows.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python src/normalize_selection.py <input_json> <output_json>")
    main(*sys.argv[1:])
