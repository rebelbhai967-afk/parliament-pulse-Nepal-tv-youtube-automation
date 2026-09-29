import json
import sys
from pathlib import Path


def main(selection_path, gate_report_path, output_path):
    selection = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    gate = json.loads(Path(gate_report_path).read_text(encoding="utf-8"))

    warnings = gate.get("warnings", [])
    warning_text = "\n".join(str(x) for x in warnings).lower()
    rows = []

    for kind in ("long", "short"):
        for index, story in enumerate(selection.get(f"{kind}_stories", []), 1):
            reasons = []
            hook = story.get("opening_hook") or {}
            if not hook.get("text"):
                reasons.append("missing_hook")
            if not story.get("speakers"):
                reasons.append("missing_speaker")
            if not story.get("houses"):
                reasons.append("missing_house")
            if any(f"{kind} {index}" in str(w).lower() for w in warnings):
                reasons.append("editorial_gate_warning")
            if "source reused" in warning_text:
                reasons.append("source_reuse_warning")

            rows.append({
                "kind": kind,
                "index": index,
                "content_id": f"PPN-{kind.upper()}-{index:02d}",
                "status": "REVIEW_REQUIRED" if reasons else "AUTO_SAFE_FOR_QC",
                "reasons": sorted(set(reasons)),
            })

    report = {
        "policy": "No item is published automatically from this review queue.",
        "manual_review_required_before_publication": True,
        "items": rows,
    }
    Path(output_path).write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    review = sum(x["status"] == "REVIEW_REQUIRED" for x in rows)
    print(f"Editorial review queue: {len(rows)} items; {review} require review.")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: python src/editorial_review.py <selection_json> <gate_report_json> <output_json>"
        )
    main(*sys.argv[1:])
