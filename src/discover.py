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
    response = session.get(DIGITAL_URL, headers=headers, timeout=(10, 35))
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    collections = []
    seen = set()
    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if "/baithak-detail/" not in href:
            continue
        full = urljoin(DIGITAL_URL, href)
        if full in seen:
            continue
        parent_text = link.parent.get_text(" ", strip=True) if link.parent else ""
        label = " ".join((link.get_text(" ", strip=True), parent_text))
        house = digital_house(label)
        if not house:
            continue
        seen.add(full)
        source_id = "national_assembly" if house == "National Assembly" else "house_of_representatives"
        title = link.get_text(" ", strip=True) or parent_text[:220] or house
        collections.append({
            "source_id": source_id,
            "house": house,
            "title": re.sub(r"\s+", " ", title).strip(),
            "url": full,
            "source_index": len(collections),
            "platform": "digital_parliament",
        })
    found = {item["house"] for item in collections}
    required = {"National Assembly", "House of Representatives"}
    missing = sorted(required - found)
    if missing:
        raise RuntimeError(
            "Official Digital Parliament archive did not expose both Houses. "
            f"Missing: {', '.join(missing)}; found {len(collections)} meeting pages."
        )
    # Preserve source order from the official archive; downstream code balances Houses.
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

    try:
        collections = discover_digital(session, headers)
        platform = "digital_parliament"
        print(f"Using official Digital Parliament archive: {len(collections)} meeting pages.")
    except (requests.RequestException, RuntimeError) as exc:
        print(f"WARNING: Digital Parliament discovery unavailable: {exc}", file=sys.stderr)
        collections = discover_legacy(session, headers)
        platform = "legacy_parliament"
        print(f"Using legacy official archives: {len(collections)} collections.")

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
