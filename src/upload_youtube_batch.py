import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_upload(video, item, client_secret, token, privacy, publish_at):
    command = [
        sys.executable, "src/youtube_upload.py", str(video),
        "--title", str(item.get("title", "")),
        "--description", str(item.get("description", "")),
        "--tags", ",".join(item.get("tags", [])),
        "--privacy", privacy,
        "--client-secret", client_secret,
        "--token", token,
    ]
    if publish_at:
        command += ["--publish-at", publish_at]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    marker = "=== YouTube Upload Result ==="
    output = result.stdout or ""
    if marker not in output:
        raise RuntimeError(f"YouTube upload returned no API result for {video}")
    raw = output.split(marker, 1)[1].strip()
    try:
        response = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse YouTube upload response for {video}: {exc}") from exc
    return response


def main(masters, metadata_dir, client_secret, token, privacy, kind, publish_at):
    masters = Path(masters)
    metadata_dir = Path(metadata_dir)
    items = json.loads((metadata_dir / f"{kind}_metadata.json").read_text(encoding="utf-8"))

    results = []
    for item in items:
        index = int(item["index"])
        video = masters / f"{kind}_{index:02d}.mp4"
        if not video.exists():
            raise FileNotFoundError(video)

        print(f"\n=== YouTube {kind.upper()} {index:02d} ===")
        response = run_upload(video, item, client_secret, token, privacy, publish_at)
        results.append({
            "index": index,
            "video": str(video),
            "status": "uploaded_private_scheduled" if publish_at else "uploaded",
            "youtube_video_id": response.get("id"),
            "youtube_url": (
                f"https://www.youtube.com/watch?v={response.get('id')}"
                if response.get("id") else ""
            ),
            "publish_at": publish_at or "",
        })

    (masters / f"youtube_{kind}_upload_report.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Uploaded {len(results)} {kind} videos.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("masters")
    parser.add_argument("metadata_dir")
    parser.add_argument("--client-secret", default="client_secret.json")
    parser.add_argument("--token", default="token.json")
    parser.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    parser.add_argument("--kind", choices=["long", "short"], required=True)
    parser.add_argument("--publish-at", default="")
    args = parser.parse_args()
    main(args.masters, args.metadata_dir, args.client_secret, args.token, args.privacy, args.kind)
