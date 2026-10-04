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
    "download on app store", "download on the app store",
    "get it on google play", "get it on google play store",
    "app store", "google play", "download on play store", "download on the play store",
    "get it on play store", "get it on the play store", "play store", "watch on youtube",
    "ninrnayartha prastut", "nirdeshan", "samjhauta pes", "summary",
    "first meeting", "meeting", "sammananiye sabhamukh", "video",
    "watch video", "pratibedan pes", "pratibedhan pes", "national anthem",
    "bidhyak prastut", "सम्माननीय अध्यक्ष", "शून्य समय",
    "house of representatives", "national assembly", "federal parliament", "parliament",
    "annual report", "report presented", "proposal presented", "bill presented",
    "parliamentary session", "parliamentary discussion", "house session",
    "house meeting", "meeting of the house", "assembly meeting", "full video",
    "discussion", "session", "meeting",
    "प्रतिवेदन", "सभासमक्ष", "सभा समक्ष", "वार्षिक प्रतिवेदन", "आर्थिक वर्ष",
    "प्रस्ताव प्रस्तुत", "विधेयक प्रस्तुत", "पेस", "प्रस्तुत", "बैठक", "अधिवेशन",
    "बजेट", "विकास", "शिक्षा", "स्वास्थ्य", "रोजगारी", "सुरक्षा", "कानुन", "समिति",
    "budget", "development", "education", "health", "employment", "security", "law", "committee",
}

PROCEDURAL_SPEAKER_TERMS = (
    "बैठक", "अधिवेशन", "शून्य समय", "विशेष समय", "प्रतिवेदन", "सभासमक्ष",
    "सभासमक्ष पेस", "सभा समक्ष पेस", "विधेयक", "प्रस्तुत", "प्रस्ताव",
    "सम्माननीय अध्यक्ष", "अध्यक्ष", "national anthem", "zero hour",
    "special hour", "prastav", "bidhyak", "pratibedan", "sammananiye",
    "meeting", "session", "report", "presented", "proposal", "annual report",
    "exposed", "shocking", "unbelievable", "breaking", "viral",
)


def looks_like_person_name(text):
    text = clean(text)
    if not text or any(ch.isdigit() for ch in text):
        return False
    normalized = text.lower()
    ui_tokens = (
        "download on app store", "download on the app store",
        "get it on google play", "get it on google play store",
        "app store", "google play", "download on play store", "download on the play store",
        "get it on play store", "get it on the play store", "play store", "watch on youtube",
    )
    if any(token in normalized for token in ui_tokens):
        return False
    if normalized in GENERIC_SPEAKERS:
        return False
    if any(term in normalized for term in PROCEDURAL_SPEAKER_TERMS):
        return False
    tokens = [t for t in re.split(r"\s+", text) if t]
    if not 2 <= len(tokens) <= 6:
        return False
    # A verified label should contain either Latin or Devanagari name tokens.
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
    # Official Parliament collection pages use labels such as "video - Gagan
    # Kumar Thapa". Some pages also expose the member name without the "video -"
    # prefix. Accept both forms, but run every label through the procedural/name
    # safety filter so labels such as "Zero Hour" or "Bill Presented" are never
    # promoted to speaker names.
    value = clean(text)
    # Collection cards often expose a larger parent label such as
    # "Meeting ... video - Member Name video - Member Name". Extract the
    # official "video - Name" token anywhere in that label, rather than only
    # when the whole string starts with "video -".
    match = re.search(
        r"video\s*[-–:]\s*(.*?)(?=\s+video\s*[-–:]|$)",
        value,
        flags=re.I,
    )
    if match:
        value = clean(match.group(1))
    else:
        value = re.sub(r"^video\s*[-–:]\s*", "", value, flags=re.I).strip()
    return normalize_speaker(value)


def speaker_hints_from_page_text(soup):
    """Recover official 'video - Member Name' labels from rendered page text."""
    hints = []
    try:
        text = soup.get_text(" ", strip=True)
    except Exception:
        text = ""
    if text:
        for match in re.finditer(
            r"video\s*[-–:]\s*(.*?)(?=\s+video\s*[-–:]|$)",
            text,
            flags=re.I,
        ):
            value = clean(match.group(1))
            if value and len(value) <= 100:
                hints.append(value)
    return hints


def speaker_from_page_title(title):
    # Official Parliament video pages sometimes expose the member name only
    # in the final component of the page title, e.g.
    # "House meeting / Ambika Devi Sangraula". Accept that final component
    # only when it is clearly non-procedural; never promote labels such as
    # "zero hour", "jawaf", "report", etc. to a speaker name.
    title = clean(title)
    if not title:
        return ""
    parts = re.split(r"\s*(?:/|\||:|–|—)\s*", title)
    for part in reversed([clean(x) for x in parts if clean(x)]):
        if re.search(r"\b(?:MP|Hon\.?|Honorable|माननीय|मा\.?|सांसद)\b", part, re.I):
            candidate = re.sub(r"\b(?:MP|Hon\.?|Honorable|माननीय|मा\.?|सांसद)\b", " ", part, flags=re.I)
            candidate = normalize_speaker(candidate)
            if candidate:
                return candidate
        # Some official Parliament pages expose a member name only after
        # the final "/" without an explicit MP/Hon./सांसद marker. Accept that
        # final component only when the existing name/procedural filters classify
        # it as a plausible person name. Never promote procedural labels.
        candidate = normalize_speaker(part)
        if candidate:
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
        label_parts = [
            clean(link.get_text(" ", strip=True)),
            clean(link.get("aria-label")),
            clean(link.get("title")),
            clean(link.get("data-title")),
            clean(link.get("data-name")),
        ]
        parent = link.parent
        if parent:
            parent_text = clean(parent.get_text(" ", strip=True))
            if parent_text and len(parent_text) <= 180:
                label_parts.append(parent_text)
        label = next((x for x in label_parts if x), "")
        speaker = ""
        for candidate in label_parts:
            speaker = speaker_from_link(candidate)
            if speaker:
                break
        pages.append({
            "page": full,
            "speaker": speaker,
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

    for node in soup.find_all(string=re.compile(r"video\s*[-–:]\s*", re.I)):
        hint = clean(node)
        if hint:
            speaker_hints.append(hint)
    for node in soup.find_all(string=True):
        hint = clean(node)
        if not hint or len(hint) > 120:
            continue
        if re.search(r"(?:video|सांसद|member|mp)\s*[-–:]", hint, re.I):
            speaker_hints.append(hint)
    for anchor in soup.find_all("a", href=True):
        for attr in ("aria-label", "title", "data-title", "data-name"):
            hint = clean(anchor.get(attr))
            if hint:
                speaker_hints.append(hint)

    speaker_hints.extend(speaker_hints_from_page_text(soup))

    title = next((x for x in title_candidates if clean(x)), "")
    speaker_hint = ""
    for hint in speaker_hints:
        candidate = speaker_from_link(hint)
        if candidate:
            speaker_hint = candidate
            break
    # Some Parliament pages expose the member name only in the page title
    # (for example, "House meeting / Dhurba Raj Rai"). Use that as a
    # second verified source before giving up, but never promote procedural
    # labels such as "Zero Hour", "Bill Presented", or "Annual Report".
    if not speaker_hint:
        speaker_hint = speaker_from_page_title(title)
    for meta in soup.find_all("meta"):
        value = clean(meta.get("content"))
        if not value or len(value) > 180:
            continue
        candidate = speaker_from_page_title(value)
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

    for collection in selected:
        pages = video_pages(collection, s)
        print(f"{collection['house']}: {len(pages)} videos in {collection['title']}")
        for page in pages:
            if page["page"] in seen_pages:
                continue
            seen_pages.add(page["page"])
            page_source = None
            page_title = ""
            page_speaker = ""
            try:
                page_source, page_title, page_speaker = source_from_page(page["page"], s)
            except Exception as exc:
                print("Page metadata failed:", page["page"], exc)
            # Never promote the ordinary page title into a speaker name.
            speaker = page.get("speaker") or page_speaker
            page_candidates.append({
                "collection": collection,
                "page": page,
                "speaker": speaker,
                "page_title": page_title,
                "source": page_source,
            })

    # Build a balanced candidate pool across both Houses. Speaker attribution is
    # best-effort, but source diversity is mandatory: a small run must not fill
    # almost entirely from whichever House appears first on the archive page.
    houses = []
    for item in page_candidates:
        house = item["collection"]["house"]
        if house not in houses:
            houses.append(house)

    by_house = {house: [] for house in houses}
    for item in page_candidates:
        by_house.setdefault(item["collection"]["house"], []).append(item)

    # Within each House, prefer verified member names first, then other official
    # Parliament pages. Never manufacture a speaker from a procedural page title.
    for house in by_house:
        by_house[house].sort(key=lambda x: (1 if x.get("speaker") else 0), reverse=True)

    ordered = []
    while len(ordered) < max_videos:
        made = False
        for house in houses:
            pool = by_house.get(house, [])
            if pool:
                ordered.append(pool.pop(0))
                made = True
                if len(ordered) >= max_videos:
                    break
        if not made:
            break

    for item in ordered:
        collection = item["collection"]
        page = item["page"]
        try:
            source = item.get("source")
            page_title = item.get("page_title", "")
            speaker = item.get("speaker", "")
            if not source:
                source, page_title, page_speaker = source_from_page(page["page"], s)
                speaker = speaker or page_speaker
            if not source:
                print("Skipping: no video source", page["page"])
                continue
            path = out / f"video_{index:03d}.mp4"
            print(f"Downloading {index}: {speaker or '[unattributed]'} -> {path.name}")
            download(source, path, s)
            speaker = normalize_speaker(speaker)
            records.append({
                "index": index,
                "file": str(path),
                "page": page["page"],
                "source": source,
                "house": collection["house"],
                "source_id": collection["source_id"],
                "collection_title": collection["title"],
                "page_title": page_title,
                "speaker": speaker,
            })
            index += 1
        except Exception as exc:
            print("Download failed:", page["page"], exc)

    (out / "videos.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    named_count = sum(1 for item in records if item.get("speaker"))
    print(f"Downloaded {len(records)} Parliament videos from both Houses; speaker-attributed: {named_count}.")
    if len(records) < 4:
        raise RuntimeError("Too few Parliament videos downloaded for multi-story selection.")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4, 5):
        print("Usage: python src/download_multi.py <collections_json> <output_dir> [max_collections] [max_videos]")
        raise SystemExit(1)
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) >= 4 else 4, int(sys.argv[4]) if len(sys.argv) >= 5 else 20)
