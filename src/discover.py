import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DIGITAL_URL = "https://digital.parliament.gov.np/baithak"
LEGACY_SOURCES = [
    {
        "id": "national_assembly",
        "house": "National Assembly",
        "url": "https://na.parliament.gov.np/np/videos",
        "host": "https://na.parliament.gov.np",
        "video_prefix": "/np/video/",
        "collection_prefix": "/np/videos/",
    },
    {
        "id": "house_of_representatives",
        "house": "House of Representatives",
        "url": "https://hr.parliament.gov.np/en/videos",
        "host": "https://hr.parliament.gov.np",
        "video_prefix": "/en/video/",
        "collection_prefix": "/en/videos/",
    },
]


def digital_house(text):
    value = re.sub(r"\s+", " ", text or "")
    if "समिति" in value or "committee" in value.lower() or "संयुक्त" in value:
        return ""
    if "राष्ट्रिय सभा" in value or "National Assembly" in value:
        return "National Assembly"
    if "प्रतिनिधि सभा" in value or "House of Representatives" in value:
        return "House of Representatives"
    return ""


def discover_digital(session, headers):
    """Discover official meeting pages, classifying from detail pages when cards omit House names."""
    response = session.get(DIGITAL_URL, headers=headers, timeout=(10, 35))
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    seen = set()
    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if "/baithak-detail/" not in href:
            continue
        full = urljoin(DIGITAL_URL, href)
        if full in seen:
            continue
        seen.add(full)
        parent_text = link.parent.get_text(" ", strip=True) if link.parent else ""
        title = re.sub(r"\s+", " ", link.get_text(" ", strip=True) or parent_text).strip()
        candidates.append((full, title, parent_text))

    collections = []
    for full, title, parent_text in candidates:
        # The archive cards often omit the House label; inspect the official meeting detail page.
        house = digital_house(" ".join((title, parent_text)))
        detail_text = ""
        if not house:
            try:
                detail = session.get(full, headers=headers, timeout=(10, 25))
                detail.raise_for_status()
                detail_soup = BeautifulSoup(detail.text, "html.parser")
                for tag in detail_soup(["script", "style", "noscript", "svg"]):
                    tag.decompose()
                detail_text = re.sub(r"\s+", " ", detail_soup.get_text(" ", strip=True))
                # Prefer explicit meeting metadata/headings over generic page-wide text.
                headings = " ".join(x.get_text(" ", strip=True) for x in detail_soup.find_all(["h1", "h2", "h3", "title"]))
                house = digital_house(headings)
                if not house:
                    house = digital_house(detail_text[:1800])
                if not title or title == full:
                    title = headings[:220] or detail_soup.title.get_text(" ", strip=True) if detail_soup.title else title
            except requests.RequestException as exc:
                print(f"WARNING: Could not inspect official meeting page {full}: {exc}", file=sys.stderr)
                continue
        if not house:
            # Never guess the House when the official page does not identify it.
            continue
        source_id = "national_assembly" if house == "National Assembly" else "house_of_representatives"
        collections.append({
            "source_id": source_id,
            "house": house,
            "title": re.sub(r"\s+", " ", title or parent_text or house).strip()[:240],
            "url": full,
            "source_index": len(collections),
            "platform": "digital_parliament",
        })

    found = {item["house"] for item in collections}
    required = {"National Assembly", "House of Representatives"}
    missing = sorted(required - found)
    if missing:
        raise RuntimeError(
            "Official Digital Parliament archive did not expose both Houses after checking meeting detail pages. "
            f"Missing: {', '.join(missing)}; found {len(collections)} classifiable meeting pages "
            f"from {len(candidates)} archive links."
        )
    return collections

def discover_legacy(session, headers):
    collections = []
    seen = set()
    source_failures = []
    for source in LEGACY_SOURCES:
        response = None
        last_error = None
        for attempt in range(1, 4):
            try:
                response = session.get(source["url"], headers=headers, timeout=(10, 30), verify=False)
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                last_error = exc
                print(
                    f"WARNING: {source['house']} legacy source attempt {attempt}/3 failed: {exc}",
                    file=sys.stderr,
                )
                if attempt < 3:
                    time.sleep(attempt * 3)
        if response is None or not response.ok:
            source_failures.append(f'{source["house"]} ({source["url"]}): {last_error}')
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link.get("href", "").strip()
            if not href:
                continue
            full = urljoin(source["host"], href)
            if source["collection_prefix"] not in full or full in seen:
                continue
            seen.add(full)
            collections.append({
                "source_id": source["id"],
                "house": source["house"],
                "title": link.get_text(" ", strip=True),
                "url": full,
                "source_index": len(collections),
                "platform": "legacy_parliament",
            })
    found = {item["house"] for item in collections}
    required = {source["house"] for source in LEGACY_SOURCES}
    missing = sorted(required - found)
    if source_failures or missing:
        details = "; ".join(source_failures) if source_failures else "No collection links found"
        raise RuntimeError(
            "Both official discovery routes failed. "
            f"Missing Houses: {', '.join(missing)}. Legacy errors: {details}"
        )
    return collections


def discover(output_path):
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ParliamentPulseNepal/1.0)"}
    session = requests.Session()
    session.headers.update(headers)

    # Prefer the legacy official video archives first. The last successful
    # end-to-end build used these per-video official pages; the newer Digital
    # Parliament meeting archive often links to YouTube for recordings, which
    # GitHub-hosted runners may block with bot verification. Digital Parliament
    # remains a fallback if either legacy House archive is unavailable.
    try:
        collections = discover_legacy(session, headers)
        platform = "legacy_parliament"
        print(f"Using legacy official archives: {len(collections)} collections.")
    except (requests.RequestException, RuntimeError) as legacy_exc:
        print(f"WARNING: Legacy official archives unavailable: {legacy_exc}", file=sys.stderr)
        collections = discover_digital(session, headers)
        platform = "digital_parliament"
        print(f"Using official Digital Parliament archive: {len(collections)} meeting pages.")

    result = {
        "sources": LEGACY_SOURCES,
        "collections": collections,
        "platform": platform,
        "selection_policy": "latest official meeting pages from both Houses; never treat one House as the whole Parliament",
    }
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    houses = sorted({item["house"] for item in collections})
    print(f"Discovered {len(collections)} official collections across: {', '.join(houses)}.")
    for item in collections[:12]:
        print(item["house"], "|", item["title"][:100], "|", item["url"])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python src/discover.py <output_json>")
        raise SystemExit(1)
    discover(sys.argv[1])
