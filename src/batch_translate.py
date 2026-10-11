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



def _translate_with_backoff(text, label, translator, fallback_loader=None):
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

    quality_markers = (
        "appears garbled", "appears repetitive",
        "lacks basic English structure", "appears non-English",
        "low English lexical coverage", "very low English lexical coverage"
    )

    def translate_one(chunk, chunk_label, model, allow_recovery=True):
        """Translate one chunk, recovering from deterministic decoder collapse.

        ONNX greedy decoding is deterministic, so repeating the same request
        does not change a repetition failure. Instead, first retry the failed
        text as two smaller context-preserving pieces. Only then use the
        heavier fallback model.
        """
        try:
            result = model.translate(
                chunk,
                src_lang="npi_Deva",
                tgt_lang="eng_Latn",
                max_new_tokens=128,
            ).strip()
            if not result:
                raise RuntimeError("Local translation returned empty text")
            _validate_english(result, chunk_label)
            return result
        except RuntimeError as exc:
            message = str(exc)
            if not any(marker in message for marker in quality_markers):
                raise

            # Try the configured fallback on the complete context before splitting.
            # Splitting first can remove context needed for a correct English subtitle.
            if fallback_loader is not None:
                try:
                    print(
                        f"Translation quality gate failed for {chunk_label}; "
                        "trying configured fallback on full context."
                    )
                    fallback_translator = fallback_loader()
                    fallback = fallback_translator.translate(
                        chunk,
                        src_lang="npi_Deva",
                        tgt_lang="eng_Latn",
                        max_new_tokens=128,
                    ).strip()
                    if not fallback:
                        raise RuntimeError("Configured fallback returned empty text")
                    _validate_english(fallback, chunk_label + " fallback")
                    return fallback
                except RuntimeError as fallback_error:
                    if not any(marker in str(fallback_error) for marker in quality_markers):
                        raise
                    print(
                        f"Fallback quality gate failed for {chunk_label}; "
                        "trying smaller chunks as a last recovery."
                    )

            words = chunk.split()
            if allow_recovery and len(chunk) >= 90 and len(words) >= 10:
                midpoint = max(1, len(chunk) // 2)
                cut = chunk.rfind(" ", 0, midpoint)
                if cut < 35:
                    cut = chunk.find(" ", midpoint)
                if 35 <= cut < len(chunk) - 20:
                    left = chunk[:cut].strip()
                    right = chunk[cut:].strip()
                    print(
                        f"Translation quality gate failed for {chunk_label}; "
                        "splitting into two smaller context chunks."
                    )
                    left_result = translate_one(
                        left, chunk_label + "a", model, allow_recovery=False
                    )
                    right_result = translate_one(
                        right, chunk_label + "b", model, allow_recovery=False
                    )
                    return f"{left_result} {right_result}".strip()

            raise

    for chunk_no, chunk in enumerate(chunks, 1):
        chunk_label = label if len(chunks) == 1 else f"{label} chunk {chunk_no}"
        last_error = None
        for attempt in range(2):
            try:
                translated_parts.append(
                    translate_one(chunk, chunk_label, translator)
                )
                last_error = None
                break
            except RuntimeError as exc:
                last_error = exc
                if attempt == 0 and not any(
                    marker in str(exc) for marker in quality_markers
                ):
                    print(
                        f"Local translation retry 1/2 for {chunk_label}; "
                        f"waiting 3s"
                    )
                    time.sleep(3)
                else:
                    raise
        if last_error is not None:
            raise RuntimeError(
                f"English translation failed for {chunk_label}: {last_error}"
            ) from last_error

    return " ".join(translated_parts).strip()

def _validate_english(english, label):
    letters = [ch for ch in english if ch.isalpha()]
    latin = [ch for ch in letters if ('A' <= ch <= 'Z') or ('a' <= ch <= 'z')]
    if len(letters) >= 12 and len(latin) / len(letters) < 0.55:
        raise RuntimeError(f"Translation appears non-English for {label}")

    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", english.lower())
    # Detect phonetic Nepali transliteration while translation is still at the
    # segment level, so the configured fallback can retry before SRT assembly.
    if len(words) >= 16:
        try:
            from wordfreq import zipf_frequency
            eligible = [word for word in words if len(word) >= 3]
            if len(eligible) >= 12:
                known = sum(1 for word in eligible if zipf_frequency(word, "en") >= 2.5)
                coverage = known / len(eligible)
                # Segment-level lexical coverage is noisy for names,
                # parliamentary terminology, and short context chunks. Keep this
                # threshold conservative; the full subtitle file is checked
                # separately with a stricter threshold before rendering.
                if coverage < 0.45:
                    raise RuntimeError(
                        f"Translation has very low English lexical coverage for {label} ({coverage:.2f})"
                    )
        except ImportError:
            pass

    if len(words) >= 12:
        counts = {}
        for word in words:
            counts[word] = counts.get(word, 0) + 1
        most_common = max(counts.values(), default=0)
        if most_common >= 6 and most_common / len(words) >= 0.30:
            raise RuntimeError(f"Translation appears repetitive for {label}")

    # Do not reject a translation solely because it lacks a tiny hard-coded
    # list of English function words. Parliamentary fragments, names, and
    # short clauses can be valid English without those tokens. The later
    # subtitle lexical-coverage gate screens for transliteration/garbling.
    # Reject obvious translation corruption such as PROFRIBESTRIBSTRIB.
    # Repeated 3-6 character chunks 3+ times inside a long token are highly
    # unlikely in normal English and should fail closed before subtitles ship.
    for token in re.findall(r"[A-Za-z]{16,}", english):
        lowered = token.lower()
        for size in range(3, 7):
            chunks = [lowered[i:i + size] for i in range(0, len(lowered) - size + 1)]
            if any(lowered.count(chunk) >= 3 for chunk in set(chunks)):
                raise RuntimeError(f"Translation appears garbled for {label}: {token}")


def _translate_segments(segments, label_prefix, translator, fallback_loader=None):
    """Translate selected subtitle segments locally, preserving segment order."""
    results = []
    for index, text in segments:
        translated = _translate_with_backoff(
            text, f"{label_prefix} segment {index + 1}", translator, fallback_loader
        )
        _validate_english(
            translated, f"{label_prefix} segment {index + 1}"
        )
        results.append(" ".join(translated.split()).strip())
    return results

def main(input_dir, output_dir, summary_output=None, selection_file=None):
    """Generate English subtitles from the original Nepali audio using Whisper.

    Do not translate the already-ASR-transcribed Nepali text: ASR errors and
    IndicTrans transliteration were causing repeatedly bad English captions.
    The original video/audio remains unchanged; only SRT captions are created.
    """
    import subprocess
    import tempfile
    from faster_whisper import WhisperModel

    inp, out = Path(input_dir), Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(inp.glob("video_*.json"))
    selected_ranges = _selected_ranges(selection_file)

    if selected_ranges:
        files = [f for f in files if str(f.resolve()) in selected_ranges]
        print(f"Selected original-audio sources for English subtitles: {len(files)}")
    elif selection_file and Path(selection_file).exists():
        raise RuntimeError("Selection contains no transcript windows for English subtitles.")

    if not files:
        raise RuntimeError("No cleaned transcripts found.")

    model_name = os.environ.get("WHISPER_TRANSLATION_MODEL", "large-v3-turbo")
    cpu_threads = int(os.environ.get("WHISPER_CPU_THREADS", "2"))
    beam_size = int(os.environ.get("WHISPER_TRANSLATION_BEAM_SIZE", "5"))
    print(
        f"Loading cached/free offline Whisper model for Nepali-audio-to-English "
        f"subtitles: {model_name} (CPU int8, beam={beam_size})"
    )
    model = WhisperModel(
        model_name,
        device="cpu",
        compute_type="int8",
        cpu_threads=cpu_threads,
    )

    summaries = {}
    for file in files:
        data = json.loads(file.read_text(encoding="utf-8"))
        ranges = selected_ranges.get(str(file.resolve()))
        if not ranges:
            raise RuntimeError(f"No selected original-audio ranges for {file.name}")

        source_video = Path(str(data.get("video", "")).strip())
        if not source_video.is_absolute():
            source_video = Path.cwd() / source_video
        if not source_video.exists():
            source_video = Path("data/videos") / f"{file.stem}.mp4"
        if not source_video.exists():
            raise FileNotFoundError(
                f"Cannot locate original source video for English subtitles: {source_video}"
            )

        subtitle_rows = []
        with tempfile.TemporaryDirectory(prefix="ppn-english-subtitles-") as tmp:
            for range_no, (range_start, range_end) in enumerate(ranges, 1):
                audio_path = Path(tmp) / f"{file.stem}-{range_no}.wav"
                command = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", str(max(0.0, range_start)),
                    "-i", str(source_video),
                    "-t", str(max(0.1, range_end - range_start)),
                    "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(audio_path),
                ]
                result = subprocess.run(command, capture_output=True, text=True)
                if result.returncode != 0 or not audio_path.exists():
                    raise RuntimeError(
                        f"Could not extract subtitle audio for {file.name}: "
                        f"{result.stderr[-1000:]}"
                    )

                segments, info = model.transcribe(
                    str(audio_path),
                    language="ne",
                    task="translate",
                    beam_size=beam_size,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    vad_filter=True,
                    word_timestamps=False,
                )
                before = len(subtitle_rows)
                for segment in segments:
                    text = " ".join(str(segment.text or "").split()).strip()
                    if not text:
                        continue
                    letters = [ch for ch in text if ch.isalpha()]
                    latin = [
                        ch for ch in letters
                        if ("A" <= ch <= "Z") or ("a" <= ch <= "z")
                    ]
                    # Keep mixed-script/short English cues for the file-level
                    # lexical QC to assess. A strict per-cue 0.70 ratio can discard
                    # every cue in an otherwise translatable Nepali passage.
                    if letters and len(latin) / len(letters) < 0.35:
                        continue
                    cue_start = max(range_start, range_start + float(segment.start))
                    cue_end = min(range_end, range_start + float(segment.end))
                    if cue_end > cue_start:
                        subtitle_rows.append((cue_start, cue_end, text))

                if len(subtitle_rows) == before:
                    raise RuntimeError(
                        f"Whisper produced no English subtitle cues for "
                        f"{file.name} selected range {range_start:.1f}-{range_end:.1f}s "
                        f"(detected audio language: {getattr(info, 'language', 'unknown')})."
                    )

        subtitle_rows.sort(key=lambda row: (row[0], row[1]))
        joined = " ".join(row[2] for row in subtitle_rows).strip()
        letters = [ch for ch in joined if ch.isalpha()]
        latin = [
            ch for ch in letters
            if ("A" <= ch <= "Z") or ("a" <= ch <= "z")
        ]
        latin_ratio = len(latin) / len(letters) if letters else 0.0
        if not subtitle_rows or latin_ratio < 0.75:
            raise RuntimeError(
                f"Direct audio translation did not produce English-first subtitles "
                f"for {file.name} (Latin ratio {latin_ratio:.2f})."
            )

        target = out / f"{file.stem}.srt"
        with target.open("w", encoding="utf-8") as handle:
            for index, (cue_start, cue_end, text) in enumerate(subtitle_rows, 1):
                handle.write(
                    f"{index}\n{fmt(cue_start)} --> {fmt(cue_end)}\n{text}\n\n"
                )

        if summary_output is not None:
            summaries[file.stem] = joined[:2000]
        print(
            f"Created English subtitles from original Nepali audio: {file.name} "
            f"({len(subtitle_rows)} cues; Latin ratio {latin_ratio:.2f})"
        )

    if summary_output is not None:
        Path(summary_output).write_text(
            json.dumps(summaries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print("English subtitles generated from original Nepali audio; original audio/video unchanged.")


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
