import json
import re
import sys
from pathlib import Path


BASE_TAGS = [
    "Nepal Parliament",
    "Nepal Parliament News",
    "Nepal Politics",
    "Nepal News",
    "संसद",
    "प्रतिनिधि सभा",
    "नेपाल संसद",
    "Parliament Pulse Nepal TV",
]


def clean_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def shorten(text, limit=90):
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def video_title_map(video_dir):
    mapping = {}
    metadata = Path(video_dir) / "videos.json"
    if not metadata.exists():
        return mapping

    for item in load_json(metadata):
        filename = Path(item.get("file", "")).name
        title = clean_text(item.get("title", ""))
        if filename and title:
            mapping[filename] = title

    return mapping


def build_metadata(story, label, source_titles):
    video_file = Path(story.get("video", "")).name
    source_title = source_titles.get(video_file, "")
    center = clean_text(story.get("center_text") or story.get("text"))

    if source_title:
        title = f"{source_title} | Parliament Pulse Nepal TV"
    elif center:
        title = f"{shorten(center, 82)} | Parliament Pulse Nepal TV"
    else:
        title = f"Nepal Parliament {label} | Parliament Pulse Nepal TV"

    title = title[:100]

    description = (
        f"Nepal Parliament {label} — Parliament Pulse Nepal TV.\n\n"
        f"Selected from an official Nepal Parliament video based on transcript "
        f"signals such as topic relevance, questions and important statements.\n\n"
        f"Topic excerpt:\n{shorten(center, 350)}\n\n"
        "This video is presented for news and public-information purposes. "
        "The channel does not alter the meaning of parliamentary statements."
    )

    tags = list(BASE_TAGS)
    for word in re.findall(r"[\u0900-\u097F]{3,}", center):
        if word not in tags:
            tags.append(word)
        if len(tags) >= 30:
            break

    return {
        "title": title,
        "description": description[:5000],
        "tags": tags[:30],
        "category_id": "25",
        "privacy": "private",
        "source_video": video_file,
        "start": story.get("start"),
        "end": story.get("end"),
        "story_text": center,
    }


def main():
    if len(sys.argv) != 3:
        print("Usage: python src/generate_metadata.py <daily_selection.json> <output_dir>")
        sys.exit(1)

    selection_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    data = load_json(selection_file)
    titles = video_title_map("data/videos")

    long_story = data.get("long_video")
    short_story = data.get("short_video")

    if not long_story:
        raise RuntimeError("No long_video found in selection.")

    long_metadata = build_metadata(long_story, "Long Video", titles)
    with open(output_dir / "long_metadata.json", "w", encoding="utf-8") as file:
        json.dump(long_metadata, file, ensure_ascii=False, indent=2)

    if short_story:
        short_metadata = build_metadata(short_story, "Short / Reel", titles)
        with open(output_dir / "short_metadata.json", "w", encoding="utf-8") as file:
            json.dump(short_metadata, file, ensure_ascii=False, indent=2)

    print(f"Created metadata in: {output_dir}")


if __name__ == "__main__":
    main()
