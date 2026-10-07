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
GENERIC_SPEAKERS = {
    "", "zero hour", "special hour", "jawaf", "prastav prastut",
    "ninrnayartha prastut", "samjhauta pes", "summary", "first meeting",
    "meeting", "national anthem", "bidhyak prastut", "pratibedan pes",
    "pratibedhan pes", "sammananiye sabhamukh", "सम्माननीय अध्यक्ष", "शून्य समय",
}


def clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


PROCEDURAL_LABELS = (
    "zero hour", "special hour", "jawaf", "prastav prastut",
    "pratibedan pes", "pratibedhan pes", "bidhyak prastut",
    "national anthem", "sammananiye sabhamukh", "सम्माननीय अध्यक्ष",
    "शून्य समय", "प्रतिवेदन", "वार्षिक प्रतिवेदन", "सभासमक्ष",
    "सभा समक्ष", "विधेयक प्रस्तुत", "प्रस्ताव प्रस्तुत", "बैठक",
    "अधिवेशन", "प्रस्तुत", "प्रस्ताव", "विधेयक"
)

def is_procedural_label(text):
    """Classify only the final archive label, not the session header.

    Parliament page titles often look like:
    "House session / Dhurba Raj Rai". The session header contains words such
    as "meeting" or "assembly" even when the final component is a real member
    name. Inspecting the whole title incorrectly marks every named-member page
    as procedural.
    """
    value = clean(text)
    if not value:
        return False
    tail = re.split(r"\s*(?:/|\||:)\s*", value)[-1].strip().lower()
    return bool(tail) and any(term in tail for term in PROCEDURAL_LABELS)


COMMON_NEPALI = {
    "यो","त्यो","यस","यसको","यसमा","हामी","हाम्रो","उहाँ","उनी","उहाँले",
    "सरकार","मन्त्रालय","मन्त्री","सभामुख","अध्यक्ष","सांसद","संसद","कानुन",
    "विधेयक","बजेट","प्रश्न","जवाफ","निर्णय","समिति","प्रतिवेदन","देश","जनता",
    "भएको","भएका","गरेको","गर्न","गर्ने","गर्नुपर्छ","भन्ने","भने","पनि","र","तर",
    "मा","बाट","लाई","ले","को","का","की","छ","छन्","हो","हुन","हुन्छ","थियो",
    "थिए","किन","कसरी","कति","कहिले","जहाँ","जुन","तथा","वा","अथवा","साथै",
    "लागि","मार्फत","सम्बन्धी","बारेमा","भित्र","बाहिर","समय","आज","भोलि"
}

def looks_hallucinated_nepali(text):
    """Reject obvious Whisper repetition/hallucination artifacts."""
    value = clean(text)
    if not value:
        return True
    if re.search(r"([\u0900-\u097F])\1{5,}", value):
        return True
    tokens = [t.strip(".,!?;:।") for t in value.split() if t.strip(".,!?;:।")]
    if len(tokens) >= 12:
        counts = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        most_common = max(counts.values(), default=0)
        if most_common >= 6 and most_common / len(tokens) >= 0.30:
            return True
    for token in tokens:
        if len(token) >= 10:
            for size in (2, 3, 4):
                pattern = token[:size]
                if pattern and token.count(pattern) >= 4:
                    return True
    return False

def transcript_quality_penalty(text, avg_logprob=None):
    text = clean(text)
    dev = len(re.findall(r"[\u0900-\u097F]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    letters = dev + latin
    penalty = 0
    if letters < 30:
        penalty -= 10
    ratio = dev / letters if letters else 0
    if ratio < 0.45:
        penalty -= 12
    elif ratio < 0.60:
        penalty -= 5
    tokens = [t.strip(".,!?;:।") for t in text.split()]
    common_ratio = sum(1 for t in tokens if t in COMMON_NEPALI) / max(1, len(tokens))
    if len(tokens) >= 40 and common_ratio < 0.06:
        penalty -= 10
    elif len(tokens) >= 40 and common_ratio < 0.10:
        penalty -= 5
    if avg_logprob is not None:
        if avg_logprob < -1.0:
            penalty -= 10
        elif avg_logprob < -0.7:
            penalty -= 5
    return penalty

def score(text, avg_logprob=None):
    text = clean(text)
    value = sum(v for k, v in KEYWORDS.items() if k in text)
    value += 2 * sum(1 for p in STRONG if p in text)
    if "?" in text or any(x in text for x in ["किन", "कसरी", "कहिले", "कति"]):
        value += 3
    if 100 <= len(text) <= 650:
        value += 5
    value += transcript_quality_penalty(text, avg_logprob)
    return value


def words(text):
    stop = {"को","का","की","ले","लाई","मा","बाट","र","तर","पनि","छ","हो","हुन","भएको","गरेको","गर्ने","गर्न","भन्ने","हामी","उहाँ","यस","यो","त्यो"}
    return {w.strip(".,!?;:।") for w in clean(text).split() if len(w.strip(".,!?;:।")) >= 3 and w.strip(".,!?;:।") not in stop}


def similarity(a, b):
    x, y = words(a), words(b)
    return len(x & y) / len(x | y) if x | y else 0.0


def build_candidate(segments, i, min_s=60, max_s=180):
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
    selected = segments[left:right+1]
    if any(looks_hallucinated_nepali(clean(s.get("nepali", ""))) for s in selected):
        return {
            "start": round(start,3), "end": round(end,3), "duration": round(end-start,3),
            "score": -9999, "text": "", "hook_text": "", "avg_logprob": -10.0,
            "max_transcript_gap": 9999.0,
        }
    text = " ".join(clean(s.get("nepali")) for s in selected)
    opening_text = " ".join(clean(s.get("nepali")) for s in selected[:2])
    logs = [float(s.get("avg_logprob", 0.0)) for s in selected if s.get("avg_logprob") is not None]
    avg_logprob = sum(logs) / len(logs) if logs else None
    max_gap = 0.0
    for previous, current in zip(selected, selected[1:]):
        gap = max(
            0.0,
            float(current.get("start", 0)) - float(previous.get("end", 0)),
        )
        max_gap = max(max_gap, gap)
    return {
        "start": round(start,3), "end": round(end,3),
        "duration": round(end-start,3), "score": score(text, avg_logprob),
        "text": text, "hook_text": opening_text, "avg_logprob": avg_logprob,
        "max_transcript_gap": round(max_gap, 3),
    }

def build_long_windows(segments, max_windows=3):
    """Create coherent 3–5 minute windows around strong transcript anchors."""
    if not segments:
        return []
    total_start = float(segments[0].get("start", 0))
    total_end = float(segments[-1].get("end", total_start))
    if total_end - total_start < 181:
        return []

    anchors = []
    for i, seg in enumerate(segments):
        text = clean(seg.get("nepali"))
        if text:
            anchors.append((score(text), float(seg.get("start", 0)), i))
    anchors.sort(reverse=True)

    windows = []
    for _, anchor_start, _ in anchors[:max_windows * 4]:
        # Build roughly 3–5 minutes around the strongest point while staying
        # inside the actual Parliament recording.
        start_target = max(total_start, min(anchor_start - 45, total_end - 240))
        end_target = min(total_end, start_target + 240)
        if end_target - start_target < 181:
            start_target = max(total_start, end_target - 181)

        left = min(range(len(segments)), key=lambda j: abs(float(segments[j].get("start", 0)) - start_target))
        right = next(
            (j for j in range(left, len(segments))
             if float(segments[j].get("end", 0)) >= end_target),
            len(segments) - 1,
        )
        start = float(segments[left].get("start", start_target))
        end = float(segments[right].get("end", end_target))
        if 181 <= end - start <= 300:
            window_segments = segments[left:right + 1]
            if any(looks_hallucinated_nepali(clean(s.get("nepali", ""))) for s in window_segments):
                continue
            text = " ".join(clean(s.get("nepali")) for s in window_segments)
            hook_text = " ".join(clean(s.get("nepali")) for s in segments[left:min(left + 2, right + 1)])
            logs = [float(s.get("avg_logprob", 0.0)) for s in segments[left:right + 1] if s.get("avg_logprob") is not None]
            avg_logprob = sum(logs) / len(logs) if logs else None
            if avg_logprob is not None and avg_logprob < -0.95:
                continue
            if looks_hallucinated_nepali(text):
                continue
            windows.append({
                "start": round(start, 3), "end": round(end, 3),
                "duration": round(end - start, 3),
                "score": score(text, avg_logprob), "text": text, "hook_text": hook_text,
                "avg_logprob": avg_logprob,
            })

    unique = {}
    for w in windows:
        unique[(w["start"], w["end"])] = w
    return list(unique.values())

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
        # Speaker names are optional. Never infer a name from a procedural
        # Parliament page label; keep the story attributable to the official
        # source page and House even when no member name is exposed.
        for i, seg in enumerate(segments):
            if not clean(seg.get("nepali")):
                continue
            c = build_candidate(segments, i)
            if looks_hallucinated_nepali(c.get("text", "")):
                continue
            if c["duration"] < 60 or c["duration"] > 180:
                continue
            if c.get("avg_logprob") is not None and c["avg_logprob"] < -0.95:
                continue
            if speaker.lower() in GENERIC_SPEAKERS:
                speaker = ""
            c.update({
                "video": video,
                "transcript": str(transcript_file),
                "speaker": speaker,
                "house": vm.get("house", ""),
                "source_page": vm.get("page", ""),
                "page_title": vm.get("page_title", ""),
                "collection_title": vm.get("collection_title", ""),
            })
            candidates.append(c)

    candidates.sort(key=lambda x: x["score"], reverse=True)

    long_candidates = []
    for transcript_file in sorted(Path(input_dir).glob("video_*.json")):
        data = json.loads(transcript_file.read_text(encoding="utf-8"))
        segments = data.get("segments", [])
        video = str(Path("data/videos") / (transcript_file.stem + ".mp4"))
        vm = meta.get(video, {})
        speaker = clean(vm.get("speaker"))
        for w in build_long_windows(segments):
            sp = clean(vm.get("speaker"))
            if sp.lower() in GENERIC_SPEAKERS:
                sp = ""
            w.update({"video": video, "transcript": str(transcript_file),
                      "speaker": sp, "house": vm.get("house", ""),
                      "source_page": vm.get("page", ""), "page_title": vm.get("page_title", ""),
                      "collection_title": vm.get("collection_title", "")})
            long_candidates.append(w)
    long_candidates.sort(key=lambda x: x["score"], reverse=True)

    # Keep a genuinely diverse candidate pool. The old top-score pool could
    # be dominated by the same few videos, leaving no unused source material
    # for Shorts after the Long selection. Reserve candidates across sources.
    pool, per_video = [], {}
    for c in candidates:
        if per_video.get(c["video"], 0) >= 3:
            continue
        pool.append(c)
        per_video[c["video"]] = per_video.get(c["video"], 0) + 1
        if len(pool) >= 120:
            break

    # Build a second, source-diverse pool specifically for Shorts. Do not let
    # procedural page titles alone discard usable transcript windows: the
    # transcript itself is the editorial evidence. We only reject very short
    # or very low-information transcript windows.
    used = set()
    short_source_pool, short_per_video = [], {}
    for c in candidates:
        if c["video"] in used:
            continue
        text_value = clean(c.get("text", ""))
        if looks_hallucinated_nepali(text_value):
            continue
        if len(text_value) < 80:
            continue
        if c.get("avg_logprob") is not None and c["avg_logprob"] < -0.95:
            continue
        # A long transcript gap usually corresponds to silence/dead air in the
        # source recording. Shorts must stay within continuous speech windows.
        if c.get("max_transcript_gap", 0) > 5.0:
            continue
        if short_per_video.get(c["video"], 0) >= 2:
            continue
        short_source_pool.append(c)
        short_per_video[c["video"]] = short_per_video.get(c["video"], 0) + 1
        if len(short_source_pool) >= 120:
            break

    long_stories = []
    used = set()
    long_source_count = {}
    used_ranges = {}
    houses = []
    for candidate in long_candidates:
        house = clean(candidate.get("house"))
        if house and house not in houses:
            houses.append(house)

    # Prefer one Long story from each House. Speaker attribution is used only
    # when the official page exposes a verified name; otherwise the story remains
    # unattributed rather than blocking the entire daily build.
    house_order = []
    for candidate in long_candidates:
        house = clean(candidate.get("house"))
        if house and house not in house_order:
            house_order.append(house)

    preferred_houses = house_order[:2] if len(house_order) >= 2 else house_order

    for preferred_house in preferred_houses:
        house_candidates = [c for c in long_candidates if clean(c.get("house")) == preferred_house]

        # Prefer substantive/member-led source pages. Procedural labels such as
        # "Annual Report", "Zero Hour" or "Bill Presented" are not speaker
        # attribution and should not become the main Long story when a
        # non-procedural window exists for the same House.
        substantive = [c for c in house_candidates if not is_procedural_label(c.get("page_title", ""))]
        # Prefer member/topic pages when available, but do not make a
        # procedural archive label a hard exclusion. The transcript itself
        # remains the evidence for whether the window is substantive.
        if substantive:
            house_candidates = substantive

        house_candidates.sort(
            key=lambda c: (
                1 if clean(c.get("speaker")) else 0,
                c.get("score", 0),
            ),
            reverse=True,
        )
        for candidate in house_candidates:
            if len(long_stories) >= 2:
                break
            video = candidate["video"]
            if video in used or long_source_count.get(video, 0) >= 1:
                continue
            ranges = used_ranges.setdefault(video, [])
            if any(abs(candidate["start"] - s) < 60 for s, e in ranges):
                continue
            long_stories.append(enrich_piece({
                "pieces": [candidate],
                "duration": candidate["duration"],
                "score": candidate["score"],
                "speakers": [candidate["speaker"]] if candidate.get("speaker") else [],
                "houses": [candidate["house"]],
                "topic_text": candidate["text"],
            }))
            long_source_count[video] = 1
            ranges.append((candidate["start"], candidate["end"]))
            used.add(video)
            break

    # If one House did not produce a standalone 181+ second window, build its
    # Long story from two related transcript windows from that same House first.
    # This prevents the second Long slot from silently becoming another story
    # from the already-covered House.
    required_houses = [h for h in ("House of Representatives", "National Assembly") if h]
    covered_houses = {h for s in long_stories for h in (s.get("houses") or [])}
    missing_houses = [h for h in required_houses if h not in covered_houses]

    for missing_house in missing_houses:
        if len(long_stories) >= 2:
            break
        house_pool = [
            c for c in pool
            if clean(c.get("house")) == missing_house
            and c["video"] not in used
        ]
        house_pool.sort(key=lambda c: (1 if clean(c.get("speaker")) else 0, c.get("score", 0)), reverse=True)
        added = False
        for anchor in house_pool:
            related = sorted(
                [x for x in house_pool if x["video"] != anchor["video"] and x["video"] not in used],
                key=lambda x: (similarity(anchor["text"], x["text"]), x["score"]),
                reverse=True,
            )
            for other in related:
                total = anchor["duration"] + other["duration"]
                if not 181 <= total <= 600:
                    continue
                if similarity(anchor["text"], other["text"]) < 0.02:
                    continue
                long_stories.append(enrich_piece({
                    "pieces": [anchor, other],
                    "duration": round(total, 3),
                    "score": anchor["score"] + other["score"] + 8,
                    "speakers": [x["speaker"] for x in (anchor, other) if x.get("speaker")],
                    "houses": [missing_house],
                    "topic_text": anchor["text"] + " " + other["text"],
                    "source_title": " / ".join(x.get("page_title", "") for x in (anchor, other) if x.get("page_title")),
                }))
                used.update([anchor["video"], other["video"]])
                added = True
                break
            if added:
                break

    # Fill any remaining Long slot from the strongest unused substantive window,
    # but never violate the both-Houses requirement when both Houses are present.
    if len(long_stories) < 2:
        for candidate in long_candidates:
            if len(long_stories) >= 2:
                break
            video = candidate["video"]
            house = clean(candidate.get("house"))
            if video in used or long_source_count.get(video, 0) >= 1:
                continue
            if required_houses and any(h not in {x for s in long_stories for x in (s.get("houses") or [])} for h in required_houses):
                # Defer generic fill while a required House is still missing.
                continue
            long_stories.append(enrich_piece({
                "pieces": [candidate],
                "duration": candidate["duration"],
                "score": candidate["score"],
                "speakers": [candidate["speaker"]] if candidate.get("speaker") else [],
                "houses": [house] if house else [],
                "topic_text": candidate["text"],
            }))
            long_source_count[video] = 1
            used.add(video)

    # Final fallback: combine related transcript windows only after House balance
    # has been attempted. Never create a second Long from a single already-used
    # House when both Houses are available.
    if len(long_stories) < 2:
        for anchor in pool:
            if len(long_stories) >= 2 or anchor["video"] in used:
                break
            related = sorted(
                [x for x in pool if x["video"] not in used and x["video"] != anchor["video"]],
                key=lambda x: (similarity(anchor["text"], x["text"]), x["score"]), reverse=True)
            for other in related:
                total = anchor["duration"] + other["duration"]
                if not 181 <= total <= 600:
                    continue
                sim = similarity(anchor["text"], other["text"])
                if sim < 0.02:
                    continue
                long_stories.append(enrich_piece({
                    "pieces": [anchor, other], "duration": round(total,3),
                    "score": anchor["score"] + other["score"] + 8,
                    "speakers": [x["speaker"] for x in (anchor, other) if x["speaker"]],
                    "houses": sorted({x["house"] for x in (anchor, other) if x["house"]}),
                    "topic_text": anchor["text"] + " " + other["text"],
                    "source_title": " / ".join(x.get("page_title", "") for x in (anchor, other) if x.get("page_title")),
                }))
                used.update([anchor["video"], other["video"]])
                break

    short_stories = []
    short_used = set()
    short_pool = sorted(
        short_source_pool,
        key=lambda c: (
            1 if clean(c.get("speaker")) else 0,
            c.get("score", 0),
            len(clean(c.get("text", ""))),
        ),
        reverse=True,
    )
    for c in short_pool:
        if c["video"] in used or c["video"] in short_used:
            continue
        # A procedural page title is not a speaker name, but it can still
        # contain a substantive transcript window. Do not discard the clip
        # solely because the archive label is procedural; transcript quality
        # and topic relevance are the editorial evidence.
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
                "source_title": piece.get("page_title", ""),
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
                "source_title": c2.get("page_title", ""),
                "video": c2["video"],
            }))
            short_used.add(c["video"])
        if len(short_stories) >= 2:
            break

    result = {
        "model": "parliament-multi-story-v2-editorial-hooks",
        "target": {"long": 2, "short": 2},
        "selection_rules": [
            "Candidate pool comes from both National Assembly and House of Representatives.",
            "Speaker names are included only when exposed by the official Parliament video page; otherwise no name is inferred.",
            "Long stories are 181–600 seconds and use distinct parliamentary source windows.",
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
    long_houses = {h for s in long_stories for h in (s.get("houses") or []) if h}
    if len(long_houses) < 2 and {"House of Representatives", "National Assembly"} <= set(houses):
        raise RuntimeError(
            f"Long stories must represent both Parliament Houses; found {sorted(long_houses)}. "
            "The selector will not substitute a second story from the same House."
        )
    if len(long_stories) < 2 or len(short_stories) < 2:
        raise RuntimeError(
            f"Not enough diverse stories for a safe 2+2 daily build: "
            f"{len(long_stories)} long, {len(short_stories)} short. "
            "Speaker names are optional; the failure means there were not enough "
            "substantive, transcript-grounded source windows."
        )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python src/batch_analyze_v2.py <transcripts_clean_dir> <selection_json>")
        raise SystemExit(1)
    main(sys.argv[1], sys.argv[2])
