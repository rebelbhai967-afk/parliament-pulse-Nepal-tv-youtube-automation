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


def main(input_dir, output_dir, summary_output=None):
    inp, out = Path(input_dir), Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    translator = GoogleTranslator(source="ne", target="en")
    files = sorted(inp.glob("video_*.json"))
    summaries = {}
    if not files:
        raise RuntimeError("No cleaned transcripts found.")
    for file in files:
        target = out / f"{file.stem}.srt"
        data = json.loads(file.read_text(encoding="utf-8"))
        lines = []
        summary_source = []
        for seg in data.get("segments", []):
            text = str(seg.get("nepali", "")).strip()
            if not text:
                continue
            summary_source.append(text)
            try:
                english = translator.translate(text).strip()
            except Exception as exc:
                print("Translation warning:", exc)
                english = text
            lines.append((float(seg.get("start",0)), float(seg.get("end",0)), english))
            time.sleep(0.15)
        with target.open("w", encoding="utf-8") as f:
            for i, (start, end, text) in enumerate(lines, 1):
                f.write(f"{i}\n{fmt(start)} --> {fmt(end)}\n{text}\n\n")
        if summary_output is not None:
            sample = " ".join(summary_source[:8]).strip()
            try:
                summaries[file.stem] = translator.translate(sample[:1200]).strip() if sample else ""
            except Exception:
                summaries[file.stem] = ""
        print("Translated", file.name)
    if summary_output is not None:
        Path(summary_output).write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Batch translation complete.")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print("Usage: python src/batch_translate.py <cleaned_transcripts> <srt_output> [summary_json]")
        raise SystemExit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)
