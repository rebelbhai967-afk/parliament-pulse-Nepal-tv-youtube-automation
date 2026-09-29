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

def build(story, kind, index, summaries):
    speakers = [clean(x) for x in story.get("speakers", []) if clean(x)]
    houses = story.get("houses", [])
    issue = clean(story.get("topic_text", ""))[:220]
    speaker_text = " & ".join(speakers[:4]) if speakers else "Nepal Parliament"

    source_videos = [p.get("video", "") for p in story.get("pieces", []) if p.get("video")]
    summary = ""
    for video in source_videos:
        summary = clean(summaries.get(Path(video).stem, ""))
        if summary:
            break

    safe_topic = re.sub(r"[^A-Za-z0-9 ,&()\-]", "", summary).strip()
    if kind == "long":
        title = f"{speaker_text} | Parliament Discussion in Nepal"
        if safe_topic:
            title = f"{speaker_text} | {safe_topic[:55]}"
    else:
        speaker = speakers[0] if speakers else clean(story.get("speaker")) or "Nepal Parliament"
        title = f"{speaker} | Parliament Speech in Nepal"
        if safe_topic:
            title = f"{speaker} | {safe_topic[:60]}"

    title = re.sub(r"\s+", " ", title).strip()[:100]
    description = (
        f"{speaker_text} discusses a documented parliamentary issue in Nepal.\n\n"
        f"House: {', '.join(houses) if houses else 'Federal Parliament'}\n"
        f"Format: {'multi-speaker parliamentary discussion' if kind == 'long' else 'short parliamentary highlight'}\n\n"
        f"Topic context: {summary or issue}\n\n"
        "Source: Official Parliament of Nepal video archive. "
        "This edited clip removes non-substantive portions while preserving the meaning of the parliamentary statements. "
        "English subtitles are provided for accessibility."
    )
    tags = BASE_TAGS + speakers[:4] + english_keywords(summary)[:18]
    tags = list(dict.fromkeys([x for x in tags if x]))[:30]
    prompts = [
        "Which part of this parliamentary discussion would you like explained in a future video?",
        "What public issue raised here deserves more attention or context?",
        "Which point from this discussion should we document next?"
    ]
    community_prompt = prompts[(index - 1) % len(prompts)]
    description += f"\\n\\nCommunity note: {community_prompt}"
    hashtags = ["#NepalParliament", "#NepalPolitics", "#ParliamentNews", "#NepalNews", "#ParliamentPulseNepalTV"]
    return {
        "index": index, "title": title, "description": description,
        "tags": tags, "hashtags": hashtags, "category_id": "25", "privacy": "private",
        "speakers": speakers, "houses": houses, "story_text": issue,
        "topic_summary": summary, "community_prompt": community_prompt, "duration": story.get("duration"), "kind": kind
    }

def main(selection, output, summary_file=None):
    data = json.loads(Path(selection).read_text(encoding="utf-8"))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    summaries = json.loads(Path(summary_file).read_text(encoding="utf-8")) if summary_file and Path(summary_file).exists() else {}
    longs = [build(x, "long", i, summaries) for i, x in enumerate(data.get("long_stories", []), 1)]
    shorts = [build(x, "short", i, summaries) for i, x in enumerate(data.get("short_stories", []), 1)]
    (out / "long_metadata.json").write_text(json.dumps(longs, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "short_metadata.json").write_text(json.dumps(shorts, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "all_metadata.json").write_text(json.dumps({"long": longs, "short": shorts}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Metadata created: {len(longs)} long + {len(shorts)} short")

if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print("Usage: python src/generate_metadata_v2.py <selection_json> <output_dir> [summary_json]")
        raise SystemExit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)
