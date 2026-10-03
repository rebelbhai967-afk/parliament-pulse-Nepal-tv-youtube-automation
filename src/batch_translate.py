import json
import sys
import time
from pathlib import Path
from deep_translator import GoogleTranslator


def fmt(seconds):
    seconds = float(seconds)
    h = int(seconds // 3600); m = int((seconds % 3600) // 60); s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000: s += 1; ms -= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _selected_ranges(selection_file):
    """Return transcript-file -> merged time ranges for selected story pieces."""
    ranges = {}
    if not selection_file or not Path(selection_file).exists():
        return ranges
    selection = json.loads(Path(selection_file).read_text(encoding="utf-8"))
    for story in selection.get("long_stories", []) + selection.get("short_stories", []):
        for piece in story.get("pieces", []):
            transcript = str(piece.get("transcript", "")).strip()
            if not transcript:
                continue
            start = float(piece.get("start", 0))
            end = float(piece.get("end", start))
            if end <= start:
                continue
            key = str(Path(transcript).resolve())
            ranges.setdefault(key, []).append((start, end))
    for key, values in ranges.items():
        values.sort()
        merged = []
        for start, end in values:
            if merged and start <= merged[-1][1] + 0.5:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        ranges[key] = merged
    return ranges


def _overlaps_selected(seg_start, seg_end, ranges):
    if not ranges:
        return True
    return any(seg_end > start and seg_start < end for start, end in ranges)


def _translate_with_backoff(translator, text, label):
    """Translate with a conservative request rate and exponential backoff."""
    if not text:
        raise RuntimeError(f"Empty translation input for {label}")
    max_attempts = 6
    for attempt in range(max_attempts):
        try:
            result = translator.translate(text).strip()
            if result:
                return result
            raise RuntimeError("translator returned an empty result")
        except Exception as exc:
            wait = min(60.0, 5.0 * (2 ** attempt))
            print(
                f"Translation warning (attempt {attempt + 1}/{max_attempts}) "
                f"for {label}: {exc}"
            )
            if attempt == max_attempts - 1:
                raise RuntimeError(
                    f"English translation failed for {label}: {exc}"
                ) from exc
            time.sleep(wait)


def _validate_english(english, label):
    letters = [ch for ch in english if ch.isalpha()]
    latin = [ch for ch in letters if ('A' <= ch <= 'Z') or ('a' <= ch <= 'z')]
    if len(letters) >= 12 and len(latin) / len(letters) < 0.55:
        raise RuntimeError(f"Translation appears non-English for {label}")


def main(input_dir, output_dir, summary_output=None, selection_file=None):
    inp, out = Path(input_dir), Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    translator = GoogleTranslator(source="ne", target="en")
    files = sorted(inp.glob("video_*.json"))
    selected_ranges = _selected_ranges(selection_file)

    if selected_ranges:
        files = [
            f for f in files
            if str(f.resolve()) in selected_ranges
        ]
        print(f"Selected transcript sources for translation: {len(files)}")
    elif selection_file and Path(selection_file).exists():
        raise RuntimeError("Selection contains no transcript windows for translation.")

    summaries = {}
    if not files:
        raise RuntimeError("No cleaned transcripts found.")

    # Google Translate's public endpoint can rate-limit bursty runners.
    # Keep requests comfortably below the documented burst threshold and
    # add backoff when the service responds with a server/rate-limit error.
    request_interval = 1.25
    last_request = 0.0
    translation_cache = {}

    def translate(text, label):
        nonlocal last_request
        now = time.monotonic()
        delay = request_interval - (now - last_request)
        if delay > 0:
            time.sleep(delay)
        result = translation_cache.get(text)
        if result is None:
            result = _translate_with_backoff(translator, text, label)
            translation_cache[text] = result
        last_request = time.monotonic()
        _validate_english(result, label)
        return result

    for file in files:
        target = out / f"{file.stem}.srt"
        data = json.loads(file.read_text(encoding="utf-8"))
        ranges = selected_ranges.get(str(file.resolve()))
        lines = []
        summary_source = []

        for seg in data.get("segments", []):
            seg_start = float(seg.get("start", 0))
            seg_end = float(seg.get("end", seg_start))
            if not _overlaps_selected(seg_start, seg_end, ranges):
                continue
            text = str(seg.get("nepali", "")).strip()
            if not text:
                continue
            summary_source.append(text)
            english = translate(
                text,
                f"{file.name} segment {seg.get('start', 0)}",
            )
            lines.append((seg_start, seg_end, english))

        if not lines:
            raise RuntimeError(f"No selected transcript segments found for {file.name}")

        with target.open("w", encoding="utf-8") as f:
            for i, (start, end, text) in enumerate(lines, 1):
                f.write(f"{i}\n{fmt(start)} --> {fmt(end)}\n{text}\n\n")

        if summary_output is not None:
            sample = " ".join(summary_source[:8]).strip()
            summary_text = ""
            if sample:
                summary_text = translate(
                    sample[:1200],
                    f"{file.name} topic summary",
                )
            summaries[file.stem] = summary_text
        print("Translated", file.name)

    if summary_output is not None:
        Path(summary_output).write_text(
            json.dumps(summaries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print("Batch translation complete.")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4, 5):
        print("Usage: python src/batch_translate.py <cleaned_transcripts> <srt_output> [summary_json] [selection_json]")
        raise SystemExit(1)
    main(
        sys.argv[1],
        sys.argv[2],
        sys.argv[3] if len(sys.argv) >= 4 else None,
        sys.argv[4] if len(sys.argv) == 5 else None,
    )
