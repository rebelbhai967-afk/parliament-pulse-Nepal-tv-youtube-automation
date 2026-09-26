import json
import re
import sys
from pathlib import Path


# Important parliamentary keywords.
KEYWORDS = {
    "सरकार": 3,
    "मन्त्री": 4,
    "प्रधानमन्त्री": 5,
    "सांसद": 2,
    "सभामुख": 2,
    "अध्यक्ष": 2,
    "कानुन": 4,
    "विधेयक": 4,
    "संशोधन": 4,
    "बजेट": 5,
    "कर": 3,
    "नीति": 3,
    "योजना": 3,
    "भ्रष्टाचार": 5,
    "अनियमितता": 5,
    "जवाफ": 4,
    "प्रश्न": 3,
    "निर्णय": 4,
    "महत्वपूर्ण": 3,
    "जनता": 2,
    "संविधान": 4,
    "शिक्षा": 3,
    "स्वास्थ्य": 3,
    "रोजगारी": 3,
    "महँगी": 4,
    "विकास": 3,
    "सुरक्षा": 3,
    "विदेश": 3,
    "सीमा": 4,
}


def normalize_text(text: str) -> str:
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

    question_marks = text.count("?")

    if question_marks:
        score += 2

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
            score += 1

    return score


def length_score(text: str) -> int:
    word_count = len(text.split())

    if word_count >= 40:
        return 3

    if word_count >= 20:
        return 2

    if word_count >= 10:
        return 1

    return 0


def score_segment(segment: dict) -> dict:
    text = normalize_text(
        segment.get("nepali", "")
    )

    score = 0

    score += keyword_score(text)
    score += question_score(text)
    score += length_score(text)

    return {
        "start": segment.get("start", 0),
        "end": segment.get("end", 0),
        "nepali": text,
        "score": score,
    }


def merge_nearby_segments(
    segments: list,
    max_gap: float = 4.0
) -> list:

    if not segments:
        return []

    merged = []

    current = dict(segments[0])

    for segment in segments[1:]:
        gap = (
            float(segment["start"])
            - float(current["end"])
        )

        if gap <= max_gap:
            current["end"] = segment["end"]

            current["nepali"] = (
                current["nepali"]
                + " "
                + segment["nepali"]
            )

            current["score"] += segment["score"]

        else:
            merged.append(current)
            current = dict(segment)

    merged.append(current)

    return merged


def analyze_transcript(
    input_path: str,
    output_path: str,
    top_n: int = 10
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

    segments = transcript.get(
        "segments",
        []
    )

    if not segments:
        raise RuntimeError(
            "No transcript segments found."
        )

    scored_segments = []

    for segment in segments:
        scored = score_segment(segment)

        if scored["score"] > 0:
            scored_segments.append(scored)

    scored_segments.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    candidates = merge_nearby_segments(
        scored_segments[:50]
    )

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    candidates = candidates[:top_n]

    for index, candidate in enumerate(
        candidates,
        start=1
    ):
        candidate["rank"] = index

    result = {
        "video": transcript.get(
            "video"
        ),
        "model": "keyword-scoring-v1",
        "candidate_count": len(candidates),
        "candidates": candidates,
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
        f"Found {len(candidates)} clip candidates"
    )

    for candidate in candidates:
        print("")
        print(
            f"Rank {candidate['rank']} "
            f"| Score {candidate['score']}"
        )
        print(
            f"{candidate['start']}s - "
            f"{candidate['end']}s"
        )
        print(
            candidate["nepali"][:300]
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

    top_n = 10

    if len(sys.argv) == 4:
        top_n = int(sys.argv[3])

    analyze_transcript(
        input_path,
        output_path,
        top_n
    )
