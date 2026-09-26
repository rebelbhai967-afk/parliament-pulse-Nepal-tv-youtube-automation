import json
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def get_video_source(video_page_url: str):
    response = requests.get(
        video_page_url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # HTML5 video/source
    video = soup.find("video")

    if video:
        if video.get("src"):
            return urljoin(
                video_page_url,
                video["src"]
            )

        source = video.find("source")

        if source and source.get("src"):
            return urljoin(
                video_page_url,
                source["src"]
            )

    # Fallback: search source tags
    source = soup.find(
        "source",
        src=True
    )

    if source:
        return urljoin(
            video_page_url,
            source["src"]
        )

    return None


def download_video(
    video_page_url: str,
    output_dir: str
):
    output = Path(output_dir)
    output.mkdir(
        parents=True,
        exist_ok=True
    )

    print(
        f"Opening video page: {video_page_url}"
    )

    video_url = get_video_source(
        video_page_url
    )

    if not video_url:
        raise RuntimeError(
            "Could not find the actual video "
            "source on the Parliament page."
        )

    print(
        f"Video source found: {video_url}"
    )

    response = requests.get(
        video_url,
        stream=True,
        timeout=60,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    filename = video_url.split("/")[-1].split("?")[0]

    if not filename:
        filename = "parliament_video.mp4"

    output_file = output / filename

    with open(
        output_file,
        "wb"
    ) as file:

        for chunk in response.iter_content(
            chunk_size=1024 * 1024
        ):
            if chunk:
                file.write(chunk)

    print(
        f"Video saved to: {output_file}"
    )

    return str(output_file)


if __name__ == "__main__":

    if len(sys.argv) != 3:
        print(
            "Usage: python download.py "
            "<video_page_url> <output_directory>"
        )
        sys.exit(1)

    download_video(
        sys.argv[1],
        sys.argv[2]
    )
