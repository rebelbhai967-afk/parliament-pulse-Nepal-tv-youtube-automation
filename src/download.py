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


def get_session():
    session = requests.Session()

    session.headers.update({
        "User-Agent": "Mozilla/5.0"
    })

    return session


def get_video_pages(collection_url, session):
    response = session.get(
        collection_url,
        timeout=30,
        verify=False
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    videos = []
    seen = set()

    for link in soup.find_all("a", href=True):

        href = link.get("href", "").strip()

        if not href:
            continue

        full_url = urljoin(
            BASE_URL,
            href
        )

        # Individual Parliament video
        if "/np/video/" in full_url or "/en/video/" in full_url:

            if full_url in seen:
                continue

            seen.add(full_url)

            title = link.get_text(
                " ",
                strip=True
            )

            videos.append({
                "title": title,
                "url": full_url
            })

    return videos


def get_video_source(video_page_url, session):

    response = session.get(
        video_page_url,
        timeout=30,
        verify=False
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # HTML5 video
    video = soup.find("video")

    if video:

        if video.get("src"):
            return urljoin(
                video_page_url,
                video["src"]
            )

        source = video.find(
            "source",
            src=True
        )

        if source:
            return urljoin(
                video_page_url,
                source["src"]
            )

    # Any source tag
    source = soup.find(
        "source",
        src=True
    )

    if source:
        return urljoin(
            video_page_url,
            source["src"]
        )

    # Search common video attributes
    for tag in soup.find_all(
        ["video", "source", "iframe"]
    ):

        for attribute in [
            "src",
            "data-src",
            "data-video"
        ]:

            value = tag.get(attribute)

            if value:
                value = value.strip()

                if (
                    ".mp4" in value.lower()
                    or ".m3u8" in value.lower()
                    or "video" in value.lower()
                ):
                    return urljoin(
                        video_page_url,
                        value
                    )

    return None


def download_file(
    video_url,
    output_file,
    session
):

    print(
        f"Downloading: {video_url}"
    )

    response = session.get(
        video_url,
        stream=True,
        timeout=120,
        verify=False
    )

    response.raise_for_status()

    with open(
        output_file,
        "wb"
    ) as file:

        for chunk in response.iter_content(
            chunk_size=1024 * 1024
        ):

            if chunk:
                file.write(chunk)


def download_collection(
    collection_url,
    output_dir
):

    output = Path(output_dir)

    output.mkdir(
        parents=True,
        exist_ok=True
    )

    session = get_session()

    print(
        f"Opening collection: {collection_url}"
    )

    video_pages = get_video_pages(
        collection_url,
        session
    )

    print(
        f"Found {len(video_pages)} videos"
    )

    results = []

    for index, video in enumerate(
        video_pages,
        start=1
    ):

        print(
            f"\nVideo {index}/{len(video_pages)}"
        )

        print(
            f"Title: {video['title']}"
        )

        source = get_video_source(
            video["url"],
            session
        )

        if not source:

            print(
                "Video source not found"
            )

            continue

        filename = (
            f"video_{index:03d}.mp4"
        )

        output_file = (
            output / filename
        )

        try:

            download_file(
                source,
                output_file,
                session
            )

            results.append({
                "title": video["title"],
                "page": video["url"],
                "source": source,
                "file": str(output_file)
            })

            print(
                f"Saved: {output_file}"
            )

        except Exception as error:

            print(
                f"Download failed: {error}"
            )

    return results


if __name__ == "__main__":

    if len(sys.argv) != 3:

        print(
            "Usage:"
        )

        print(
            "python download.py "
            "<collection_url> "
            "<output_directory>"
        )

        sys.exit(1)

    collection_url = sys.argv[1]
    output_dir = sys.argv[2]

    results = download_collection(
        collection_url,
        output_dir
    )

    print(
        f"\nCompleted: {len(results)} videos"
    )
