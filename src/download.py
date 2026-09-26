import sys
from pathlib import Path

import yt_dlp


def download_video(url: str, output_dir: str):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    options = {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "outtmpl": str(output / "%(id)s.%(ext)s"),
    }

    print(f"Downloading: {url}")

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    print(f"Download completed: {output}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python download.py "
            "<youtube_url> <output_directory>"
        )
        sys.exit(1)

    download_video(
        sys.argv[1],
        sys.argv[2]
    )
