import re

QUESTION_WORDS = ("किन", "कसरी", "कहिले", "कति", "के", "कसको", "कहाँ")
STRONG_WORDS = ("सरकार", "मन्त्रालय", "निर्णय", "जवाफ", "प्रश्न", "विधेयक", "बजेट", "रोजगारी", "शिक्षा", "स्वास्थ्य", "महँगी", "भ्रष्टाचार", "अनियमितता", "विकास", "सुरक्षा", "सीमा", "प्रतिवेदन", "कानुन", "संशोधन", "जनता", "नागरिक", "अधिकार")
FILLER_PHRASES = ("धन्यवाद सभामुख", "धन्यवाद अध्यक्ष", "मेरो भनाइ यति नै", "समय दिनुभएकोमा धन्यवाद")

def clean(text):
    return re.sub(r"\\s+", " ", str(text or "")).strip()

def sentence_candidates(text):
    text = clean(text)
    parts = re.split(r"(?<=[।!?])\\s+", text)
    parts = [clean(p) for p in parts if len(clean(p)) >= 24]
    if parts:
        return parts
    clauses = re.split(r"(?<=[,;:])\\s+", text)
    return [clean(x) for x in clauses if len(clean(x)) >= 24]

def score_hook(sentence):
    value = clean(sentence)
    low = value.lower()
    score = 0
    if "?" in value or any(w in value for w in QUESTION_WORDS):
        score += 4
    score += 3 * sum(1 for w in STRONG_WORDS if w in value)
    if 45 <= len(value) <= 150:
        score += 4
    if len(value) < 35:
        score -= 3
    if any(p in low for p in FILLER_PHRASES):
        score -= 10
    if len(set(value.split())) < max(3, len(value.split()) * 0.45):
        score -= 4
    return score

def choose_hook(text):
    candidates = sentence_candidates(text)
    if not candidates:
        return {"text": clean(text)[:180], "strategy": "strongest_available", "score": 0}
    # Only rank sentences inside the selected opening transcript window. This
    # keeps hook text aligned with the opening audio; never quote a later line
    # while showing unrelated earlier audio.
    ranked = sorted(enumerate(candidates), key=lambda pair: (score_hook(pair[1]), -pair[0]), reverse=True)
    best = ranked[0][1]
    score = score_hook(best)
    strategy = ("question_hook" if "?" in best or any(w in best for w in QUESTION_WORDS)
                else "public_issue_hook" if any(w in best for w in STRONG_WORDS)
                else "strong_quote_hook")
    return {"text": best[:180], "strategy": strategy, "score": score}

def enrich_piece(piece):
    piece = dict(piece)
    hook = choose_hook(piece.get("hook_text") or piece.get("text", ""))
    start = float(piece.get("start", 0))
    end = float(piece.get("end", start))
    # Keep the hook bounded and the main story continuous. Silence and
    # speaker-change cuts are handled only when the transcript timestamps are
    # available; do not create timing drift by blindly removing audio silence
    # after subtitles have been timestamped.
    hook_duration = min(8.0, max(4.0, end - start - 2.0))
    piece["hook"] = hook
    piece["hook_start"] = round(start, 3)
    piece["hook_end"] = round(start + hook_duration, 3)
    piece["main_start"] = round(start + hook_duration, 3)
    piece["main_end"] = round(end, 3)
    return piece
