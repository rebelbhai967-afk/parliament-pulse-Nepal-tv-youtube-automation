"""
YouTube uploader for Parliament Pulse Nepal TV.

Authentication:
- Uses OAuth 2.0.
- Local testing can use client_secret.json + token.json.
- GitHub Actions integration can be added later.

The uploader is intentionally separate from the video-generation pipeline.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

DEFAULT_CATEGORY_ID = "25"  # News & Politics

DEFAULT_PRIVACY = "private"


def load_credentials(client_secret_file, token_file):
    """
    Load existing OAuth token or start OAuth authorization.

    For the first local authorization:
        client_secret.json must exist.

    After authorization:
        token.json is reused.
    """

    credentials = None

    if os.path.exists(token_file):
        credentials = Credentials.from_authorized_user_file(
            token_file,
            SCOPES,
        )

    if credentials and credentials.valid:
        return credentials

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

        with open(token_file, "w", encoding="utf-8") as file:
            file.write(credentials.to_json())

        return credentials

    if not os.path.exists(client_secret_file):
        raise FileNotFoundError(
            f"OAuth client file not found: {client_secret_file}\n"
            "Create/download the OAuth client JSON first."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        client_secret_file,
        SCOPES,
    )

    credentials = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )

    with open(token_file, "w", encoding="utf-8") as file:
        file.write(credentials.to_json())

    return credentials


def build_youtube_service(credentials):
    """Create the YouTube API service."""

    return build(
        "youtube",
        "v3",
        credentials=credentials,
    )


def upload_video(
    youtube,
    video_file,
    title,
    description,
    tags=None,
    category_id=DEFAULT_CATEGORY_ID,
    privacy_status=DEFAULT_PRIVACY,
    made_for_kids=False,
    publish_at=None,
):
    """
    Upload one video to YouTube.
    """

    video_file = Path(video_file)

    if not video_file.exists():
        raise FileNotFoundError(
            f"Video file not found: {video_file}"
        )

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "categoryId": str(category_id),
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }
    if publish_at:
        if privacy_status != "private":
            raise ValueError("publish_at requires private privacyStatus")
        body["status"]["publishAt"] = publish_at

    if tags:
        body["snippet"]["tags"] = tags[:500]

    media = MediaFileUpload(
        str(video_file),
        chunksize=8 * 1024 * 1024,
        resumable=True,
        mimetype="video/*",
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None

    print(f"Uploading: {video_file}")

    while response is None:
        status, response = request.next_chunk()

        if status:
            progress = int(status.progress() * 100)
            print(f"Upload progress: {progress}%")

    video_id = response["id"]

    print(f"Upload complete: {video_id}")
    print(f"https://www.youtube.com/watch?v={video_id}")

    return response


def load_metadata(metadata_file):
    """
    Load upload metadata from JSON.
    """

    metadata_path = Path(metadata_file)

    if not metadata_path.exists():
        raise FileNotFoundError(
            f"Metadata file not found: {metadata_path}"
        )

    with open(metadata_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    return data


def main():
    parser = argparse.ArgumentParser(
        description="Upload a Parliament Pulse Nepal TV video to YouTube."
    )

    parser.add_argument(
        "video",
        help="Path to the video file",
    )

    parser.add_argument(
        "--title",
        required=True,
        help="YouTube video title",
    )

    parser.add_argument(
        "--description",
        default="",
        help="YouTube video description",
    )

    parser.add_argument(
        "--tags",
        default="",
        help="Comma-separated YouTube tags",
    )

    parser.add_argument(
        "--privacy",
        choices=["private", "unlisted", "public"],
        default=DEFAULT_PRIVACY,
        help="YouTube privacy status",
    )

    parser.add_argument(
        "--category",
        default=DEFAULT_CATEGORY_ID,
        help="YouTube category ID",
    )

    parser.add_argument(
        "--client-secret",
        default="client_secret.json",
        help="OAuth client secret JSON file",
    )

    parser.add_argument(
        "--token",
        default="token.json",
        help="OAuth token JSON file",
    )

    parser.add_argument(
        "--metadata",
        help="Optional metadata JSON file",
    )

    parser.add_argument(
        "--publish-at",
        default="",
        help="ISO-8601 publish time; video remains private until that time",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check inputs without uploading",
    )

    args = parser.parse_args()

    video_file = Path(args.video)

    if not video_file.exists():
        print(f"ERROR: Video not found: {video_file}")
        sys.exit(1)

    title = args.title
    description = args.description

    tags = [
        tag.strip()
        for tag in args.tags.split(",")
        if tag.strip()
    ]

    if args.metadata:
        metadata = load_metadata(args.metadata)

        title = metadata.get("title", title)
        description = metadata.get(
            "description",
            description,
        )

        metadata_tags = metadata.get("tags")

        if metadata_tags:
            tags = metadata_tags

    print()
    print("=== Parliament Pulse Nepal TV ===")
    print(f"Video: {video_file}")
    print(f"Title: {title}")
    print(f"Privacy: {args.privacy}")
    print(f"Tags: {len(tags)}")
    print()

    if args.dry_run:
        print("DRY RUN: no upload performed.")
        return

    try:
        credentials = load_credentials(
            args.client_secret,
            args.token,
        )

        youtube = build_youtube_service(credentials)

        response = upload_video(
            youtube=youtube,
            video_file=video_file,
            title=title,
            description=description,
            tags=tags,
            category_id=args.category,
            privacy_status=args.privacy,
            publish_at=args.publish_at or None,
        )

        print()
        print("=== YouTube Upload Result ===")
        print(json.dumps(response, ensure_ascii=False, indent=2))

    except Exception as error:
        print()
        print("YouTube upload failed:")
        print(str(error))
        sys.exit(1)


if __name__ == "__main__":
    main()
