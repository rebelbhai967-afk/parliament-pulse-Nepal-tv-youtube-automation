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


def clean_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text


def keyword_score(text: str) -> int:
    score = 0

    for keyword, points in KEYWORDS.items():
        if keyword in text:
            score += points

    return score


def question_score(text: str) -> int:
    score = 0

    for word in QUESTION_WORDS:
        if word in text:
            score += 2

    if "?" in text:
        score += 3

    return score


def statement_score(text: str) -> int:
    score = 0

    for phrase in STRONG_PHRASES:
        if phrase in text:
            score += 2

    return score


def length_score(text: str) -> int:
    words = text.split()
    count = len(words)

    if count >= 12:
        return 2

    if count >= 6:
        return 1

    return 0


def score_segment(segment: dict) -> dict:
    text = clean_text(
        segment.get("nepali", "")
    )

    score = 0

    score += keyword_score(text)
    score += question_score(text)
    score += statement_score(text)
    score += length_score(text)

    return {
        "start": float(
            segment.get("start", 0)
        ),
        "end": float(
            segment.get("end", 0)
        ),
        "nepali": text,
        "score": score,
    }


def build_clip(
    segments: list,
    center_index: int
) -> dict:

    start_index = max(
        0,
        center_index - 1
    )

    end_index = min(
        len(segments) - 1,
        center_index + 1
    )

    selected = segments[
        start_index:end_index + 1
    ]

    start = selected[0]["start"]
    end = selected[-1]["end"]

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
        "start": round(start, 3),
        "end": round(end, 3),
        "duration": round(
            end - start,
            3
        ),
        "score": score,
        "nepali": text.strip(),
    }


def overlap(
    first: dict,
    second: dict
) -> bool:

    return (
        first["start"] < second["end"]
        and first["end"] > second["start"]
    )


def select_best_candidates(
    scored: list
) -> list:

    candidates = []

    for index, segment in enumerate(
        scored
    ):

        if segment["score"] <= 0:
            continue

        candidate = build_clip(
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

    selected = []

    for candidate in candidates:

        if any(
            overlap(
                candidate,
                existing
            )
            for existing in selected
        ):
            continue

        selected.append(
            candidate
        )

    return selected


def analyze_transcript(
    input_path: str,
    output_path: str
):

    input_file = Path(
        input_path
    )

    output_file = Path(
        output_path
    )

    if not input_file.exists():
        raise FileNotFoundError(
            f"Transcript not found: {input_file}"
        )

    with open(
        input_file,
        "r",
        encoding="utf-8"
    ) as file:

        transcript = json.load(file)

    raw_segments = transcript.get(
        "segments",
        []
    )

    if not raw_segments:
        raise RuntimeError(
            "No transcript segments found."
        )

    scored = []

    for segment in raw_segments:

        item = score_segment(
            segment
        )

        if item["nepali"]:
            scored.append(item)

    if not scored:
        raise RuntimeError(
            "No usable transcript segments found."
        )

    candidates = select_best_candidates(
        scored
    )

    if not candidates:
        raise RuntimeError(
            "No important moments found."
        )

    # ------------------------------------------------
    # LONG VIDEO
    # ------------------------------------------------
    #
    # Highest-scoring important Parliament moment
    # becomes the main/long-video topic.
    #

    long_video = candidates[0].copy()

    long_video["type"] = "long"
    long_video["rank"] = 1

    # ------------------------------------------------
    # SHORT / REEL
    # ------------------------------------------------
    #
    # IMPORTANT:
    # Short cannot overlap with the long video.
    #
    # We deliberately select a different moment.
    #

    short_video = None

    for candidate in candidates[1:]:

        if not overlap(
            candidate,
            long_video
        ):

            short_video = candidate.copy()
            break

    # If there is no second independent moment,
    # do NOT reuse the long-video clip.
    if short_video:

        short_video["type"] = "short"
        short_video["rank"] = 1

    # ------------------------------------------------
    # Additional candidates
    # ------------------------------------------------

    alternative_candidates = []

    for candidate in candidates:

        if overlap(
            candidate,
            long_video
        ):
            continue

        if short_video and overlap(
            candidate,
            short_video
        ):
            continue

        alternative_candidates.append(
            candidate
        )

        if len(
            alternative_candidates
        ) >= 5:

            break

    # ------------------------------------------------
    # FINAL RESULT
    # ------------------------------------------------

    result = {
        "video": transcript.get(
            "video"
        ),

        "model": (
            "parliament-story-selector-v3"
        ),

        "selection_rules": {
            "long_video": (
                "Highest scoring important "
                "Parliament moment."
            ),
            "short_video": (
                "Separate important moment "
                "that does not overlap with "
                "the long video."
            ),
            "avoid_duplicate_story": True
        },

        "long_video": long_video,

        "short_video": short_video,

        "alternatives": (
            alternative_candidates
        ),

        "candidate_count": len(
            candidates
        )
    }

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2
        )

    # ------------------------------------------------
    # PRINT RESULTS
    # ------------------------------------------------

    print("")
    print(
        "===================================="
    )
    print(
        "PARLIAMENT STORY ANALYSIS"
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
        f"Score: {long_video['score']}"
    )

    print(
        f"Time: "
        f"{long_video['start']}s - "
        f"{long_video['end']}s"
    )

    print(
        long_video["nepali"][:700]
    )

    print("")

    if short_video:

        print(
            "SHORT / REEL"
        )

        print(
            "------------------------------------"
        )

        print(
            f"Score: {short_video['score']}"
        )

        print(
            f"Time: "
            f"{short_video['start']}s - "
            f"{short_video['end']}s"
        )

        print(
            short_video["nepali"][:700]
        )

    else:

        print(
            "SHORT / REEL"
        )

        print(
            "------------------------------------"
        )

        print(
            "No separate story found."
        )

        print(
            "System will NOT reuse the "
            "long-video moment."
        )

    print("")
    print(
        f"Analysis saved to: {output_file}"
    )


if __name__ == "__main__":

    if len(sys.argv) != 3:

        print("Usage:")
        print(
            "python analyze.py "
            "<input_json> "
            "<output_json>"
        )

        sys.exit(1)

    analyze_transcript(
        sys.argv[1],
        sys.argv[2]
    )
