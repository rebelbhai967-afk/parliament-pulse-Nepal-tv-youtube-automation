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
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/120.0 Safari/537.36"
        )
    })

    return session


def get_video_pages(
    collection_url,
    session
):
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

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link.get(
            "href",
            ""
        ).strip()

        if not href:
            continue

        full_url = urljoin(
            BASE_URL,
            href
        )

        if (
            "/np/video/" in full_url
            or "/en/video/" in full_url
        ):

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


def get_video_source(
    video_page_url,
    session
):
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

    video = soup.find(
        "video"
    )

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

    source = soup.find(
        "source",
        src=True
    )

    if source:

        return urljoin(
            video_page_url,
            source["src"]
        )

    for tag in soup.find_all(
        [
            "video",
            "source",
            "iframe"
        ]
    ):

        for attribute in [
            "src",
            "data-src",
            "data-video"
        ]:

            value = tag.get(
                attribute
            )

            if not value:
                continue

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
    print("")
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

    output_path = Path(
        output_file
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        output_path,
        "wb"
    ) as file:

        for chunk in response.iter_content(
            chunk_size=1024 * 1024
        ):

            if chunk:
                file.write(chunk)

    size = output_path.stat().st_size

    print(
        f"Saved: {output_path}"
    )

    print(
        f"Size: "
        f"{size / (1024 * 1024):.2f} MB"
    )


def download_collection(
    collection_url,
    output_dir,
    max_videos=10
):
    output = Path(
        output_dir
    )

    output.mkdir(
        parents=True,
        exist_ok=True
    )

    session = get_session()

    print("")
    print(
        "===================================="
    )

    print(
        "Opening Parliament collection:"
    )

    print(
        collection_url
    )

    print(
        "===================================="
    )

    video_pages = get_video_pages(
        collection_url,
        session
    )

    print("")
    print(
        f"Found {len(video_pages)} "
        f"Parliament videos"
    )

    if max_videos is not None:

        video_pages = video_pages[
            :max_videos
        ]

        print(
            f"Processing first "
            f"{len(video_pages)} videos"
        )

    results = []

    for index, video in enumerate(
        video_pages,
        start=1
    ):

        print("")
        print(
            "------------------------------------"
        )

        print(
            f"VIDEO {index}/{len(video_pages)}"
        )

        print(
            f"Title: {video['title']}"
        )

        print(
            f"Page: {video['url']}"
        )

        print(
            "------------------------------------"
        )

        try:

            source = get_video_source(
                video["url"],
                session
            )

            if not source:

                print(
                    "Video source not found."
                )

                continue

            filename = (
                f"video_{index:03d}.mp4"
            )

            output_file = (
                output / filename
            )

            download_file(
                source,
                output_file,
                session
            )

            result = {
                "index": index,
                "title": video["title"],
                "page": video["url"],
                "source": source,
                "file": str(
                    output_file
                )
            }

            results.append(
                result
            )

            print(
                "DOWNLOAD PASSED"
            )

        except Exception as error:

            print(
                f"Download failed: "
                f"{error}"
            )

    metadata_file = (
        output / "videos.json"
    )

    with open(
        metadata_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            results,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("")
    print(
        "===================================="
    )

    print(
        "PARLIAMENT DOWNLOAD SUMMARY"
    )

    print(
        "===================================="
    )

    print(
        f"Successful videos: "
        f"{len(results)}"
    )

    print(
        f"Metadata: "
        f"{metadata_file}"
    )

    return results


if __name__ == "__main__":

    if len(sys.argv) not in [
        3,
        4
    ]:

        print("Usage:")

        print(
            "python download.py "
            "<collection_url> "
            "<output_directory> "
            "[max_videos]"
        )

        sys.exit(1)

    collection_url = sys.argv[1]

    output_dir = sys.argv[2]

    max_videos = 10

    if len(sys.argv) == 4:

        max_videos = int(
            sys.argv[3]
        )

    results = download_collection(
        collection_url,
        output_dir,
        max_videos
    )

    print("")
    print(
        f"Completed: "
        f"{len(results)} videos"
    )
