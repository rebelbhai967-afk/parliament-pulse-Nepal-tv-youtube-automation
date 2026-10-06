import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def stable_content_id(kind, pieces):
    records = []
    for piece in pieces:
        records.append(
            "|".join([
                str(piece.get("source_page", "")).strip(),
                str(piece.get("video", "")).strip(),
                str(round(float(piece.get("start", 0)), 3)),
                str(round(float(piece.get("end", 0)), 3)),
            ])
        )
    key = f"{kind}|" + "||".join(sorted(records))
    return "PPN-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16].upper(), key


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
            pieces = story.get("pieces", [])
            content_id, stable_key = stable_content_id(kind, pieces)
            source_records = [
                {
                    "video": p.get("video", ""),
                    "source_page": p.get("source_page", ""),
                    "page_title": p.get("page_title", ""),
                    "start": round(float(p.get("start", 0)), 3),
                    "end": round(float(p.get("end", 0)), 3),
                }
                for p in pieces
            ]
            rows.append({
                "content_id": content_id,
                "kind": kind,
                "index": index,
                "title": m.get("title"),
                "speakers": m.get("speakers", story.get("speakers", [])),
                "houses": m.get("houses", story.get("houses", [])),
                "source_videos": [p.get("video") for p in pieces if p.get("video")],
                "source_records": source_records,
                "source_fingerprint": hashlib.sha256(stable_key.encode("utf-8")).hexdigest(),
                "duration": story.get("duration"),
                "source": "Official Parliament of Nepal video archive",
                "state": "GENERATED",
                "qc": "PENDING",
                "editorial_review": "PENDING",
                "youtube": {"status": "PENDING", "video_id": "", "url": ""},
                "facebook": {"status": "PENDING", "post_id": "", "url": ""},
                "instagram": {"status": "PENDING", "post_id": "", "url": ""},
                "tiktok": {"status": "PENDING", "post_id": "", "url": ""},
            })

    Path(output).write_text(
        json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "state_machine": [
                "GENERATED",
                "QC_PASS",
                "EDITORIAL_REVIEW",
                "APPROVED",
                "UPLOADED_PRIVATE",
                "SCHEDULED",
                "PUBLISHED",
                "VERIFIED",
            ],
            "items": rows,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Content ledger created: {len(rows)} items")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python src/content_ledger.py <selection_json> <metadata_dir> <output_json>")
    main(*sys.argv[1:])
