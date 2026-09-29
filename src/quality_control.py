import json
import subprocess
import sys
from pathlib import Path


def probe_duration(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {path}")
    return float(result.stdout.strip())


def check_video(path, minimum, maximum, expected_width=None, expected_height=None):
    if not path.exists() or path.stat().st_size < 10_000:
        raise RuntimeError(f"Missing or suspiciously small video: {path}")
    duration = probe_duration(path)
    if not minimum <= duration <= maximum:
        raise RuntimeError(
            f"Rendered duration outside rule: {path.name} = {duration:.1f}s "
            f"(expected {minimum}-{maximum}s)"
        )
    if expected_width and expected_height:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                str(path),
            ],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe dimensions failed: {path}")
        dimensions = result.stdout.strip()
        expected = f"{expected_width}x{expected_height}"
        if dimensions != expected:
            raise RuntimeError(
                f"Wrong dimensions: {path.name} = {dimensions}, expected {expected}"
            )
    return duration


def clean_list(values):
    return {
        str(v).strip().lower()
        for v in values
        if str(v).strip()
    }


def main(selection_path, masters_dir, thumbnails_dir):
    selection = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    masters = Path(masters_dir)
    thumbs = Path(thumbnails_dir)

    longs = selection.get("long_stories", [])
    shorts = selection.get("short_stories", [])

    errors = []

    if len(longs) != 12:
        errors.append(f"Expected exactly 12 long stories, found {len(longs)}")
    if len(shorts) != 12:
        errors.append(f"Expected exactly 12 short stories, found {len(shorts)}")

    long_speakers = set()
    short_speakers = set()
    used_long_sources = set()
    used_short_sources = set()

    for i, story in enumerate(longs, 1):
        path = masters / f"long_{i:02d}.mp4"
        try:
            duration = check_video(path, 181, 600, 1920, 1080)
            print(f"LONG {i:02d}: {duration:.1f}s OK")
        except Exception as exc:
            errors.append(str(exc))

        speakers = clean_list(story.get("speakers", []))
        long_speakers.update(speakers)
        for piece in story.get("pieces", []):
            source = str(piece.get("video", piece.get("source_video", ""))).strip()
            if source:
                used_long_sources.add(source)

        thumb = thumbs / f"long_{i:02d}.jpg"
        if not thumb.exists() or thumb.stat().st_size < 5_000:
            errors.append(f"Missing thumbnail: {thumb}")

    for i, story in enumerate(shorts, 1):
        path = masters / f"short_{i:02d}.mp4"
        try:
            duration = check_video(path, 1, 89.999, 1080, 1920)
            print(f"SHORT {i:02d}: {duration:.1f}s OK")
        except Exception as exc:
            errors.append(str(exc))

        speaker = str(story.get("speaker", "")).strip()
        if speaker:
            short_speakers.add(speaker.lower())

        source = str(
            story.get("video", story.get("source_video", ""))
        ).strip()
        if source:
            used_short_sources.add(source)

        thumb = thumbs / f"short_{i:02d}.jpg"
        if not thumb.exists() or thumb.stat().st_size < 5_000:
            errors.append(f"Missing thumbnail: {thumb}")

    if len(used_short_sources) < min(12, len(shorts)):
        errors.append(
            f"Short-source diversity is low: {len(used_short_sources)} unique sources"
        )

    duplicate_speakers = [
        s for s in short_speakers
        if s in long_speakers and s not in {"", "parliament", "nepal parliament"}
    ]
    if duplicate_speakers:
        print(
            "NOTICE: speakers appear in both long and short pools: "
            + ", ".join(sorted(duplicate_speakers)[:10])
        )

    if errors:
        print("")
        print("QUALITY CONTROL FAILED")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    report = {
        "status": "passed",
        "long_count": len(longs),
        "short_count": len(shorts),
        "unique_long_speakers": len(long_speakers),
        "unique_short_speakers": len(short_speakers),
        "unique_long_sources": len(used_long_sources),
        "unique_short_sources": len(used_short_sources),
    }
    report_path = masters / "quality_control_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("")
    print("QUALITY CONTROL PASSED")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: python src/quality_control.py "
            "<selection_json> <masters_dir> <thumbnails_dir>"
        )
    main(*sys.argv[1:])
