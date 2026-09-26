import json
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://na.parliament.gov.np"


def discover_videos(output_path: str):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    archive_url = f"{BASE_URL}/np/videos"

    print(f"Checking: {archive_url}")

    response = requests.get(
        archive_url,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    videos = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        title = link.get_text(" ", strip=True)

        if "/np/video/" in href or "/en/video/" in href:
            video_url = urljoin(BASE_URL, href)

            if video_url not in seen:
                seen.add(video_url)

                videos.append({
                    "title": title,
                    "url": video_url
                })

    with open(
        output,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            videos,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(f"Found {len(videos)} videos")
    print(f"Saved to: {output}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "Usage: python discover.py <output_json>"
        )
        sys.exit(1)

    discover_videos(sys.argv[1])
