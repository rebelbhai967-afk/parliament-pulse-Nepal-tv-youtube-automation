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
    # The actual cold-open clip begins at the start of the selected story piece.
    # Keep the hook text aligned with that audio rather than quoting a later sentence.
    first = candidates[0]
    score = 0
    if "?" in first or any(w in first for w in QUESTION_WORDS):
        score += 4
    score += 2 * sum(1 for w in STRONG_WORDS if w in first)
    if 45 <= len(first) <= 150:
        score += 4
    return {
        "text": first[:180],
        "strategy": ("question_hook" if "?" in first or any(w in first for w in QUESTION_WORDS) else "public_issue_hook" if any(w in first for w in STRONG_WORDS) else "strong_quote_hook"),
        "score": score,
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
