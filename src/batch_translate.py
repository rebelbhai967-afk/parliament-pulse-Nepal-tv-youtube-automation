import json
import sys
import time
import re
from pathlib import Path


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



def _translate_with_backoff(text, label):
    """Use Google's public translation endpoint directly, with endpoint fallback."""
    if not text:
        raise RuntimeError(f"Empty translation input for {label}")
    endpoints = [
        "https://translate.googleapis.com/translate_a/single",
        "https://translate.google.com/translate_a/single",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
    }
    max_attempts = 4
    last_error = None
    for attempt in range(max_attempts):
        for endpoint in endpoints:
            try:
                params = {
                    "client": "gtx",
                    "sl": "ne",
                    "tl": "en",
                    "dt": "t",
                    "ie": "UTF-8",
                    "oe": "UTF-8",
                    "q": text,
                }
                response = requests.get(endpoint, params=params, headers=headers, timeout=30)
                if response.status_code in (403, 429):
                    raise RuntimeError(f"HTTP {response.status_code} rate-limited by {endpoint}")
                response.raise_for_status()
                payload = response.json()
                parts = []
                if isinstance(payload, list) and payload and isinstance(payload[0], list):
                    for item in payload[0]:
                        if isinstance(item, list) and item and item[0]:
                            parts.append(str(item[0]))
                elif isinstance(payload, dict):
                    for item in payload.get("sentences", []):
                        if item.get("trans"):
                            parts.append(str(item["trans"]))
                result = "".join(parts).strip()
                if result:
                    return result
                raise RuntimeError("Google translation response contained no translated text")
            except Exception as exc:
                last_error = exc
                print(f"Translation endpoint warning for {label}: {exc}")
        wait = min(120.0, 15.0 * (2 ** attempt))
        if attempt < max_attempts - 1:
            print(f"Translation retry {attempt + 1}/{max_attempts}; waiting {wait:.0f}s")
            time.sleep(wait)
    raise RuntimeError(f"English translation failed for {label}: {last_error}") from last_error

def _validate_english(english, label):
    letters = [ch for ch in english if ch.isalpha()]
    latin = [ch for ch in letters if ('A' <= ch <= 'Z') or ('a' <= ch <= 'z')]
    if len(letters) >= 12 and len(latin) / len(letters) < 0.55:
        raise RuntimeError(f"Translation appears non-English for {label}")


def _translate_segments(segments, label_prefix):
    """Translate many subtitle segments in one request to avoid per-segment throttling."""
    results = []
    batch = []
    chars = 0
    batch_index = 0

    def flush():
        nonlocal batch, chars, batch_index
        if not batch:
            return
        batch_index += 1
        markers = []
        source_parts = []
        for index, text in batch:
            marker = f"PPSEG{index:04d}"
            markers.append(marker)
            source_parts.append(f"{marker}: {text}")
        payload = "\n".join(source_parts)
        translated = _translate_with_backoff(
            payload, f"{label_prefix} batch {batch_index}"
        )
        _validate_english(translated, f"{label_prefix} batch {batch_index}")

        parsed = {}
        for marker in markers:
            match = re.search(
                rf"{re.escape(marker)}\s*:\s*(.*?)(?=\s+PPSEG\d{{4}}\s*:|$)",
                translated,
                flags=re.DOTALL,
            )
            if match:
                parsed[marker] = " ".join(match.group(1).split()).strip()

        missing = [marker for marker in markers if not parsed.get(marker)]
        if missing:
            raise RuntimeError(
                f"Could not safely map translated subtitle batch "
                f"{batch_index}; missing markers: {', '.join(missing)}"
            )
        for index, _ in batch:
            results.append((index, parsed[f"PPSEG{index:04d}"]))
        batch = []
        chars = 0

    for index, text in segments:
        # Stay well below the public endpoint's practical text-size limit.
        added = len(text) + 18
        if batch and chars + added > 2800:
            flush()
            # A small pause between successful batch requests prevents bursts.
            time.sleep(2.0)
        batch.append((index, text))
        chars += added
        if len(batch) >= 8:
            flush()
            time.sleep(2.0)
    flush()
    results.sort(key=lambda item: item[0])
    return [text for _, text in results]


def main(input_dir, output_dir, summary_output=None, selection_file=None):
    inp, out = Path(input_dir), Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
        files = sorted(inp.glob("video_*.json"))
    selected_ranges = _selected_ranges(selection_file)

    if selected_ranges:
        files = [f for f in files if str(f.resolve()) in selected_ranges]
        print(f"Selected transcript sources for translation: {len(files)}")
    elif selection_file and Path(selection_file).exists():
        raise RuntimeError("Selection contains no transcript windows for translation.")

    summaries = {}
    if not files:
        raise RuntimeError("No cleaned transcripts found.")

    for file in files:
        target = out / f"{file.stem}.srt"
        data = json.loads(file.read_text(encoding="utf-8"))
        ranges = selected_ranges.get(str(file.resolve()))
        selected = []
        for seg in data.get("segments", []):
            seg_start = float(seg.get("start", 0))
            seg_end = float(seg.get("end", seg_start))
            if not _overlaps_selected(seg_start, seg_end, ranges):
                continue
            text = str(seg.get("nepali", "")).strip()
            if text:
                selected.append((seg_start, seg_end, text))

        if not selected:
            raise RuntimeError(f"No selected transcript segments found for {file.name}")

        translated = _translate_segments(
            [(i, text) for i, (_, _, text) in enumerate(selected)],
            file.name,
        )
        lines = [
            (selected[i][0], selected[i][1], translated[i])
            for i in range(len(selected))
        ]

        with target.open("w", encoding="utf-8") as f:
            for i, (start, end, text) in enumerate(lines, 1):
                f.write(f"{i}\n{fmt(start)} --> {fmt(end)}\n{text}\n\n")

        if summary_output is not None:
            # Avoid another Google request: the topic summary source is already
            # represented by the first translated subtitle lines.
            summary_text = " ".join(translated[:8]).strip()
            summaries[file.stem] = summary_text[:2000]
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
