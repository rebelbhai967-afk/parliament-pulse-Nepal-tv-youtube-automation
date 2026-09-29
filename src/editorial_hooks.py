import re

QUESTION_WORDS = ("किन", "कसरी", "कहिले", "कति", "के", "कसको", "कहाँ")
STRONG_WORDS = ("सरकार", "मन्त्रालय", "निर्णय", "जवाफ", "प्रश्न", "विधेयक", "बजेट", "रोजगारी", "शिक्षा", "स्वास्थ्य", "महँगी", "भ्रष्टाचार", "अनियमितता", "विकास", "सुरक्षा", "सीमा", "प्रतिवेदन", "कानुन", "संशोधन")

def clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()

def sentence_candidates(text):
    text = clean(text)
    parts = re.split(r"(?<=[।!?])\s+", text)
    parts = [clean(p) for p in parts if len(clean(p)) >= 24]
    if parts:
        return parts
    clauses = re.split(r"(?<=[,;:])\s+", text)
    return [clean(x) for x in clauses if len(clean(x)) >= 24]

def choose_hook(text):
    candidates = sentence_candidates(text)
    if not candidates:
        return {"text": clean(text)[:180], "strategy": "strongest_available", "score": 0}
    best = None
    for sentence in candidates[:10]:
        score = 0
        if "?" in sentence or any(w in sentence for w in QUESTION_WORDS):
            score += 4
        score += 2 * sum(1 for w in STRONG_WORDS if w in sentence)
        if 45 <= len(sentence) <= 150:
            score += 4
        if len(sentence) > 190:
            score -= 2
        if sentence.startswith(("त्यसपछि", "त्यसैगरी", "धन्यवाद", "माननीय", "सभामुखज्यू")):
            score -= 3
        candidate = (score, sentence)
        if best is None or candidate[0] > best[0]:
            best = candidate
    return {
        "text": best[1][:180],
        "strategy": ("question_hook" if "?" in best[1] or any(w in best[1] for w in QUESTION_WORDS) else "public_issue_hook" if any(w in best[1] for w in STRONG_WORDS) else "strong_quote_hook"),
        "score": best[0],
    }

def enrich_piece(piece):
    piece = dict(piece)
    hook = choose_hook(piece.get("text", ""))
    start = float(piece.get("start", 0))
    end = float(piece.get("end", start))
    hook_duration = min(8.0, max(4.0, end - start - 2.0))
    piece["hook"] = hook
    piece["hook_start"] = round(start, 3)
    piece["hook_end"] = round(start + hook_duration, 3)
    piece["main_start"] = round(start + hook_duration, 3)
    piece["main_end"] = round(end, 3)
    return piece
