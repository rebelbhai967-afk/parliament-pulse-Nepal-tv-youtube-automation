
import json
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://na.parliament.gov.np"


def discover_videos(output_path: str):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    url = f"{BASE_URL}/np/videos"

    print(f"Checking Nepal Parliament video archive: {url}")

    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    videos = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        title = link.get_text(" ", strip=True)

        if "/np/videos/" in href and title:
            if href.startswith("/"):
                full_url = BASE_URL + href
            else:
                full_url = href

            videos.append({
                "title": title,
                "url": full_url
            })

    # Remove duplicates
    unique_videos = []
    seen = set()

    for video in videos:
        if video["url"] not in seen:
            seen.add(video["url"])
            unique_videos.append(video)

    with open(output, "w", encoding="utf-8") as f:
        json.dump(
            unique_videos,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(f"Found {len(unique_videos)} video pages")
    print(f"Saved to: {output}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "Usage: python discover.py <output_json>"
        )
        sys.exit(1)

    discover_videos(sys.argv[1])


import json

import sys
from pathlib import Path

import yt_dlp


def discover_videos(query: str, output_path: str, limit: int = 10):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Searching YouTube for: {query}")

    options = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    }

    search_query = f"ytsearch{limit}:{query}"

    with yt_dlp.YoutubeDL(options) as ydl:
        result = ydl.extract_info(search_query, download=False)

    videos = []

    for entry in result.get("entries", []):
        if not entry:
            continue

        videos.append({
            "id": entry.get("id"),
            "title": entry.get("title"),
            "url": entry.get("url")
                or f"https://www.youtube.com/watch?v={entry.get('id')}",
            "channel": entry.get("channel"),
            "duration": entry.get("duration"),
        })

    with open(output, "w", encoding="utf-8") as f:
        json.dump(
            videos,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(f"Found {len(videos)} videos")
    print(f"Results saved to: {output}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python discover.py "
            '"search query" <output_json> [limit]'
        )
        sys.exit(1)

    query = sys.argv[1]
    output_path = sys.argv[2]

    limit = int(sys.argv[3]) if len(sys.argv) >= 4 else 10

    discover_videos(
        query,
        output_path,
        limit
    )
