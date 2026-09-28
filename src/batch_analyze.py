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
    text = str(text).strip()

    return re.sub(
        r"\s+",
        " ",
        text
    )


def keyword_score(text):
    score = 0

    for keyword, weight in KEYWORDS.items():
        if keyword in text:
            score += weight

    return score


def question_score(text):
    score = 0

    for word in QUESTION_WORDS:
        if word in text:
            score += 2

    if "?" in text:
        score += 2

    return score


def statement_score(text):
    score = 0

    for phrase in STRONG_PHRASES:
        if phrase in text:
            score += 2

    return score


def length_score(text):
    length = len(text)

    if 80 <= length <= 500:
        return 5

    if 40 <= length < 80:
        return 3

    if 500 < length <= 800:
        return 3

    return 1


def score_segment(segment):
    text = clean_text(
        segment.get("nepali", "")
    )

    score = 0

    score += keyword_score(text)
    score += question_score(text)
    score += statement_score(text)
    score += length_score(text)

    return score


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
        "को",
        "का",
        "की",
        "ले",
        "लाई",
        "मा",
        "बाट",
        "र",
        "तर",
        "पनि",
        "छ",
        "हो",
        "हुन",
        "भएको",
        "गरेको",
        "गर्ने",
        "गर्न",
        "भन्ने",
        "हामी",
        "तपाईं",
        "उहाँ",
        "यस",
        "यो",
        "त्यो",
    }

    words = set()

    for word in text.split():
        word = word.strip(
            ".,!?;:।"
        )

        if (
            len(word) >= 3
            and word not in ignored
        ):
            words.add(word)

    return words


def topic_similarity(
    first_text,
    second_text
):
    first = topic_words(
        first_text
    )

    second = topic_words(
        second_text
    )

    if not first or not second:
        return 0.0

    intersection = first & second
    union = first | second

    if not union:
        return 0.0

    return len(intersection) / len(union)


def overlaps(first, second):
    return not (
        first["end"] <= second["start"]
        or second["end"] <= first["start"]
    )


def score_transcript(
    transcript_file
):
    with open(
        transcript_file,
        "r",
        encoding="utf-8"
    ) as file:
        data = json.load(file)

    segments = data.get(
        "segments",
        []
    )

    candidates = []

    for index, segment in enumerate(
        segments
    ):
        text = clean_text(
            segment.get(
                "nepali",
                ""
            )
        )

        if not text:
            continue

        candidate = build_candidate(
            segments,
            index,
            min_duration=20,
            max_duration=89
        )

        if 20 <= candidate["duration"] <= 89:
            candidates.append(candidate)

    return candidates


def choose_short_story(
    candidates,
    long_story
):
    for candidate in candidates:
        # Short must come from a DIFFERENT
        # Parliament video.
        if (
            candidate["video"]
            == long_story["video"]
        ):
            continue

        # Avoid almost identical topic.
        similarity = topic_similarity(
            candidate["text"],
            long_story["text"]
        )

        if similarity >= 0.35:
            continue

        return candidate

    return None


def analyze_all_transcripts(
    input_dir,
    output_file
):
    input_path = Path(input_dir)
    output_path = Path(output_file)

    transcript_files = sorted(
        input_path.glob(
            "video_*.json"
        )
    )

    if not transcript_files:
        raise RuntimeError(
            "No transcript files found."
        )

    all_candidates = []

    for transcript_file in transcript_files:
        print("")
        print(
            f"Analyzing: "
            f"{transcript_file}"
        )

        candidates = score_transcript(
            transcript_file
        )

        video_name = (
            transcript_file.stem
            + ".mp4"
        )

        video_path = (
            Path("data/videos")
            / video_name
        )

        for candidate in candidates:
            candidate["video"] = str(
                video_path
            )

            candidate["transcript"] = str(
                transcript_file
            )

            all_candidates.append(
                candidate
            )

    if not all_candidates:
        raise RuntimeError(
            "No story candidates found."
        )

    all_candidates.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    long_center = all_candidates[0]
    source_transcript = Path(long_center["transcript"])
    with open(source_transcript, "r", encoding="utf-8") as file:
        source_data = json.load(file)
    source_segments = source_data.get("segments", [])
    center_index = min(
        range(len(source_segments)),
        key=lambda i: abs(float(source_segments[i].get("start", 0)) - long_center["start"])
    )
    long_story = build_candidate(
        source_segments,
        center_index,
        min_duration=181,
        max_duration=600
    )
    long_story["score"] = long_center["score"]
    long_story["video"] = long_center["video"]
    long_story["transcript"] = long_center["transcript"]

    short_story = None

    for candidate in all_candidates[1:]:
        if (
            candidate["video"]
            == long_story["video"]
        ):
            continue

        similarity = topic_similarity(
            candidate["text"],
            long_story["text"]
        )

        if similarity >= 0.35:
            continue

        short_story = candidate
        break

    alternatives = []

    for candidate in all_candidates:
        if candidate is long_story:
            continue

        if short_story is not None:
            if candidate is short_story:
                continue

        if (
            candidate["video"]
            == long_story["video"]
        ):
            continue

        similarity = topic_similarity(
            candidate["text"],
            long_story["text"]
        )

        if similarity >= 0.35:
            continue

        alternatives.append(
            candidate
        )

    result = {
        "model": (
            "parliament-story-selector-v5-duration-aware"
        ),
        "input_transcripts": [
            str(file)
            for file in transcript_files
        ],
        "total_candidates": len(
            all_candidates
        ),
        "selection_rules": [
            "Long story uses the highest-scoring candidate center and expands to 181–600 seconds.",
            "Short/Reel must come from a different Parliament video.",
            "Short/Reel should have a different topic from the Long story.",
            "Short/Reel is kept between 20 and 89 seconds.",
            "Overlapping or highly similar stories are excluded.",
            "If no separate story exists, short_video is null."
        ],
        "long_video": long_story,
        "short_video": short_story,
        "alternatives": alternatives[:10],
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("")
    print("====================================")
    print("DAILY PARLIAMENT STORY SELECTION")
    print("====================================")

    print("")
    print("LONG VIDEO")
    print(
        f"Video: "
        f"{long_story['video']}"
    )
    print(
        f"Score: "
        f"{long_story['score']}"
    )
    print(
        f"Start: "
        f"{long_story['start']}"
    )
    print(
        f"End: "
        f"{long_story['end']}"
    )

    print("")
    print("SHORT / REEL")

    if short_story:
        print(
            f"Video: "
            f"{short_story['video']}"
        )
        print(
            f"Score: "
            f"{short_story['score']}"
        )
        print(
            f"Start: "
            f"{short_story['start']}"
        )
        print(
            f"End: "
            f"{short_story['end']}"
        )
    else:
        print(
            "No separate Short story found."
        )

    print("")
    print(
        f"Output: {output_path}"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage:")
        print(
            "python src/batch_analyze.py "
            "<transcript_directory> "
            "<output_json>"
        )
        sys.exit(1)

    analyze_all_transcripts(
        sys.argv[1],
        sys.argv[2]
    )
