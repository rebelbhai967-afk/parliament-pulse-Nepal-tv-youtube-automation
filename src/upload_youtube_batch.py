import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_upload(video, metadata, client_secret, token, privacy):
    command = [
        sys.executable, "src/youtube_upload.py", str(video),
        "--metadata", str(metadata),
        "--privacy", privacy,
        "--client-secret", client_secret,
        "--token", token,
    ]
    subprocess.run(command, check=True)


def main(masters, metadata_dir, client_secret, token, privacy, kind):
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
        run_upload(video, metadata_dir / f"{kind}_{index:02d}_upload.json", client_secret, token, privacy)
        results.append({"index": index, "video": str(video), "status": "uploaded"})

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
    args = parser.parse_args()
    main(args.masters, args.metadata_dir, args.client_secret, args.token, args.privacy, args.kind)
