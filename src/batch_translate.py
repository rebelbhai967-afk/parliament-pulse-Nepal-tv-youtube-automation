import json
import sys
import time
import re
import os
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



def _translate_with_backoff(text, label, translator):
    """Translate locally with IndicTrans2; no remote translation API.

    Long parliamentary transcript segments can push the ONNX decoder into a
    degenerate repetition loop. Keep each model input bounded and translate
    sentence-aware chunks, then join them back into one subtitle string.
    """
    if not text:
        raise RuntimeError(f"Empty translation input for {label}")

    max_chars = int(os.environ.get("INDICTRANS_MAX_INPUT_CHARS", "220"))

    def split_chunks(value):
        value = " ".join(value.split()).strip()
        if len(value) <= max_chars:
            return [value]
        pieces = []
        remaining = value
        while len(remaining) > max_chars:
            cut = -1
            for marker in ("।", "?", "!", ".", ";", ":", ","):
                pos = remaining.rfind(marker, 0, max_chars + 1)
                if pos > cut:
                    cut = pos
            if cut < max_chars // 2:
                space = remaining.rfind(" ", 0, max_chars + 1)
                cut = space if space > max_chars // 2 else max_chars - 1
            piece = remaining[:cut + 1].strip()
            if not piece:
                piece = remaining[:max_chars].strip()
            pieces.append(piece)
            remaining = remaining[len(piece):].strip()
        if remaining:
            pieces.append(remaining)
        return pieces

    chunks = split_chunks(text)
    translated_parts = []
    for chunk_no, chunk in enumerate(chunks, 1):
        chunk_label = label if len(chunks) == 1 else f"{label} chunk {chunk_no}"
        last_error = None
        for attempt in range(3):
            try:
                result = translator.translate(
                    chunk,
                    src_lang="npi_Deva",
                    tgt_lang="eng_Latn",
                    max_new_tokens=96,
                ).strip()
                if not result:
                    raise RuntimeError("Local translation returned empty text")
                _validate_english(result, chunk_label)
                translated_parts.append(result)
                break
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    wait = 5 * (attempt + 1)
                    print(
                        f"Local translation retry {attempt + 1}/3 for "
                        f"{chunk_label}; waiting {wait}s"
                    )
                    time.sleep(wait)
        else:
            raise RuntimeError(
                f"English translation failed for {chunk_label}: {last_error}"
            ) from last_error

    return " ".join(translated_parts).strip()

def _validate_english(english, label):
    letters = [ch for ch in english if ch.isalpha()]
    latin = [ch for ch in letters if ('A' <= ch <= 'Z') or ('a' <= ch <= 'z')]
    if len(letters) >= 12 and len(latin) / len(letters) < 0.55:
        raise RuntimeError(f"Translation appears non-English for {label}")

    # Reject obvious translation corruption such as PROFRIBESTRIBSTRIB.
    # Repeated 3-6 character chunks 3+ times inside a long token are highly
    # unlikely in normal English and should fail closed before subtitles ship.
    for token in re.findall(r"[A-Za-z]{16,}", english):
        lowered = token.lower()
        for size in range(3, 7):
            chunks = [lowered[i:i + size] for i in range(0, len(lowered) - size + 1)]
            if any(lowered.count(chunk) >= 3 for chunk in set(chunks)):
                raise RuntimeError(f"Translation appears garbled for {label}: {token}")


def _translate_segments(segments, label_prefix, translator):
    """Translate selected subtitle segments locally, preserving segment order."""
    results = []
    for index, text in segments:
        translated = _translate_with_backoff(
            text, f"{label_prefix} segment {index + 1}", translator
        )
        _validate_english(
            translated, f"{label_prefix} segment {index + 1}"
        )
        results.append(" ".join(translated.split()).strip())
    return results

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

    model_name = os.environ.get(
        "INDICTRANS_MODEL",
        "hari31416/indictrans2-indic-en-dist-200M-ONNX-fp16",
    )
    print(f"Loading free offline translation model: {model_name}")
    from indictrans_onnx import IndicTransONNX
    translator = IndicTransONNX(model_name)

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
            translator,
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
