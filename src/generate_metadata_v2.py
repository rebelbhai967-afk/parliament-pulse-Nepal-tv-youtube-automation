import json
import re
import sys
from pathlib import Path

BASE_TAGS = [
    "Nepal Parliament", "Nepal Parliament News", "Nepal Politics", "Nepal News",
    "House of Representatives Nepal", "National Assembly Nepal", "Parliament Pulse Nepal TV"
]

TITLE_BANNED = (
    "shocking", "unbelievable", "destroyed", "exposed", "traitor",
    "disgrace", "scandal", "you won't believe", "breaking", "must watch",
    "viral", "sensational", "historic"
)

def contains_banned(text):
    lowered = clean(text).lower()
    return any(re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", lowered) for term in TITLE_BANNED)

def safe_title_topic(summary, fallback):
    summary = clean(summary)
    if not summary or contains_banned(summary):
        return fallback
    return summary

def neutralize_loaded_terms(text):
    """Keep translated topic text neutral enough for titles/metadata validation."""
    text = clean(text)
    replacements = {
        "exposed": "discussed",
        "shocking": "notable",
        "unbelievable": "reported",
        "destroyed": "affected",
        "traitor": "political figure",
        "disgrace": "controversy",
        "scandal": "issue",
        "you won't believe": "reported",
        "breaking": "latest",
        "must watch": "discussion",
        "viral": "widely discussed",
        "sensational": "notable",
        "historic": "significant",
    }
    for old, new in replacements.items():
        text = re.sub(rf"\b{re.escape(old)}\b", new, text, flags=re.I)
    # A second defensive pass prevents a replacement or punctuation boundary
    # from accidentally leaving a banned token in user-facing metadata.
    for banned in TITLE_BANNED:
        text = re.sub(rf"(?<![A-Za-z]){re.escape(banned)}(?![A-Za-z])", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" |:-")

TOPIC_LABELS = [
    ("water", "Water Management"),
    ("खाने पानी", "Water Management"),
    ("जलस्रोत", "Water Resources"),
    ("बजेट", "Budget and Planning"),
    ("विनियोजन", "Budget and Planning"),
    ("कानुन", "Law and Legislation"),
    ("विधेयक", "Law and Legislation"),
    ("संशोधन", "Law and Legislation"),
    ("शिक्षा", "Education"),
    ("स्वास्थ्य", "Health"),
    ("रोजगारी", "Employment"),
    ("महँगी", "Cost of Living"),
    ("सुरक्षा", "Public Security"),
    ("सीमा", "Border and Security"),
    ("सुशासन", "Governance and Public Administration"),
    ("भ्रष्टाचार", "Corruption and Accountability"),
    ("अनियमितता", "Public Accountability"),
    ("विकास", "Development and Infrastructure"),
    ("समिति", "Parliamentary Committee Discussion"),
    ("प्रतिवेदन", "Parliamentary Report"),
]

def fallback_topic(text):
    text = clean(text)
    matches = []
    lowered = text.lower()
    for needle, label in TOPIC_LABELS:
        if needle.lower() in lowered and label not in matches:
            matches.append(label)
    if matches:
        return matches[0]
    return "Parliamentary Discussion in Nepal"

def usable_english_summary(text):
    text = clean(text)
    if len(text) < 12:
        return ""
    letters = re.findall(r"[A-Za-z]", text)
    return text if len(letters) >= max(8, len(text) * 0.35) else ""

def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def english_keywords(text):
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text)
    return list(dict.fromkeys(words))

def source_topic_label(title):
    title = clean(title)
    if not title:
        return ""
    tail = title.split("/")[-1].strip()
    lowered = tail.lower()
    if any(x in lowered for x in ("national anthem", "sammananiye sabhamukh", "सम्माननीय अध्यक्ष")):
        return "Parliamentary Session"
    if any(x in lowered for x in ("zero hour", "शून्य समय")):
        return "Zero Hour Discussion"
    if any(x in lowered for x in ("jawaf", "जवाफ")):
        return "Parliamentary Response"
    if any(x in lowered for x in ("pratibedan", "प्रतिवेदन", "annual report", "वार्षिक प्रतिवेदन")):
        return "Parliamentary Report"
    if any(x in lowered for x in ("prastav", "proposal", "प्रस्ताव")):
        return "Parliamentary Proposal"
    if any(x in lowered for x in ("bidhyak", "bill", "विधेयक")):
        return "Bill and Legislation"
    if any(x in lowered for x in ("प्रश्नोत्तर", "question answer", "questions and answers", "question-answer")):
        return "Parliamentary Q&A"
    if any(x in lowered for x in ("विकास", "development")):
        return "Development and Infrastructure"
    if any(x in lowered for x in ("बजेट", "budget")):
        return "Budget and Planning"
    if any(x in lowered for x in ("कानुन", "law")):
        return "Law and Legislation"
    if any(x in lowered for x in ("शिक्षा", "education")):
        return "Education"
    if any(x in lowered for x in ("स्वास्थ्य", "health")):
        return "Health"
    if any(x in lowered for x in ("रोजगारी", "employment")):
        return "Employment"
    # Do not copy an arbitrary Nepali source-page label into an English-first
    # publishable title. Use a neutral English fallback instead.
    return "Parliamentary Discussion"

def safe_speaker(value):
    value = clean(value)
    if not value:
        return ""
    lowered = value.lower()
    bad = ("zero hour", "special hour", "jawaf", "prastav", "pratibedan", "bidhyak",
           "sammananiye", "national anthem", "प्रतिवेदन", "सभासमक्ष", "प्रस्ताव", "विधेयक",
           "प्रस्तुत", "पेस", "अध्यक्ष", "शून्य समय")
    return "" if any(x in lowered for x in bad) else value

def build(story, kind, index, summaries):
    speakers = [safe_speaker(x) for x in story.get("speakers", []) if safe_speaker(x)]
    houses = story.get("houses", [])
    issue = clean(story.get("topic_text", ""))[:220]
    speaker_text = " & ".join(speakers[:4]) if speakers else "Nepal Parliament"
    attribution = "Verified speaker attribution from the official Parliament video page." if speakers else "Speaker name was not provided on the official source page; no speaker name is inferred."

    pieces = story.get("pieces", [])
    source_videos = [p.get("video", "") for p in pieces if p.get("video")]
    source_page = story.get("source_page") or next((p.get("source_page", "") for p in pieces if p.get("source_page")), "")
    source_title = story.get("source_title") or next((p.get("page_title", "") for p in pieces if p.get("page_title")), "")
    summary = ""
    for video in source_videos:
        summary = clean(summaries.get(Path(video).stem, ""))
        if summary:
            break

    safe_topic = neutralize_loaded_terms(
        re.sub(r"[^A-Za-z0-9 ,&()\-]", "", usable_english_summary(summary)).strip()
    )
    topic_label = fallback_topic(issue)
    source_label = source_topic_label(source_title)
    if not safe_topic and source_label:
        topic_label = source_label
    topic_label = neutralize_loaded_terms(topic_label)
    title_topic = safe_title_topic(safe_topic, topic_label)
    hook = story.get("opening_hook") or {}
    hook_text = clean(hook.get("text"))
    house_text = houses[0] if houses else "Nepal Parliament"
    if kind == "long":
        title = f"{speaker_text} | {title_topic[:58]} | {house_text}"
    else:
        speaker = speakers[0] if speakers else safe_speaker(story.get("speaker"))
        title = f"{speaker} | {title_topic[:55]} | {house_text}" if speaker else f"{title_topic[:55]} | {house_text}"

    title = neutralize_loaded_terms(title)
    title = re.sub(r"\s+", " ", title).strip()
    # Final safety pass: no loaded/clickbait wording may enter a title
    # through a source label, speaker field, or translated summary.
    if contains_banned(title):
        title = f"{speaker_text} | {topic_label}"
    if contains_banned(title):
        title = f"Parliamentary Discussion | {topic_label}"
    if contains_banned(title):
        title = "Parliamentary Discussion | Nepal"

    # Final deterministic scrub. This runs after every fallback so a source-page
    # label, translated summary, or other metadata field cannot leak a loaded
    # token such as "exposed" into the publishable title.
    title = neutralize_loaded_terms(title)
    if contains_banned(title):
        title = "Parliamentary Discussion | Nepal"
    title = re.sub(r"\s+", " ", title).strip(" |:-")[:100]
    if contains_banned(title):
        title = "Parliamentary Discussion | Nepal"
    description = (
        f"{speaker_text} discusses a documented parliamentary issue in Nepal.\n"
        f"Speaker attribution: {attribution}\n\n"
        f"House: {', '.join(houses) if houses else 'Federal Parliament'}\n"
        f"Format: {'multi-speaker parliamentary discussion' if kind == 'long' else 'short parliamentary highlight'}\n"
        "Opening approach: transcript-grounded parliamentary moment.\n\n"
        f"Topic context: {safe_topic or topic_label}\n\n"
        "Source: Official Parliament of Nepal video archive. "
        "This edited clip removes non-substantive portions while preserving the meaning of the parliamentary statements. "
        "English subtitles are provided for accessibility."
    )
    # Final metadata safety pass: translated summaries or source labels must never
    # leak loaded/clickbait wording into publishable descriptions.
    description = neutralize_loaded_terms(description)
    if contains_banned(description):
        description = " ".join(
            part for part in description.split(" ")
            if part.lower().strip(".,:;!?()[]{}\\\"'") not in TITLE_BANNED
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
    # Final deterministic scrub after every field has been assembled.
    title = neutralize_loaded_terms(title)
    topic_label = neutralize_loaded_terms(topic_label)
    safe_topic = neutralize_loaded_terms(safe_topic)
    description = neutralize_loaded_terms(description)
    if contains_banned(title):
        title = "Parliamentary Discussion | Nepal"
    if contains_banned(description):
        description = "Discussion from the Official Parliament of Nepal video archive."
    hashtags = ["#NepalParliament", "#NepalPolitics", "#ParliamentNews", "#NepalNews", "#ParliamentPulseNepalTV"]
    return {
        "index": index, "title": title, "description": description,
        "tags": tags, "hashtags": hashtags, "category_id": "25", "privacy": "private",
        "speakers": speakers, "houses": houses, "story_text": issue,
        "source_title": source_title,
        "source_page": source_page,
        "speaker_attribution": attribution,
        "topic_summary": safe_topic or topic_label, "community_prompt": community_prompt,
        "hook": hook, "hook_strategy": story.get("hook_strategy", "strongest_available"),
        "duration": story.get("duration"), "kind": kind
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
