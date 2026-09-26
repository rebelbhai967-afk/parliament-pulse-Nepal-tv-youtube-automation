import json
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)

BASE_URL = "https://na.parliament.gov.np"


def discover_videos(output_path: str):

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    urls = [
        f"{BASE_URL}/index.php/np/today-parliament",
        f"{BASE_URL}/np/videos",
    ]

    videos = []
    seen = set()

    for page_url in urls:

        print(f"Checking: {page_url}")

        response = requests.get(
            page_url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            verify=False
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for link in soup.find_all("a", href=True):

            href = link.get("href", "").strip()

            title = link.get_text(
                " ",
                strip=True
            )

            if not href:
                continue

            full_url = urljoin(
                BASE_URL,
                href
            )

            # Parliament video collection
            if "/np/videos/" in full_url:

                if full_url not in seen:

                    seen.add(full_url)

                    videos.append({
                        "title": title,
                        "url": full_url,
                        "source": page_url
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


    print(
        f"Found {len(videos)} video collections"
    )

    print(
        f"Saved to: {output}"
    )


if __name__ == "__main__":

    if len(sys.argv) != 2:

        print(
            "Usage: python discover.py <output_json>"
        )

        sys.exit(1)


    discover_videos(
        sys.argv[1]
    )
