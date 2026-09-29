import json
import sys
from datetime import datetime, timezone
from pathlib import Path

def main(selection, metadata_dir, output):
    selection_data = json.loads(Path(selection).read_text(encoding="utf-8"))
    metadata = {}
    for kind in ("long", "short"):
        path = Path(metadata_dir) / f"{kind}_metadata.json"
        metadata[kind] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    rows = []
    for kind, key in (("long", "long_stories"), ("short", "short_stories")):
        stories = selection_data.get(key, [])
        meta_by_index = {x.get("index"): x for x in metadata[kind]}
        for index, story in enumerate(stories, 1):
            m = meta_by_index.get(index, {})
            rows.append({
                "content_id": f"PPN-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{kind.upper()}-{index:02d}",
                "kind": kind,
                "index": index,
                "title": m.get("title"),
                "speakers": m.get("speakers", story.get("speakers", [])),
                "houses": m.get("houses", story.get("houses", [])),
                "source_videos": [p.get("video") for p in story.get("pieces", []) if p.get("video")],
                "duration": story.get("duration"),
                "source": "Official Parliament of Nepal video archive",
                "youtube": "pending",
                "facebook": "pending",
                "instagram": "pending",
                "tiktok": "pending",
            })

    Path(output).write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": rows
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Content ledger created: {len(rows)} items")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python src/content_ledger.py <selection_json> <metadata_dir> <output_json>")
    main(*sys.argv[1:])
