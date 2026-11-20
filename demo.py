"""
AskSE - DEMO MODE: offline FAQ matcher (no AI, no API key needed).

Used automatically when LLM_API_KEY is missing, empty, or still the
placeholder from .env.example. It answers ONLY from the FAQ list, like the AI:

  1. Prompt-injection phrases (ignore rules, system prompt, api key ...) -> not found.
  2. Normalise words: lowercase, strip punctuation, drop stop words,
     map Roman Urdu / spelling variants to one word (mids -> midterm, bimar -> ill).
  3. Score every FAQ (question + answer + category). A word scores more if it
     appears in the FAQ's question/category, and less if it appears in many FAQs.
  4. Best score below MIN_SCORE -> not found. Also not found if the question has as many
     words that no FAQ mentions ("wifi") as matched words - it is about another subject.
     Otherwise return that FAQ.
  5. Roman Urdu question -> hand-written Roman Urdu answer for the 8 starter FAQs.

Works for admin-added FAQs too, because the FAQ list is read fresh on every question.
"""

import re

from prompt import ROMAN_URDU_WORDS

MIN_SCORE = 1.5   # one word matching an FAQ question (2.0) passes; one answer-only word (<= 1.0) does not

# --- prompt injection -> always "not found" -----------------------------------
INJECTION_PHRASES = [
    "ignore", "disregard", "forget your", "forget all", "your rules", "your instructions",
    "previous instructions", "system prompt", "your prompt", "the prompt", "api key", "apikey",
    "secret key", "jailbreak", "developer mode", "dan mode", "act as", "pretend", "bypass",
    "override", "reveal", "json format", "rules chor", "rules todo", "prompt batao", "prompt dikhao",
]

# --- words that carry no subject ---------------------------------------------
STOP_WORDS = set("""
a an the is are was were be been am i me my mine you your we our us it its this that these those
what when where which who whom why how do does did can could should would will shall may might must
to of in on at by for from with about as and or but if then so not no yes there here any some all
each every please tell know want need get got have has had up out off over under again more most
other such only own same than too very just also kindly hi hello thanks thank sir madam miss mam
""".split()) | set(ROMAN_URDU_WORDS) | set("""
hota hoti hote hum main mujhe mujhay aap ap koi kuch bhi aur ya wala wali walay kitna kitne kaun kon
kis kisi honi hona raha rahi rahe krna krni kar kare karen karein sakta sakti sakte kyun kyu batao
bata bataen batayen plz pls jee ji yar yaar bhai h hy hn to lia liya baje bajay
""".split())

# Domain words that appear everywhere at a university help desk: they never decide the topic
# ("When is the university open?" must NOT match "University buses ...").
GENERIC_WORDS = {"university", "campus", "department", "student", "course", "se", "software", "engineering"}

# Roman Urdu / spelling variants -> one canonical word (applied to questions AND FAQs)
SYNONYMS = {
    "uni": "university", "varsity": "university",
    "mids": "midterm", "mid": "midterm", "midterms": "midterm", "midterm": "midterm",
    "bimar": "ill", "beemar": "ill", "bimari": "ill", "sick": "ill", "illness": "ill",
    "fees": "fee", "dues": "fee",
    "buses": "bus", "gari": "bus", "gaari": "bus", "gadi": "bus", "van": "bus", "point": "bus",
    "kitab": "library", "kitabain": "library", "kutubkhana": "library",
    "haazri": "attendance", "hazri": "attendance", "hazari": "attendance", "attendence": "attendance",
    "imtihan": "exam", "imtehan": "exam", "paper": "exam", "papers": "exam", "exams": "exam",
    "khana": "food", "khaana": "food", "eat": "food", "eating": "food",
    "khulti": "open", "khuli": "open", "khula": "open", "khulta": "open", "khulay": "open",
    "khulegi": "open", "opens": "open", "opening": "open", "timing": "open", "timings": "open", "time": "open",
    "chalti": "leave", "chalta": "leave", "chalte": "leave", "chalegi": "leave", "nikalti": "leave", "nikalta": "leave",
    "jama": "pay", "jamaa": "pay", "bharni": "pay", "bharna": "pay", "deni": "pay",
    "labs": "lab", "proposals": "proposal",
}

# Hand-written Roman Urdu answers for the 8 starter FAQs (times, dates, names, emails kept exact)
ROMAN_URDU_ANSWERS = {
    "FAQ-01": "CS-LAB-102A Monday se Friday tak 08:00 AM se 06:00 PM tak khula rehta hai. Lab ke andar khana aur drinks allowed nahi hain.",
    "FAQ-02": "Har course mein kam se kam 80% attendance zaroori hai. 80% se kam attendance wala student us course ka final exam nahi de sakta.",
    "FAQ-03": "Library Monday se Thursday 08:30 AM se 08:00 PM tak, aur Friday ko 08:30 AM se 12:30 PM tak khuli hoti hai. Weekends par library band hoti hai.",
    "FAQ-04": "Exam ke 3 working days ke andar Course Coordinator ko medical certificate ke saath retake ki application dein.",
    "FAQ-05": "Fee challan student portal se download karein. Bina fine ke fee jama karne ki aakhri tareekh 15-Jan-2027 hai.",
    "FAQ-06": "Final Year Project proposal 30-Nov-2026 tak SLATE par submit karein. Har FYP group mein 2 ya 3 members hote hain.",
    "FAQ-07": "University buses Monday se Friday tak campus se 01:30 PM aur 04:30 PM par nikalti hain. Bus cards Block A mein Transport Office se milte hain.",
    "FAQ-08": "Kisi aur cheez ke liye helpdesk@se.example.edu par email karein ya Room 210 aayein, Monday se Friday 09:00 AM se 04:00 PM tak.",
}


def stem(word):
    """Very small English stemmer so 'timings'/'timing', 'drinks'/'drink' match."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("es") and word[-3] in "sxz":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def raw_words(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def keywords(text):
    """Subject words of a text: no stop words, no pure numbers, synonyms merged."""
    result = set()
    for w in raw_words(text):
        if w in STOP_WORDS or w.isdigit():
            continue
        w = SYNONYMS.get(w, w)
        w = SYNONYMS.get(stem(w), stem(w))
        if w not in GENERIC_WORDS and w not in STOP_WORDS:
            result.add(w)
    return result


def is_injection(question):
    text = " " + " ".join(raw_words(question)) + " "
    return any(" " + phrase + " " in text for phrase in INJECTION_PHRASES)


def is_roman_urdu(question):
    """Roman Urdu if it has 1 clear Urdu word, or 2+ words that could also be English ('me', 'ha')."""
    found = [w for w in raw_words(question) if w in ROMAN_URDU_WORDS]
    ambiguous = {"me", "ha", "ab"}
    return any(w not in ambiguous for w in found) or len(found) >= 2


def answer(question, faqs):
    """Return (answer_text, [faq_id]) or None (= not found)."""
    if is_injection(question):
        return None
    q_words = keywords(question)
    if not q_words or not faqs:
        return None

    faq_all = {f["id"]: keywords(f["question"] + " " + f["answer"] + " " + f["category"]) for f in faqs}
    faq_main = {f["id"]: keywords(f["question"] + " " + f["category"]) for f in faqs}

    best_id, best_score = None, 0.0
    for f in faqs:  # FAQs come in ID order, so ties go to the lower ID
        score = 0.0
        for w in q_words:
            if w in faq_all[f["id"]]:
                df = sum(1 for words in faq_all.values() if w in words)  # how many FAQs use this word
                score += (2.0 if w in faq_main[f["id"]] else 1.0) / df
        if score > best_score:
            best_id, best_score = f["id"], score

    if best_score < MIN_SCORE:
        return None
    # Wrong-subject guard: words that NO FAQ mentions (e.g. "wifi" in "Is there wifi in the lab?")
    # mean the question is about something else. If they are as many as the matched words -> not found.
    unknown = [w for w in q_words if not any(w in words for words in faq_all.values())]
    matched = [w for w in q_words if w in faq_all[best_id]]
    if unknown and len(unknown) >= len(matched):
        return None
    faq = next(f for f in faqs if f["id"] == best_id)
    if is_roman_urdu(question) and best_id in ROMAN_URDU_ANSWERS:
        return ROMAN_URDU_ANSWERS[best_id], [best_id]
    return faq["answer"], [best_id]
