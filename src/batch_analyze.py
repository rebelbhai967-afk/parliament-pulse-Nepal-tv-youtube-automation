import json
import re
import sys
from pathlib import Path


KEYWORDS = {
    "प्रधानमन्त्री": 5,
    "मन्त्री": 4,
    "अर्थमन्त्री": 5,
    "सभामुख": 3,
    "अध्यक्ष": 3,
    "सांसद": 2,
    "सरकार": 3,
    "कानुन": 4,
    "विधेयक": 4,
    "संशोधन": 4,
    "बजेट": 5,
    "कर": 3,
    "नीति": 3,
    "योजना": 3,
    "भ्रष्टाचार": 6,
    "अनियमितता": 6,
    "जवाफ": 4,
    "प्रश्न": 3,
    "निर्णय": 4,
    "महत्वपूर्ण": 3,
    "संविधान": 4,
    "शिक्षा": 3,
    "स्वास्थ्य": 3,
    "रोजगारी": 3,
    "महँगी": 4,
    "विकास": 3,
    "सुरक्षा": 3,
    "सीमा": 4,
    "प्रतिवेदन": 4,
    "वार्षिक": 3,
}

QUESTION_WORDS = [
    "किन",
    "के",
    "कसरी",
    "कहिले",
    "कहाँ",
    "कति",
    "हुन्छ",
    "गर्नुहुन्छ",
    "बताउनुहोस्",
]

STRONG_PHRASES = [
    "गम्भीर",
    "आवश्यक",
    "तत्काल",
    "सरकारले",
    "सरकारको",
    "मन्त्रालयले",
    "मन्त्रालयको",
    "निर्णय",
    "घोषणा",
    "प्रस्ताव",
    "प्रतिवेदन",
]


def clean_text(text):
    return re.sub(r"\s+", " ", str(text).strip())


def keyword_score(text):
    return sum(weight for keyword, weight in KEYWORDS.items() if keyword in text)


def question_score(text):
    score = sum(2 for word in QUESTION_WORDS if word in text)
    if "?" in text:
        score += 2
    return score


def statement_score(text):
    return sum(2 for phrase in STRONG_PHRASES if phrase in text)


def length_score(text):
    length = len(text)
    if 80 <= length <= 500:
        return 5
    if 40 <= length < 80 or 500 < length <= 800:
        return 3
    return 1


def score_segment(segment):
    text = clean_text(segment.get("nepali", ""))
    return (
        keyword_score(text)
        + question_score(text)
        + statement_score(text)
        + length_score(text)
    )


def build_candidate(segments, index, min_duration, max_duration):
    center = segments[index]
    center_start = float(center.get("start", 0))
    center_end = float(center.get("end", center_start))

    left = index
    right = index
    clip_start = center_start
    clip_end = center_end

    while (clip_end - clip_start) < min_duration:
        can_left = left > 0
        can_right = right < len(segments) - 1
        if not can_left and not can_right:
            break

        left_duration = (
            clip_end - float(segments[left - 1].get("start", clip_start))
            if can_left else -1
        )
        right_duration = (
            float(segments[right + 1].get("end", clip_end)) - clip_start
            if can_right else -1
        )

        if can_left and (not can_right or left_duration <= right_duration):
            left -= 1
            clip_start = float(segments[left].get("start", clip_start))
        elif can_right:
            right += 1
            clip_end = float(segments[right].get("end", clip_end))

    while (clip_end - clip_start) > max_duration and left < right:
        left_span = float(segments[left + 1].get("start", clip_start)) - clip_start
        right_span = clip_end - float(segments[right - 1].get("end", clip_end))
        if left_span >= right_span:
            left += 1
            clip_start = float(segments[left].get("start", clip_start))
        else:
            right -= 1
            clip_end = float(segments[right].get("end", clip_end))

    selected = segments[left:right + 1]
    text = " ".join(clean_text(item.get("nepali", "")) for item in selected)

    return {
        "start": round(clip_start, 3),
        "end": round(clip_end, 3),
        "duration": round(max(0, clip_end - clip_start), 3),
        "score": score_segment(center),
        "text": text,
        "center_text": clean_text(center.get("nepali", "")),
    }


def topic_words(text):
    ignored = {
        "को", "का", "की", "ले", "लाई", "मा", "बाट", "र", "तर", "पनि",
        "छ", "हो", "हुन", "भएको", "गरेको", "गर्ने", "गर्न", "भन्ने",
        "हामी", "तपाईं", "उहाँ", "यस", "यो", "त्यो",
    }

    return {
        word.strip(".,!?;:।")
        for word in text.split()
        if len(word.strip(".,!?;:।")) >= 3
        and word.strip(".,!?;:।") not in ignored
    }


def topic_similarity(first_text, second_text):
    first = topic_words(first_text)
    second = topic_words(second_text)
    union = first | second
    if not union:
        return 0.0
    return len(first & second) / len(union)


def add_video_context(candidate, transcript_file):
    candidate["video"] = str(Path("data/videos") / (transcript_file.stem + ".mp4"))
    candidate["transcript"] = str(transcript_file)
    return candidate


def candidates_for_duration(segments, min_duration, max_duration):
    candidates = []
    for index, segment in enumerate(segments):
        if not clean_text(segment.get("nepali", "")):
            continue
        candidate = build_candidate(
            segments, index, min_duration=min_duration, max_duration=max_duration
        )
        if min_duration <= candidate["duration"] <= max_duration:
            candidates.append(candidate)
    return candidates


def load_transcript(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def analyze_all_transcripts(input_dir, output_file):
    input_path = Path(input_dir)
    output_path = Path(output_file)
    transcript_files = sorted(input_path.glob("video_*.json"))

    if not transcript_files:
        raise RuntimeError("No transcript files found.")

    long_candidates = []
    short_candidates = []

    for transcript_file in transcript_files:
        print(f"\nAnalyzing: {transcript_file}")
        data = load_transcript(transcript_file)
        segments = data.get("segments", [])

        for candidate in candidates_for_duration(segments, 181, 600):
            long_candidates.append(add_video_context(candidate, transcript_file))

        for candidate in candidates_for_duration(segments, 20, 89):
            short_candidates.append(add_video_context(candidate, transcript_file))

    if not long_candidates:
        raise RuntimeError(
            "No valid Long story found with duration between 181 and 600 seconds."
        )

    long_candidates.sort(key=lambda item: item["score"], reverse=True)
    short_candidates.sort(key=lambda item: item["score"], reverse=True)

    long_story = long_candidates[0]
    short_story = None

    for candidate in short_candidates:
        if candidate["video"] == long_story["video"]:
            continue
        if topic_similarity(candidate["text"], long_story["text"]) >= 0.35:
            continue
        short_story = candidate
        break

    alternatives = []
    for candidate in long_candidates[1:] + short_candidates:
        if short_story is not None and candidate is short_story:
            continue
        if candidate["video"] == long_story["video"]:
            continue
        if topic_similarity(candidate["text"], long_story["text"]) >= 0.35:
            continue
        alternatives.append(candidate)
        if len(alternatives) >= 10:
            break

    result = {
        "model": "parliament-story-selector-v6-duration-aware",
        "input_transcripts": [str(file) for file in transcript_files],
        "total_long_candidates": len(long_candidates),
        "total_short_candidates": len(short_candidates),
        "selection_rules": [
            "Long story is selected only from candidates that actually reach 181–600 seconds.",
            "Short/Reel must come from a different Parliament video.",
            "Short/Reel should have a different topic from the Long story.",
            "Short/Reel is kept between 20 and 89 seconds.",
            "Candidates that cannot satisfy the requested duration are excluded.",
            "If no separate Short story exists, short_video is null.",
        ],
        "long_video": long_story,
        "short_video": short_story,
        "alternatives": alternatives,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)

    print("\n====================================")
    print("DAILY PARLIAMENT STORY SELECTION")
    print("====================================")
    print("\nLONG VIDEO")
    print(f"Video: {long_story['video']}")
    print(f"Score: {long_story['score']}")
    print(f"Start: {long_story['start']}")
    print(f"End: {long_story['end']}")
    print(f"Duration: {long_story['duration']}s")

    print("\nSHORT / REEL")
    if short_story:
        print(f"Video: {short_story['video']}")
        print(f"Score: {short_story['score']}")
        print(f"Start: {short_story['start']}")
        print(f"End: {short_story['end']}")
        print(f"Duration: {short_story['duration']}s")
    else:
        print("No separate Short story found.")

    print(f"\nOutput: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage:")
        print("python src/batch_analyze.py <transcript_directory> <output_json>")
        sys.exit(1)

    analyze_all_transcripts(sys.argv[1], sys.argv[2])
