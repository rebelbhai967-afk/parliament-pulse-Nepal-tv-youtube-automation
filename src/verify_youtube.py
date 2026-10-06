import argparse
import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main(report_dir, token_file):
    reports = sorted(Path(report_dir).glob("youtube_*_upload_report.json"))
    if not reports:
        raise RuntimeError("No YouTube upload reports found.")

    credentials = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not credentials.valid:
        raise RuntimeError("YouTube OAuth credentials are not valid for verification.")

    youtube = build("youtube", "v3", credentials=credentials)
    ids = []
    expected = {}
    for report in reports:
        for item in json.loads(report.read_text(encoding="utf-8")):
            video_id = str(item.get("youtube_video_id", "")).strip()
            if not video_id:
                raise RuntimeError(f"Missing YouTube video ID in {report.name}")
            ids.append(video_id)
            expected[video_id] = item

    response = youtube.videos().list(
        part="id,status,processingDetails,snippet",
        id=",".join(ids),
    ).execute()
    found = {item["id"]: item for item in response.get("items", [])}

    if set(found) != set(ids):
        missing = sorted(set(ids) - set(found))
        raise RuntimeError(f"YouTube verification could not find uploaded video IDs: {missing}")

    results = []
    for video_id in ids:
        item = found[video_id]
        status = item.get("status", {})
        processing = item.get("processingDetails", {})
        results.append({
            "youtube_video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "upload_status": status.get("uploadStatus", ""),
            "privacy_status": status.get("privacyStatus", ""),
            "publish_at": status.get("publishAt", ""),
            "processing_status": processing.get("processingStatus", ""),
            "expected_publish_at": expected[video_id].get("publish_at", ""),
            "title": item.get("snippet", {}).get("title", ""),
        })

        if status.get("uploadStatus") in {"failed", "rejected", "deleted"}:
            raise RuntimeError(
                f"YouTube rejected/failed video {video_id}: "
                f"{status.get('failureReason') or status.get('rejectionReason') or status.get('uploadStatus')}"
            )
        if status.get("privacyStatus") != "private":
            raise RuntimeError(f"YouTube video {video_id} is not private after scheduled upload.")

    output = Path(report_dir) / "youtube_verification_report.json"
    output.write_text(json.dumps({
        "status": "verified",
        "items": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "verified", "items": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir")
    parser.add_argument("--token", default="token.json")
    args = parser.parse_args()
    main(args.report_dir, args.token)
