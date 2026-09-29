import json
import re
import sys
from pathlib import Path


BASE_TAGS = [
    "Nepal Parliament", "Nepal Parliament News", "Nepal Politics", "Nepal News",
    "House of Representatives Nepal", "National Assembly Nepal", "Parliament Pulse Nepal TV"
]


def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def english_keywords(text):
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text)
    return list(dict.fromkeys(words))


def build(story, kind, index):
    speakers = [clean(x) for x in story.get("speakers", []) if clean(x)]
    houses = story.get("houses", [])
    issue = clean(story.get("topic_text", ""))[:220]
    speaker_text = " & ".join(speakers[:4]) if speakers else "Nepal Parliament"

    if kind == "long":
        title = f"{speaker_text} | Key Parliamentary Debate in Nepal"
    else:
        speaker = speakers[0] if speakers else "Nepal Parliament"
        title = f"{speaker} | Key Parliament Speech in Nepal"

    title = re.sub(r"\s+", " ", title).strip()[:100]
    description = (
        f"{speaker_text} discusses an important parliamentary issue in Nepal.\n\n"
        f"House: {', '.join(houses) if houses else 'Federal Parliament'}\n"
        f"Format: {'multi-speaker parliamentary compilation' if kind == 'long' else 'short parliamentary highlight'}\n\n"
        f"Main topic context: {issue}\n\n"
        "Source: Official Parliament of Nepal video archive. "
        "This edited clip removes non-substantive portions while preserving the meaning of the parliamentary statements. "
        "English subtitles are provided for accessibility."
    )
    tags = BASE_TAGS + [speaker_text] + english_keywords(issue)[:18]
    tags = list(dict.fromkeys([x for x in tags if x]))[:30]
    hashtags = ["#NepalParliament", "#NepalPolitics", "#ParliamentNews", "#NepalNews", "#ParliamentPulseNepalTV"]
    return {
        "index": index, "title": title, "description": description,
        "tags": tags, "hashtags": hashtags, "category_id": "25", "privacy": "private",
        "speakers": speakers, "houses": houses, "story_text": issue,
        "duration": story.get("duration"), "kind": kind
    }


def main(selection, output):
    data = json.loads(Path(selection).read_text(encoding="utf-8"))
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    longs = [build(x, "long", i) for i, x in enumerate(data.get("long_stories", []), 1)]
    shorts = [build(x, "short", i) for i, x in enumerate(data.get("short_stories", []), 1)]
    (out / "long_metadata.json").write_text(json.dumps(longs, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "short_metadata.json").write_text(json.dumps(shorts, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "all_metadata.json").write_text(json.dumps({"long": longs, "short": shorts}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Metadata created: {len(longs)} long + {len(shorts)} short")
    

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python src/generate_metadata_v2.py <selection_json> <output_dir>")
        raise SystemExit(1)
    main(sys.argv[1], sys.argv[2])
