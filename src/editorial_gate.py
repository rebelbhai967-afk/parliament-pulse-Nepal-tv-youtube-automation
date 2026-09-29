import json
import re
import sys
from pathlib import Path

BANNED = (
    "shocking", "unbelievable", "destroyed", "exposed", "traitor",
    "disgrace", "you won't believe", "breaking!!!", "must watch",
    "viral", "sensational", "historic!!!"
)
GENERIC_TITLES = (
    "parliament discussion in nepal",
    "parliament speech in nepal",
    "nepal parliament news"
)

def norm(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()

def validate(selection, metadata_dir):
    errors = []
    warnings = []
    title_seen = {}
    source_seen = {}
    hook_seen = {}

    for kind in ("long", "short"):
        stories = selection.get(f"{kind}_stories", [])
        path = Path(metadata_dir) / f"{kind}_metadata.json"
        metadata = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        by_index = {int(x.get("index", 0)): x for x in metadata}

        for idx, story in enumerate(stories, 1):
            m = by_index.get(idx, {})
            title = norm(m.get("title"))
            desc = norm(m.get("description"))
            hook = norm((story.get("opening_hook") or {}).get("text"))
            sources = [norm(p.get("video")) for p in story.get("pieces", []) if p.get("video")]
            speakers = [norm(x) for x in story.get("speakers", []) if norm(x)]

            if not title:
                errors.append(f"{kind} {idx}: missing title")
            elif title in GENERIC_TITLES:
                warnings.append(f"{kind} {idx}: generic fallback title")
            if title in title_seen:
                errors.append(f"duplicate title: {kind} {idx} and {title_seen[title]}")
            else:
                title_seen[title] = f"{kind} {idx}"

            if not sources:
                errors.append(f"{kind} {idx}: no source video")
            if not story.get("houses"):
                errors.append(f"{kind} {idx}: missing Parliament House attribution")
            for piece in story.get("pieces", []):
                if not norm(piece.get("source_page")):
                    errors.append(f"{kind} {idx}: missing official source page for a selected piece")
            for src in sources:
                source_seen.setdefault(src, []).append(f"{kind} {idx}")

            if not hook:
                errors.append(f"{kind} {idx}: missing opening hook")
            elif len(hook) < 20:
                warnings.append(f"{kind} {idx}: very short hook text")
            elif hook in hook_seen:
                warnings.append(f"repeated hook text: {kind} {idx} and {hook_seen[hook]}")
            else:
                hook_seen[hook] = f"{kind} {idx}"

            if not speakers:
                warnings.append(f"{kind} {idx}: speaker name not available from official source page; do not infer a name")
            if "official parliament of nepal" not in desc:
                errors.append(f"{kind} {idx}: missing official source attribution")

            combined = title + " " + desc
            for phrase in BANNED:
                if phrase in combined:
                    errors.append(f"{kind} {idx}: prohibited/sensational phrase '{phrase}'")

            if re.search(r"!{2,}|\?{2,}", title):
                errors.append(f"{kind} {idx}: excessive punctuation")

            if kind == "short" and len(title) > 95:
                warnings.append(f"{kind} {idx}: title is long for short-form")

    # A source appearing many times is not automatically wrong, but it is an
    # editorial warning: the channel should not become a single-speech clip farm.
    for src, items in source_seen.items():
        if len(items) >= 3:
            warnings.append(f"source reused {len(items)} times: {src}")

    return errors, warnings

def main(selection_path, metadata_dir):
    selection = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    errors, warnings = validate(selection, metadata_dir)
    report = {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "principles": [
            "No fabricated claims or unsupported context.",
            "No sensational/clickbait language.",
            "Every item has official source attribution; speaker attribution is required when the official source page provides a name.",
            "Repeated source material is surfaced for editorial review.",
            "Hook text must be grounded in the selected parliamentary transcript."
        ]
    }
    out = Path(metadata_dir) / "editorial_gate_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python src/editorial_gate.py <selection_json> <metadata_dir>")
    main(sys.argv[1], sys.argv[2])
