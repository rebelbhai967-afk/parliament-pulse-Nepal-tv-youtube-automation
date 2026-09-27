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
    text = re.sub(
        r"\s+",
        " ",
        text
    )
    return text


def keyword_score(text):
    score = 0

    for keyword, points in KEYWORDS.items():
        if keyword in text:
            score += points

    return score


def question_score(text):
    score = 0

    for word in QUESTION_WORDS:
        if word in text:
            score += 2

    if "?" in text:
        score += 3

    return score


def statement_score(text):
    score = 0

    for phrase in STRONG_PHRASES:
        if phrase in text:
            score += 2

    return score


def length_score(text):
    count = len(
        text.split()
    )

    if count >= 12:
        return 2

    if count >= 6:
        return 1

    return 0


def score_segment(segment):
    text = clean_text(
        segment.get(
            "nepali",
            ""
        )
    )

    score = 0

    score += keyword_score(text)
    score += question_score(text)
    score += statement_score(text)
    score += length_score(text)

    return {
        "start": float(
            segment.get(
                "start",
                0
            )
        ),
        "end": float(
            segment.get(
                "end",
                0
            )
        ),
        "nepali": text,
        "score": score,
    }


def build_candidate(
    segments,
    index
):
    start_index = max(
        0,
        index - 1
    )

    end_index = min(
        len(segments) - 1,
        index + 1
    )

    selected = segments[
        start_index:end_index + 1
    ]

    start = selected[0][
        "start"
    ]

    end = selected[-1][
        "end"
    ]

    if end - start > 60:
        end = start + 60

    text = " ".join(
        item["nepali"]
        for item in selected
    )

    score = sum(
        item["score"]
        for item in selected
    )

    return {
        "start": round(
            start,
            3
        ),
        "end": round(
            end,
            3
        ),
        "duration": round(
            end - start,
            3
        ),
        "score": score,
        "nepali": text.strip(),
    }


def score_transcript(
    transcript_file
):
    with open(
        transcript_file,
        "r",
        encoding="utf-8"
    ) as file:

        transcript = json.load(
            file
        )

    segments = transcript.get(
        "segments",
        []
    )

    scored = []

    for segment in segments:

        item = score_segment(
            segment
        )

        if item["nepali"]:
            scored.append(item)

    candidates = []

    for index in range(
        len(scored)
    ):

        if scored[index][
            "score"
        ] <= 0:
            continue

        candidate = build_candidate(
            scored,
            index
        )

        candidates.append(
            candidate
        )

    candidates.sort(
        key=lambda item: (
            item["score"],
            item["duration"]
        ),
        reverse=True
    )

    return transcript, candidates


def overlaps(
    first,
    second
):
    return (
        first["start"] < second["end"]
        and first["end"] > second["start"]
    )


def topic_words(text):
    text = clean_text(
        text
    )

    words = set(
        text.split()
    )

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

    return {
        word
        for word in words
        if len(word) >= 3
        and word not in ignored
    }


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
        return 0

    intersection = len(
        first & second
    )

    union = len(
        first | second
    )

    if union == 0:
        return 0

    return intersection / union


def choose_best_candidate(
    candidates,
    selected,
    same_video=False
):
    for candidate in candidates:

        blocked = False

        for existing in selected:

            # Same video + overlapping time
            if (
                candidate["video"]
                == existing["video"]
                and overlaps(
                    candidate,
                    existing
                )
            ):
                blocked = True
                break

            # Same video but very similar topic
            if (
                candidate["video"]
                == existing["video"]
            ):

                similarity = topic_similarity(
                    candidate["nepali"],
                    existing["nepali"]
                )

                if similarity >= 0.35:
                    blocked = True
                    break

        if blocked:
            continue

        return candidate

    return None


def analyze_all_transcripts(
    input_dir,
    output_file
):
    input_path = Path(
        input_dir
    )

    output_path = Path(
        output_file
    )

    transcript_files = sorted(
        input_path.glob(
            "video_*.json"
        )
    )

    transcript_files = [
        file
        for file in transcript_files
        if file.name
        != "transcription_summary.json"
    ]

    if not transcript_files:
        raise RuntimeError(
            f"No transcript files found "
            f"in {input_path}"
        )

    all_candidates = []

    print("")
    print(
        "===================================="
    )

    print(
        "BATCH PARLIAMENT ANALYSIS"
    )

    print(
        "===================================="
    )

    print(
        f"Transcript files: "
        f"{len(transcript_files)}"
    )

    for transcript_file in transcript_files:

        print("")
        print(
            f"Analyzing: "
            f"{transcript_file.name}"
        )

        try:

            transcript, candidates = (
                score_transcript(
                    transcript_file
                )
            )

            video_file = transcript.get(
                "video"
            )

            if not video_file:
                video_file = (
                    "data/videos/"
                    + transcript_file.stem
                    + ".mp4"
                )

            for candidate in candidates:

                candidate["video"] = (
                    video_file
                )

                candidate[
                    "transcript"
                ] = str(
                    transcript_file
                )

            all_candidates.extend(
                candidates
            )

            print(
                f"Candidates: "
                f"{len(candidates)}"
            )

        except Exception as error:

            print(
                f"Failed: {error}"
            )

    if not all_candidates:
        raise RuntimeError(
            "No useful Parliament "
            "candidates found."
        )

    all_candidates.sort(
        key=lambda item: (
            item["score"],
            item["duration"]
        ),
        reverse=True
    )

    selected = []

    # -----------------------------------------
    # LONG VIDEO
    # -----------------------------------------

    long_video = (
        all_candidates[0].copy()
    )

    long_video[
        "type"
    ] = "long_video"

    long_video[
        "rank"
    ] = 1

    selected.append(
        long_video
    )

    # -----------------------------------------
    # SHORT / REEL
    # -----------------------------------------

    short_video = (
        choose_best_candidate(
            all_candidates,
            selected
        )
    )

    if short_video:

        short_video = (
            short_video.copy()
        )

        short_video[
            "type"
        ] = "short_video"

        short_video[
            "rank"
        ] = 1

        selected.append(
            short_video
        )

    # -----------------------------------------
    # ALTERNATIVES
    # -----------------------------------------

    alternatives = []

    for candidate in all_candidates:

        if any(
            candidate is item
            for item in selected
        ):
            continue

        blocked = False

        for existing in selected:

            if (
                candidate["video"]
                == existing["video"]
                and overlaps(
                    candidate,
                    existing
                )
            ):
                blocked = True
                break

            similarity = topic_similarity(
                candidate["nepali"],
                existing["nepali"]
            )

            if similarity >= 0.35:
                blocked = True
                break

        if blocked:
            continue

        alternatives.append(
            candidate
        )

        if len(alternatives) >= 10:
            break

    result = {
        "model": (
            "daily-multi-video-selector-v1"
        ),

        "input_transcripts": len(
            transcript_files
        ),

        "total_candidates": len(
            all_candidates
        ),

        "selection_rules": {
            "long_video": (
                "Highest-scoring "
                "important Parliament story."
            ),
            "short_video": (
                "Separate Parliament story "
                "from a different video or "
                "different topic."
            ),
            "avoid_duplicate_story": True,
            "avoid_overlapping_clip": True
        },

        "long_video": long_video,

        "short_video": short_video,

        "alternatives": alternatives,
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

    # -----------------------------------------
    # PRINT RESULT
    # -----------------------------------------

    print("")
    print(
        "===================================="
    )

    print(
        "DAILY CONTENT SELECTION"
    )

    print(
        "===================================="
    )

    print("")
    print(
        "LONG VIDEO"
    )

    print(
        "------------------------------------"
    )

    print(
        f"Video: "
        f"{long_video['video']}"
    )

    print(
        f"Score: "
        f"{long_video['score']}"
    )

    print(
        f"Time: "
        f"{long_video['start']} - "
        f"{long_video['end']}"
    )

    print(
        long_video["nepali"][:700]
    )

    print("")

    print(
        "SHORT / REEL"
    )

    print(
        "------------------------------------"
    )

    if short_video:

        print(
            f"Video: "
            f"{short_video['video']}"
        )

        print(
            f"Score: "
            f"{short_video['score']}"
        )

        print(
            f"Time: "
            f"{short_video['start']} - "
            f"{short_video['end']}"
        )

        print(
            short_video["nepali"][:700]
        )

    else:

        print(
            "No separate Short/Reel story found."
        )

    print("")

    print(
        f"Saved: {output_path}"
    )


if __name__ == "__main__":

    if len(sys.argv) != 3:

        print("Usage:")

        print(
            "python batch_analyze.py "
            "<transcript_directory> "
            "<output_json>"
        )

        sys.exit(1)

    input_directory = sys.argv[1]

    output_json = sys.argv[2]

    analyze_all_transcripts(
        input_directory,
        output_json
    )
