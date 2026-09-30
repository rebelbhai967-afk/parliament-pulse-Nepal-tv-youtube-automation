import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}


def session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


GENERIC_SPEAKERS = {
    "", "zero hour", "special hour", "jawaf", "prastav prastut",
    "ninrnayartha prastut", "nirdeshan", "samjhauta pes", "summary",
    "first meeting", "meeting", "sammananiye sabhamukh", "video",
    "watch video", "pratibedan pes", "pratibedhan pes", "national anthem",
    "bidhyak prastut", "सम्माननीय अध्यक्ष", "शून्य समय",
    "house of representatives", "national assembly", "federal parliament", "parliament",
    "annual report", "report presented", "proposal presented", "bill presented",
    "प्रतिवेदन", "सभासमक्ष", "सभा समक्ष", "वार्षिक प्रतिवेदन", "आर्थिक वर्ष",
    "प्रस्ताव प्रस्तुत", "विधेयक प्रस्तुत", "पेस", "प्रस्तुत", "बैठक", "अधिवेशन",
}

PROCEDURAL_SPEAKER_TERMS = (
    "बैठक", "अधिवेशन", "शून्य समय", "विशेष समय", "प्रतिवेदन", "सभासमक्ष",
    "सभासमक्ष पेस", "सभा समक्ष पेस", "विधेयक", "प्रस्तुत", "प्रस्ताव",
    "सम्माननीय अध्यक्ष", "अध्यक्ष", "national anthem", "zero hour",
    "special hour", "prastav", "bidhyak", "pratibedan", "sammananiye",
    "meeting", "session", "report", "presented", "proposal", "annual report",
    "bill", "exposed", "shocking", "unbelievable", "breaking", "viral",
)

def looks_like_person_name(text):
    text = clean(text)
    if not text or any(ch.isdigit() for ch in text):
        return False
    normalized = text.lower()
    if normalized in GENERIC_SPEAKERS:
        return False
    if any(term in normalized for term in PROCEDURAL_SPEAKER_TERMS):
        return False
    if any(term in normalized for term in ("प्रतिवेदन", "सभासमक्ष", "सभा समक्ष", "वार्षिक प्रतिवेदन", "आर्थिक वर्ष", "प्रस्ताव", "विधेयक", "प्रस्तुत", "पेस")):
        return False
    tokens = [t for t in re.split(r"\s+", text) if t]
    if not 2 <= len(tokens) <= 6:
        return False
    return any(re.search(r"[A-Za-z]", t) for t in tokens) or any(re.search(r"[\u0900-\u097F]", t) for t in tokens)

def normalize_speaker(text):
    text = clean(text)
    text = re.sub(r"^video\s*[-–:]\s*", "", text, flags=re.I)
    text = re.sub(r"^(मा\.?|माननीय|hon\.?|honorable)\s+", "", text, flags=re.I)
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    if normalized in GENERIC_SPEAKERS or not looks_like_person_name(text):
        return ""
    return text.strip()

def speaker_from_link(text):
    return normalize_speaker(text)

def speaker_from_page_title(title):
    """Extract a likely member name only from a clearly name-like title component."""
    title = clean(title)
    if not title:
        return ""
    # Parliament pages often append a member after a procedural/topic label.
    parts = re.split(r"\s*(?:/|\\||:|–|—)\s*", title)
    candidates = list(reversed([clean(x) for x in parts if clean(x)]))
    # Prefer components containing an honorific/member cue, then ordinary two-part names.
    for part in candidates:
        if re.search(r"\b(?:MP|Hon\.?|माननीय|मा\.?|सांसद)\b", part, re.I):
            cleaned = re.sub(r"\b(?:MP|Hon\.?|माननीय|मा\.?|सांसद)\b", " ", part, flags=re.I)
            candidate = normalize_speaker(cleaned)
            if candidate:
                return candidate
    for part in candidates:
        candidate = normalize_speaker(part)
        if candidate and not is_procedural_label_text(candidate):
            return candidate
    return ""

def is_procedural_label_text(text):
    value = clean(text).lower()
    return bool(value) and any(term in value for term in PROCEDURAL_SPEAKER_TERMS)


def video_pages(collection, s):
    response = s.get(collection["url"], timeout=30, verify=False)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    pages = []
    seen = set()
    host = f"{urlparse(collection['url']).scheme}://{urlparse(collection['url']).netloc}"

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href:
            continue
        full = urljoin(host, href)
        if not ("/np/video/" in full or "/en/video/" in full):
            continue
        if full in seen:
            continue
        seen.add(full)
        label = clean(link.get_text(" ", strip=True))
        pages.append({
            "page": full,
            "speaker": speaker_from_link(label),
            "link_label": label,
        })
    return pages


def source_from_page(page_url, s):
    response = s.get(page_url, timeout=30, verify=False)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    title_candidates = []
    speaker_hints = []
    h1 = soup.find("h1")
    if h1:
        title_candidates.append(h1.get_text(" ", strip=True))
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        title_candidates.append(clean(og.get("content")))
    if soup.title:
        title_candidates.append(soup.title.get_text(" ", strip=True))

    # The Parliament archive often exposes member names as child labels such as
    # "video - Hon. Name" while the page title itself is a session/topic label.
    # Capture those explicit labels rather than guessing a speaker from the
    # procedural title.
    for node in soup.find_all(string=re.compile(r"^\s*video\s*-\s*", re.I)):
        hint = clean(node)
        if hint:
            speaker_hints.append(hint)

    title = next((x for x in title_candidates if clean(x)), "")
    speaker_hint = ""
    for hint in speaker_hints:
        candidate = speaker_from_link(hint)
        if candidate:
            speaker_hint = candidate
            break

    for tag in soup.find_all(["video", "source", "iframe"]):
        for attr in ["src", "data-src", "data-video"]:
            value = clean(tag.get(attr))
            if value and (".mp4" in value.lower() or ".m3u8" in value.lower() or "video" in value.lower()):
                return urljoin(page_url, value), title, speaker_hint
    return None, title, speaker_hint


def download(url, path, s):
    with s.get(url, stream=True, timeout=180, verify=False) as response:
        response.raise_for_status()
        with open(path, "wb") as f:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)


def main(collections_json, output_dir, max_collections=16, max_videos=24):
    data = json.loads(Path(collections_json).read_text(encoding="utf-8"))
    collections = data.get("collections", [])
    selected = []
    seen_sources = set()
    for item in collections:
        if item["source_id"] not in seen_sources or len(selected) < max_collections:
            selected.append(item)
            seen_sources.add(item["source_id"])
        if len(selected) >= max_collections:
            break

    # Prefer two latest collections per House.
    # Respect the requested collection budget and spread it across both Houses.
    # The previous implementation hard-coded only two collections per House,
    # which could leave the pipeline with too few distinct videos for 12+12.
    selected = []
    counts = {}
    seen_collection = set()
    for item in collections:
        key = (item.get("source_id"), item.get("url"))
        if key in seen_collection:
            continue
        source_id = item.get("source_id", "")
        if counts.get(source_id, 0) >= max(1, max_collections // 2):
            continue
        selected.append(item)
        seen_collection.add(key)
        counts[source_id] = counts.get(source_id, 0) + 1
        if len(selected) >= max_collections:
            break

    # If one House has fewer available collections, fill remaining slots from
    # the other House instead of silently stopping early.
    if len(selected) < max_collections:
        for item in collections:
            key = (item.get("source_id"), item.get("url"))
            if key in seen_collection:
                continue
            selected.append(item)
            seen_collection.add(key)
            if len(selected) >= max_collections:
                break

    s = session()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = []
    seen_pages = set()
    index = 1
    page_candidates = []

    # Inspect all selected collection pages first. Then prioritize verified
    # person-name labels, while keeping the actual downloaded source count low.
    for collection in selected:
        pages = video_pages(collection, s)
        print(f"{collection['house']}: {len(pages)} videos in {collection['title']}")
        for page in pages:
            if page["page"] in seen_pages:
                continue
            seen_pages.add(page["page"])
            speaker = page.get("speaker") or speaker_from_page_title(page.get("link_label", ""))
            # Resolve the actual video page title before ranking candidates. Parliament
            # collection labels are often procedural (e.g. "Zero Hour"), while the
            # individual video page title can contain the member's real name.
            page_source = None
            page_title = ""
            page_speaker = ""
            try:
                page_source, page_title, page_speaker = source_from_page(page["page"], s)
            except Exception as exc:
                print("Page metadata failed:", page["page"], exc)
            speaker = speaker or speaker_from_page_title(page_title)
            page_candidates.append({
                "collection": collection,
                "page": page,
                "speaker": speaker or page_speaker,
                "page_title": page_title,
                "source": page_source,
            })

    named = [x for x in page_candidates if x["speaker"]]
    unnamed = [x for x in page_candidates if not x["speaker"]]
    ordered = []

    # Round-robin Houses for named clips first, so both Houses remain represented.
    houses = []
    for item in page_candidates:
        house = item["collection"]["house"]
        if house not in houses:
            houses.append(house)

    while named and len(ordered) < max_videos:
        made = False
        for house in houses:
            hit = next((x for x in named if x["collection"]["house"] == house), None)
            if hit:
                ordered.append(hit)
                named.remove(hit)
                made = True
                if len(ordered) >= max_videos:
                    break
        if not made:
            break

    ordered.extend(unnamed[:max(0, max_videos - len(ordered))])

    for item in ordered:
        collection = item["collection"]
        page = item["page"]
        try:
            source = item.get("source")
            page_title = item.get("page_title", "")
            page_speaker = item.get("speaker", "")
            if not source:
                source, page_title, page_speaker = source_from_page(page["page"], s)
            if not source:
                print("Skipping: no video source", page["page"])
                continue
            path = out / f"video_{index:03d}.mp4"
            speaker = item["speaker"] or page_speaker or speaker_from_page_title(page_title)
            print(f"Downloading {index}: {speaker or '[unattributed]'} -> {path.name}")
            download(source, path, s)
            records.append({
                "index": index,
                "file": str(path),
                "page": page["page"],
                "source": source,
                "house": collection["house"],
                "source_id": collection["source_id"],
                "collection_title": collection["title"],
                "page_title": page_title,
                "speaker": normalize_speaker(speaker),
            })
            index += 1
        except Exception as exc:
            print("Download failed:", page["page"], exc)

    (out / "videos.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    named = sum(1 for item in records if item.get("speaker"))
    print(f"Downloaded {len(records)} Parliament videos from both Houses; speaker-attributed: {named}.")
    if len(records) < 4:
        raise RuntimeError("Too few Parliament videos downloaded for multi-story selection.")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4, 5):
        print("Usage: python src/download_multi.py <collections_json> <output_dir> [max_collections] [max_videos]")
        raise SystemExit(1)
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) >= 4 else 4, int(sys.argv[4]) if len(sys.argv) >= 5 else 20)
