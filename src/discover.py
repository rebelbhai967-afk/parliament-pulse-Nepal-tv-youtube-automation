import json
import sys
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

    for source in SOURCES:
        response = requests.get(source["url"], headers=headers, timeout=30, verify=False)
        response.raise_for_status()
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
