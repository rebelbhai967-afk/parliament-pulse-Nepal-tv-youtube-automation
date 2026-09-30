import json
import re
import sys
from pathlib import Path

BANNED_TITLE_PHRASES = [
    "shocking", "unbelievable", "destroyed", "exposed", "traitor",
    "disgrace", "scandal", "you won't believe", "breaking!!!",
    "must watch", "viral", "sensational", "historic!!!"
]

def contains_banned_phrase(text):
    lowered = str(text or "").lower()
    return any(re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", lowered) for phrase in BANNED_TITLE_PHRASES)

def validate_item(item, kind):
    errors = []
    title = str(item.get("title", "")).strip()
    description = str(item.get("description", "")).strip()
    speakers = item.get("speakers") or []
    hook = item.get("hook") or {}
    topic_summary = str(item.get("topic_summary", "")).strip()
    houses = item.get("houses") or []

    if not title:
        errors.append("missing title")
    if len(title) > 100:
        errors.append("title > 100 chars")
    if not description:
        errors.append("missing description")
    if len(description) > 5000:
        errors.append("description > 5000 chars")
    if not houses:
        errors.append("missing House attribution")
    # A Parliament video may expose a procedural title rather than a member
    # name. That is valid source attribution; never invent a speaker name.
    if not hook.get("text"):
        errors.append("missing transcript-grounded opening hook")
    if not topic_summary:
        errors.append("missing usable topic summary")
    if contains_banned_phrase(title):
        errors.append("loaded/clickbait title phrase after normalization")
    if hook.get("strategy") not in {"question_hook", "public_issue_hook", "strong_quote_hook", "strongest_available"}:
        errors.append("invalid hook strategy")

    lowered_title = title.lower()
    for phrase in BANNED_TITLE_PHRASES:
        if re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", lowered_title):
            errors.append(f"loaded/clickbait title phrase: {phrase}")

    # Topic summaries are also user-facing metadata, so they must remain neutral.
    for phrase in BANNED_TITLE_PHRASES:
        if re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", topic_summary.lower()):
            errors.append(f"loaded/clickbait topic phrase: {phrase}")

    if re.search(r"!{2,}|\?{2,}|\bOMG\b|\bSHOCKING\b", title, re.I):
        errors.append("sensational punctuation/language")

    if kind == "short" and len(title) > 95:
        errors.append("short title should stay compact")

    return errors

def main(metadata_dir):
    root = Path(metadata_dir)
    report = {"status": "PASS", "errors": [], "checked": 0}
    for kind in ("long", "short"):
        path = root / f"{kind}_metadata.json"
        if not path.exists():
            report["errors"].append(f"missing {path}")
            continue
        items = json.loads(path.read_text(encoding="utf-8"))
        for item in items:
            report["checked"] += 1
            for error in validate_item(item, kind):
                report["errors"].append({"kind": kind, "index": item.get("index"), "error": error})
    if report["errors"]:
        report["status"] = "FAIL"
    out = root / "metadata_quality_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python src/validate_metadata.py <metadata_dir>")
    main(sys.argv[1])
