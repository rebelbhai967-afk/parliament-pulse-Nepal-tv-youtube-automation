import json
import re
import sys
from pathlib import Path

from editorial_hooks import enrich_piece

KEYWORDS = {
    "प्रधानमन्त्री": 6, "मन्त्री": 5, "अर्थमन्त्री": 6, "सभामुख": 4, "अध्यक्ष": 4,
    "सरकार": 4, "कानुन": 5, "विधेयक": 5, "संशोधन": 5, "बजेट": 6, "कर": 4,
    "नीति": 4, "योजना": 4, "भ्रष्टाचार": 7, "अनियमितता": 7, "जवाफ": 5, "प्रश्न": 4,
    "निर्णय": 5, "महत्वपूर्ण": 4, "संविधान": 5, "शिक्षा": 4, "स्वास्थ्य": 4,
    "रोजगारी": 4, "महँगी": 5, "विकास": 4, "सुरक्षा": 5, "सीमा": 5, "प्रतिवेदन": 5,
}
STRONG = ["गम्भीर", "आवश्यक", "तत्काल", "सरकारले", "मन्त्रालयले", "निर्णय", "घोषणा", "प्रस्ताव", "जवाफदेही"]
GENERIC_SPEAKERS = {"", "zero hour", "special hour", "jawaf", "prastav prastut", "ninrnayartha prastut", "samjhauta pes", "summary", "first meeting"}


def clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def score(text):
    text = clean(text)
    value = sum(v for k, v in KEYWORDS.items() if k in text)
    value += 2 * sum(1 for p in STRONG if p in text)
    if "?" in text or any(x in text for x in ["किन", "कसरी", "कहिले", "कति"]):
        value += 3
    if 100 <= len(text) <= 650:
        value += 5
    return value


def words(text):
    stop = {"को","का","की","ले","लाई","मा","बाट","र","तर","पनि","छ","हो","हुन","भएको","गरेको","गर्ने","गर्न","भन्ने","हामी","उहाँ","यस","यो","त्यो"}
    return {w.strip(".,!?;:।") for w in clean(text).split() if len(w.strip(".,!?;:।")) >= 3 and w.strip(".,!?;:।") not in stop}


def similarity(a, b):
    x, y = words(a), words(b)
    return len(x & y) / len(x | y) if x | y else 0.0


def build_candidate(segments, i, min_s=70, max_s=180):
    start = float(segments[i].get("start", 0))
    end = float(segments[i].get("end", start))
    left = right = i
    while end - start < min_s:
        if left > 0 and (right >= len(segments)-1 or start - float(segments[left-1].get("start", start)) <= float(segments[right+1].get("end", end)) - end):
            left -= 1; start = float(segments[left].get("start", start))
        elif right < len(segments)-1:
            right += 1; end = float(segments[right].get("end", end))
        else:
            break
    while end - start > max_s and left < right:
        if start - float(segments[left].get("start", start)) >= float(segments[right].get("end", end)) - end:
            left += 1; start = float(segments[left].get("start", start))
        else:
            right -= 1; end = float(segments[right].get("end", end))
    text = " ".join(clean(s.get("nepali")) for s in segments[left:right+1])
    return {"start": round(start,3), "end": round(end,3), "duration": round(end-start,3), "score": score(text), "text": text}


def load_video_meta():
    path = Path("data/videos/videos.json")
    if not path.exists():
        return {}
    result = {}
    for item in json.loads(path.read_text(encoding="utf-8")):
        result[item["file"]] = item
    return result


def main(input_dir, output_file):
    meta = load_video_meta()
    candidates = []
    for transcript_file in sorted(Path(input_dir).glob("video_*.json")):
        data = json.loads(transcript_file.read_text(encoding="utf-8"))
        segments = data.get("segments", [])
        video = str(Path("data/videos") / (transcript_file.stem + ".mp4"))
        vm = meta.get(video, {})
        speaker = clean(vm.get("speaker"))
        for i, seg in enumerate(segments):
            if not clean(seg.get("nepali")):
                continue
            c = build_candidate(segments, i)
            if c["duration"] < 60 or c["duration"] > 180:
                continue
            c.update({
                "video": video,
                "transcript": str(transcript_file),
                "speaker": speaker,
                "house": vm.get("house", ""),
                "source_page": vm.get("page", ""),
                "collection_title": vm.get("collection_title", ""),
            })
            candidates.append(c)

    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Keep a diverse candidate pool: no single source video dominates.
    pool, per_video = [], {}
    for c in candidates:
        if per_video.get(c["video"], 0) >= 4:
            continue
        pool.append(c); per_video[c["video"]] = per_video.get(c["video"], 0) + 1
        if len(pool) >= 80:
            break

    long_stories = []
    used = set()
    for anchor in pool:
        if anchor["video"] in used:
            continue
        pieces = [anchor]
        total = anchor["duration"]
        related = [c for c in pool if c["video"] != anchor["video"] and c["video"] not in {p["video"] for p in pieces}]
        related.sort(key=lambda c: (similarity(anchor["text"], c["text"]), c["score"]), reverse=True)
        for c in related:
            sim = similarity(anchor["text"], c["text"])
            if sim < 0.08:
                continue
            if total + c["duration"] > 600:
                continue
            pieces.append(c); total += c["duration"]
            if total >= 181 or len(pieces) >= 4:
                break
        if total >= 181 and len(pieces) <= 4:
            long_stories.append(enrich_piece({
                "pieces": pieces,
                "duration": round(total,3),
                "score": round(sum(p["score"] for p in pieces) + 8 * (len(pieces)-1), 3),
                "speakers": [p["speaker"] for p in pieces if p["speaker"]],
                "houses": sorted({p["house"] for p in pieces if p["house"]}),
                "topic_text": " ".join(p["text"] for p in pieces),
            }))
            used.update(p["video"] for p in pieces)
        if len(long_stories) >= 12:
            break

    # Fallback: build 2-piece stories from remaining strong candidates.
    if len(long_stories) < 12:
        for i, a in enumerate(pool):
            if a["video"] in used:
                continue
            for b in pool[i+1:]:
                if b["video"] in used or b["video"] == a["video"]:
                    continue
                total = a["duration"] + b["duration"]
                if 181 <= total <= 600 and similarity(a["text"], b["text"]) >= 0.03:
                    long_stories.append(enrich_piece({
                        "pieces": [a,b],
                        "duration": round(total,3),
                        "score": a["score"] + b["score"],
                        "speakers": [x["speaker"] for x in [a,b] if x["speaker"]],
                        "houses": sorted({x["house"] for x in [a,b] if x["house"]}),
                        "topic_text": a["text"] + " " + b["text"],
                    }))
                    used.update([a["video"], b["video"]])
                    break
            if len(long_stories) >= 12:
                break

    short_stories = []
    short_used = set()
    for c in pool:
        if c["video"] in used or c["video"] in short_used:
            continue
        if c["duration"] <= 89:
            piece = dict(c)
            short_stories.append(enrich_piece({
                "pieces": [piece],
                "duration": piece["duration"],
                "score": piece["score"],
                "speakers": [piece["speaker"]] if piece["speaker"] else [],
                "speaker": piece["speaker"],
                "houses": [piece["house"]] if piece["house"] else [],
                "topic_text": piece["text"],
                "video": piece["video"],
            }))
            short_used.add(c["video"])
        else:
            # trim to a centered 60-85 second window
            mid = (c["start"] + c["end"]) / 2
            c2 = dict(c)
            c2["start"] = round(max(0, mid - 38), 3)
            c2["end"] = round(min(c["end"], mid + 38), 3)
            c2["duration"] = round(c2["end"] - c2["start"], 3)
            short_stories.append(enrich_piece({
                "pieces": [c2],
                "duration": c2["duration"],
                "score": c2["score"],
                "speakers": [c2["speaker"]] if c2["speaker"] else [],
                "speaker": c2["speaker"],
                "houses": [c2["house"]] if c2["house"] else [],
                "topic_text": c2["text"],
                "video": c2["video"],
            }))
            short_used.add(c["video"])
        if len(short_stories) >= 12:
            break

    result = {
        "model": "parliament-multi-story-v2-editorial-hooks",
        "target": {"long": 12, "short": 12},
        "selection_rules": [
            "Candidate pool comes from both National Assembly and House of Representatives.",
            "Long stories are 181–600 seconds and may combine 2–4 distinct speaker/video clips.",
            "Short/Reel stories are under 90 seconds and are selected from stories not used by the Long set.",
            "Speaker names come from official Parliament video-page labels when available.",
            "Repeated speakers/videos are limited to improve coverage.",
            "Low-information procedural clips are not preferred.",
            "Every selected story receives a transcript-grounded cold-open hook.",
            "The opening hook uses original Parliament audio; no synthetic voiceover is required.",
        ],
        "long_stories": long_stories,
        "short_stories": short_stories,
        "candidate_count": len(candidates),
    }
    Path(output_file).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Candidates: {len(candidates)} | Long stories: {len(long_stories)} | Short stories: {len(short_stories)}")
    if len(long_stories) < 4 or len(short_stories) < 4:
        raise RuntimeError("Not enough diverse stories for a safe multi-story build; refusing to fabricate content.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python src/batch_analyze_v2.py <transcripts_clean_dir> <selection_json>")
        raise SystemExit(1)
    main(sys.argv[1], sys.argv[2])
