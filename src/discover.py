import json
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SOURCES = [
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


def discover(output_path):
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0"}
    collections = []
    seen = set()
    source_failures = []

    for source in SOURCES:
        response = None
        last_error = None
        # Official Parliament sites can temporarily refuse connections. Retry a
        # small, bounded number of times instead of failing on the first blip.
        for attempt in range(1, 4):
            try:
                response = requests.get(
                    source["url"], headers=headers, timeout=(10, 30), verify=False
                )
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                last_error = exc
                print(
                    f"WARNING: {source['house']} source attempt {attempt}/3 failed: {exc}",
                    file=sys.stderr,
                )
                if attempt < 3:
                    time.sleep(attempt * 5)
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
            title = link.get_text(" ", strip=True)
            collections.append({
                "source_id": source["id"],
                "house": source["house"],
                "title": title,
                "url": full,
                "source_index": len(collections),
            })

    found_houses = {item["house"] for item in collections}
    required_houses = {source["house"] for source in SOURCES}
    missing_houses = sorted(required_houses - found_houses)
    if source_failures or missing_houses:
        details = "; ".join(source_failures) if source_failures else "No collection links found"
        missing = ", ".join(missing_houses) if missing_houses else "none"
        raise RuntimeError(
            "Parliament discovery incomplete; refusing to build a misleading one-House batch. "
            f"Missing Houses: {missing}. Source errors: {details}"
        )

    result = {
        "sources": SOURCES,
        "collections": collections,
        "selection_policy": "latest collections from both Houses; never treat one House as the whole Parliament",
    }
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Discovered {len(collections)} collections across {len(SOURCES)} Houses.")
    for item in collections[:12]:
        print(item["house"], "|", item["title"], "|", item["url"])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python src/discover.py <output_json>")
        raise SystemExit(1)
    discover(sys.argv[1])
