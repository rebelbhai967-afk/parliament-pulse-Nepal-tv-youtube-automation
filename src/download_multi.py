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
    return re.sub(r"\\s+", " ", str(value or "")).strip()


def speaker_from_link(text):
    text = clean(text)
    text = re.sub(r"^video\\s*-\\s*", "", text, flags=re.I)
    text = re.sub(r"^(मा\\.?|माननीय|hon\\.?|honorable)\\s+", "", text, flags=re.I)
    return text.strip()


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
    title = clean((soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else soup.title.get_text(" ", strip=True) if soup.title else ""))
    for tag in soup.find_all(["video", "source", "iframe"]):
        for attr in ["src", "data-src", "data-video"]:
            value = clean(tag.get(attr))
            if value and (".mp4" in value.lower() or ".m3u8" in value.lower() or "video" in value.lower()):
                return urljoin(page_url, value), title
    return None, title


def download(url, path, s):
    with s.get(url, stream=True, timeout=180, verify=False) as response:
        response.raise_for_status()
        with open(path, "wb") as f:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)


def main(collections_json, output_dir, max_collections=4, max_videos=20):
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
    selected = []
    counts = {}
    for item in collections:
        n = counts.get(item["source_id"], 0)
        if n < 2:
            selected.append(item)
            counts[item["source_id"]] = n + 1

    s = session()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = []
    index = 1

    for collection in selected:
        pages = video_pages(collection, s)
        print(f"{collection['house']}: {len(pages)} videos in {collection['title']}")
        for page in pages:
            if len(records) >= max_videos:
                break
            try:
                source, page_title = source_from_page(page["page"], s)
                if not source:
                    print("Skipping: no video source", page["page"])
                    continue
                path = out / f"video_{index:03d}.mp4"
                print(f"Downloading {index}: {page['speaker']} -> {path.name}")
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
                    "speaker": page["speaker"],
                })
                index += 1
            except Exception as exc:
                print("Download failed:", page["page"], exc)
        if len(records) >= max_videos:
            break

    (out / "videos.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Downloaded {len(records)} Parliament videos from both Houses.")
    if len(records) < 4:
        raise RuntimeError("Too few Parliament videos downloaded for multi-story selection.")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4, 5):
        print("Usage: python src/download_multi.py <collections_json> <output_dir> [max_collections] [max_videos]")
        raise SystemExit(1)
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) >= 4 else 4, int(sys.argv[4]) if len(sys.argv) >= 5 else 20)
