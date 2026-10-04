import json
import subprocess
import sys
import re
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


def has_audio(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True
    )
    return result.returncode == 0 and bool(result.stdout.strip())




def subtitle_stats(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    cues = []
    current = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if current:
                cues.append(" ".join(current))
                current = []
            continue
        if "-->" in line or line.isdigit():
            continue
        current.append(line)
    if current:
        cues.append(" ".join(current))
    joined = " ".join(cues)
    letters = [ch for ch in joined if ch.isalpha()]
    latin = [ch for ch in letters if ("A" <= ch <= "Z") or ("a" <= ch <= "z")]
    ratio = (len(latin) / len(letters)) if letters else 0.0
    return len(cues), ratio


def validate_subtitles(selection, subtitles_dir, errors):
    subtitles = Path(subtitles_dir)
    checked = set()
    for kind in ("long", "short"):
        for i, story in enumerate(selection.get(f"{kind}_stories", []), 1):
            for piece in story.get("pieces", []):
                video = str(piece.get("video", "")).strip()
                if not video:
                    continue
                stem = Path(video).stem
                if stem in checked:
                    continue
                checked.add(stem)
                path = subtitles / f"{stem}.srt"
                if not path.exists():
                    errors.append(f"{kind.title()} {i}: missing English subtitle file for {stem}")
                    continue
                cue_count, latin_ratio = subtitle_stats(path)
                if cue_count == 0:
                    errors.append(f"{kind.title()} {i}: empty subtitle file for {stem}")
                elif latin_ratio < 0.55:
                    errors.append(
                        f"{kind.title()} {i}: subtitle file for {stem} is not English-first "
                        f"(Latin-letter ratio {latin_ratio:.2f})"
                    )


def max_silence_seconds(path):
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path),
            "-af", "silencedetect=noise=-35dB:d=5",
            "-f", "null", "-"
        ],
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    import re
    durations = []
    for match in re.finditer(r"silence_duration:\s*([0-9.]+)", output):
        durations.append(float(match.group(1)))
    return max(durations, default=0.0)


def looks_garbled_english(text):
    """Reject obvious machine-translation corruption without judging normal prose."""
    value = " ".join(str(text or "").split())
    for token in re.findall(r"[A-Za-z]{16,}", value):
        lowered = token.lower()
        # Repeated 3-6 character chunks are a strong signal of corruption such as
        # PROFRIBESTRIBSTRIB; normal English rarely repeats the same chunk 3+ times.
        for size in range(3, 7):
            chunks = [lowered[i:i + size] for i in range(0, len(lowered) - size + 1)]
            repeated = {chunk for chunk in chunks if lowered.count(chunk) >= 3}
            if repeated:
                return True
    return False


def validate_english_quality(selection, subtitles_dir, errors):
    subtitles = Path(subtitles_dir)
    checked = set()
    for kind in ("long", "short"):
        for i, story in enumerate(selection.get(f"{kind}_stories", []), 1):
            for piece in story.get("pieces", []):
                video = str(piece.get("video", "")).strip()
                if not video:
                    continue
                stem = Path(video).stem
                if stem in checked:
                    continue
                checked.add(stem)
                path = subtitles / f"{stem}.srt"
                if not path.exists():
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if looks_garbled_english(text):
                    errors.append(f"{kind.title()} {i}: garbled English subtitle detected in {stem}")


def clean_list(values):
    return {
        str(v).strip().lower()
        for v in values
        if str(v).strip()
    }


def main(selection_path, masters_dir, thumbnails_dir, subtitles_dir):
    selection = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    masters = Path(masters_dir)
    thumbs = Path(thumbnails_dir)

    longs = selection.get("long_stories", [])
    shorts = selection.get("short_stories", [])

    errors = []

    validate_subtitles(selection, subtitles_dir, errors)
    validate_english_quality(selection, subtitles_dir, errors)

    if len(longs) != 2:
        errors.append(f"Expected exactly 2 long stories, found {len(longs)}")
    if len(shorts) != 2:
        errors.append(f"Expected exactly 2 short stories, found {len(shorts)}")

    long_speakers = set()
    short_speakers = set()
    long_houses = set()
    generic_speakers = {
        "", "zero hour", "special hour", "jawaf", "prastav prastut",
        "download on app store", "download on the app store", "get it on google play",
        "get it on google play store", "app store", "google play", "download on play store", "download on the play store",
        "get it on play store", "get it on the play store", "play store", "watch on youtube",
        "ninrnayartha prastut", "nirdeshan", "samjhauta pes", "summary",
        "first meeting", "meeting", "sammananiye sabhamukh", "video",
        "watch video", "pratibedan pes", "pratibedhan pes", "national anthem",
        "bidhyak prastut", "सम्माननीय अध्यक्ष", "शून्य समय",
    }
    used_long_sources = set()
    used_short_sources = set()

    for i, story in enumerate(longs, 1):
        hook = story.get("opening_hook") or {}
        if not hook.get("text"):
            errors.append(f"Long {i}: missing opening hook")
        if float(hook.get("score", 0)) < 0:
            errors.append(f"Long {i}: invalid hook score")
        path = masters / f"long_{i:02d}.mp4"
        try:
            duration = check_video(path, 181, 600, 1920, 1080)
            if not has_audio(path):
                errors.append(f"Long {i}: rendered master has no audio stream")
            print(f"LONG {i:02d}: {duration:.1f}s OK")
        except Exception as exc:
            errors.append(str(exc))

        speakers = clean_list(story.get("speakers", []))
        if any(s in generic_speakers for s in speakers):
            errors.append(f"Long {i}: generic speaker attribution is not allowed")
        long_speakers.update(speakers)
        long_houses.update(clean_list(story.get("houses", [])))
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
            if not has_audio(path):
                errors.append(f"Short {i}: rendered master has no audio stream")
            silence = max_silence_seconds(path)
            if silence > 5.0:
                errors.append(
                    f"Short {i}: continuous silence is too long ({silence:.1f}s); "
                    "select/render a tighter speech window"
                )
            print(f"SHORT {i:02d}: {duration:.1f}s OK; max silence {silence:.1f}s")
        except Exception as exc:
            errors.append(str(exc))

        hook = story.get("opening_hook") or {}
        if not hook.get("text"):
            errors.append(f"Short {i}: missing opening hook")

        speaker = str(story.get("speaker", "")).strip()
        if speaker:
            if speaker.lower() in generic_speakers:
                errors.append(f"Short {i}: generic speaker attribution is not allowed")
            short_speakers.add(speaker.lower())
        # Missing speaker is acceptable when the official Parliament page does
        # not expose a verified member name; the editorial review queue flags it.

        source = str(
            story.get("video", story.get("source_video", ""))
        ).strip()
        if source:
            used_short_sources.add(source)

        thumb = thumbs / f"short_{i:02d}.jpg"
        if not thumb.exists() or thumb.stat().st_size < 5_000:
            errors.append(f"Missing thumbnail: {thumb}")

    if len(long_houses & {"national assembly", "house of representatives"}) >= 1 and len(long_houses) >= 2:
        if len(long_houses & {"national assembly", "house of representatives"}) < 2:
            errors.append("Long stories should cover both National Assembly and House of Representatives when both have eligible named-speaker sources.")
    if len(used_short_sources) < min(2, len(shorts)):
        errors.append(
            f"Short-source diversity is low: {len(used_short_sources)} unique sources"
        )
    if len(used_long_sources) < min(2, len(longs)):
        errors.append(
            f"Long-source diversity is low: {len(used_long_sources)} unique sources"
        )

    overlap_sources = used_long_sources & used_short_sources
    if overlap_sources:
        errors.append(
            "Short/Long source overlap detected: " + ", ".join(sorted(overlap_sources)[:10])
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
    if len(sys.argv) != 5:
        raise SystemExit(
            "Usage: python src/quality_control.py "
            "<selection_json> <masters_dir> <thumbnails_dir> <subtitles_dir>"
        )
    main(*sys.argv[1:])
