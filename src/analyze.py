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

    question_words = [
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

    for word in question_words:
        if word in text:
            score += 2

    if "?" in text:
        score += 3

    return score


def statement_score(text: str) -> int:
    score = 0

    strong_phrases = [
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

    for phrase in strong_phrases:
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
        "start": float(segment.get("start", 0)),
        "end": float(segment.get("end", 0)),
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

    # Keep clips reasonably short.
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


def analyze_transcript(
    input_path: str,
    output_path: str,
    top_n: int = 2
):
    input_file = Path(input_path)
    output_file = Path(output_path)

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
        item = score_segment(segment)

        if item["nepali"]:
            scored.append(item)

    if not scored:
        raise RuntimeError(
            "No usable transcript segments found."
        )

    candidates = []

    for index, segment in enumerate(scored):

        if segment["score"] <= 0:
            continue

        candidate = build_clip(
            scored,
            index
        )

        candidates.append(candidate)

    # Sort highest score first.
    candidates.sort(
        key=lambda item: (
            item["score"],
            item["duration"]
        ),
        reverse=True
    )

    # Remove overlapping candidates.
    selected = []

    for candidate in candidates:

        overlaps = False

        for existing in selected:

            if (
                candidate["start"]
                < existing["end"]
                and candidate["end"]
                > existing["start"]
            ):
                overlaps = True
                break

        if overlaps:
            continue

        selected.append(candidate)

        if len(selected) >= top_n:
            break

    # If fewer than top_n candidates exist,
    # keep the available candidates.
    for rank, candidate in enumerate(
        selected,
        start=1
    ):
        candidate["rank"] = rank

    result = {
        "video": transcript.get("video"),
        "model": "keyword-scoring-v2",
        "candidate_count": len(selected),
        "candidates": selected,
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

    print(
        f"Analysis saved to: {output_file}"
    )

    print(
        f"Found {len(selected)} clip candidates"
    )

    for candidate in selected:

        print("")
        print(
            f"Rank {candidate['rank']} "
            f"| Score {candidate['score']}"
        )

        print(
            f"{candidate['start']}s - "
            f"{candidate['end']}s "
            f"({candidate['duration']}s)"
        )

        print(
            candidate["nepali"][:500]
        )


if __name__ == "__main__":

    if len(sys.argv) not in [3, 4]:
        print(
            "Usage:"
        )
        print(
            "python analyze.py "
            "<input_json> "
            "<output_json> "
            "[top_n]"
        )
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    top_n = 2

    if len(sys.argv) == 4:
        top_n = int(sys.argv[3])

    analyze_transcript(
        input_path,
        output_path,
        top_n
    )
