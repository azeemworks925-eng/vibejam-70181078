"""
AskSE - help-desk chatbot for the Software Engineering department.
Backend: FastAPI + SQLite + Groq chat completions API (OpenAI-compatible).

Run:  python main.py      (then open http://127.0.0.1:8000)
"""

import json
import os
import re
import sqlite3
import time
from pathlib import Path

import httpx
import uvicorn
from dotenv import dotenv_values
from fastapi import FastAPI, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from prompt import SYSTEM_PROMPT, build_user_message

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "askse.db"
ENV_PATH = BASE_DIR / ".env"
STATIC_DIR = BASE_DIR / "static"

ADMIN_PIN = "2026"
# LLM provider: Groq (OpenAI-compatible chat completions API, JSON mode).
# Primary model + fallback. If the first call times out / is rate-limited / overloaded
# (429, 5xx), we retry ONCE with the other model. Both calls together stay within 30 s.
# Extra settings per model keep "thinking" to a minimum so answers come back fast.
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = {
    "openai/gpt-oss-120b": {"reasoning_effort": "low"},   # primary
    "qwen/qwen3.8-27b": {"reasoning_effort": "none"},     # fallback
}
AI_TIMEOUT_SECONDS = 30          # total time budget for one chat message
FIRST_TRY_TIMEOUT = 18           # max seconds for the first attempt, leaving time for the retry
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

CATEGORIES = ["Labs", "Academics", "Library", "Exams", "Fees", "Projects", "Transport", "Help"]

STARTER_FAQS = [
    ("FAQ-01", "Labs", "When is CS-LAB-102A open, and can I eat there?",
     "CS-LAB-102A is open from 08:00 AM to 06:00 PM, Monday to Friday. Food and drinks are not allowed inside the lab."),
    ("FAQ-02", "Academics", "What is the attendance requirement?",
     "Students need at least 80% attendance in each course. A student below 80% cannot sit the final exam of that course."),
    ("FAQ-03", "Library", "What are the library timings?",
     "The library is open from 08:30 AM to 08:00 PM, Monday to Thursday, and from 08:30 AM to 12:30 PM on Friday. It is closed on weekends."),
    ("FAQ-04", "Exams", "What if I miss a midterm because I was ill?",
     "Apply for a retake to the Course Coordinator within 3 working days of the exam, with a medical certificate."),
    ("FAQ-05", "Fees", "When is the Spring 2027 fee due?",
     "Download the fee challan from the student portal. The last date to pay without a fine is 15-Jan-2027."),
    ("FAQ-06", "Projects", "How do I submit my FYP proposal?",
     "Submit the Final Year Project proposal on SLATE by 30-Nov-2026. Each FYP group has 2 or 3 members."),
    ("FAQ-07", "Transport", "When do the university buses leave?",
     "University buses leave the campus at 01:30 PM and 04:30 PM, Monday to Friday. Bus cards are issued by the Transport Office in Block A."),
    ("FAQ-08", "Help", "Who do I contact for anything else?",
     "Email helpdesk@se.example.edu or visit Room 210, 09:00 AM to 04:00 PM, Monday to Friday."),
]


# ---------------------------------------------------------------- database

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS faqs (
                   num      INTEGER PRIMARY KEY,   -- 1, 2, 3 ... (used for ordering / next ID)
                   id       TEXT UNIQUE NOT NULL,  -- FAQ-01, FAQ-02 ...
                   category TEXT NOT NULL,
                   question TEXT NOT NULL,
                   answer   TEXT NOT NULL
               )"""
        )
        count = conn.execute("SELECT COUNT(*) FROM faqs").fetchone()[0]
        if count == 0:
            insert_starter_faqs(conn)


def insert_starter_faqs(conn):
    for faq_id, category, question, answer in STARTER_FAQS:
        num = int(faq_id.split("-")[1])
        conn.execute(
            "INSERT INTO faqs (num, id, category, question, answer) VALUES (?, ?, ?, ?, ?)",
            (num, faq_id, category, question, answer),
        )


def load_faqs():
    with get_db() as conn:
        rows = conn.execute("SELECT id, category, question, answer FROM faqs ORDER BY num").fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- LLM

def get_api_key():
    """Re-read .env on every request, so a changed key works without restart."""
    values = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    return (values.get("LLM_API_KEY") or os.environ.get("LLM_API_KEY") or "").strip()


class AIServiceError(Exception):
    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def ask_ai(api_key, user_message):
    """Try the primary model; on timeout/overload retry once with the fallback. Max 30 s total."""
    if not api_key:
        raise AIServiceError("No API key")
    deadline = time.monotonic() + AI_TIMEOUT_SECONDS
    primary, fallback = list(GROQ_MODELS)
    try:
        return call_groq(api_key, primary, user_message, FIRST_TRY_TIMEOUT)
    except AIServiceError as e:
        remaining = deadline - time.monotonic()
        if not e.retryable or remaining < 3:
            raise
        print(f"{primary} failed ({e}); retrying with {fallback}")
        return call_groq(api_key, fallback, user_message, remaining)


def call_groq(api_key, model, user_message, timeout):
    """Call one Groq model in JSON mode. Returns the raw text reply. Raises AIServiceError on failure."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        **GROQ_MODELS[model],
    }
    try:
        resp = httpx.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=timeout,
        )
    except httpx.ConnectError as e:  # no internet / DNS failure -> retrying won't help
        raise AIServiceError(f"{model}: connection error {type(e).__name__}")
    except httpx.HTTPError as e:  # timeout, dropped connection ...
        raise AIServiceError(f"{model}: network error {type(e).__name__}", retryable=True)
    if resp.status_code != 200:  # invalid key (401), rate limit (429), overloaded (5xx) ...
        try:
            error = resp.json()["error"]
        except (ValueError, KeyError, TypeError):
            error = {}
        if error.get("code") == "json_validate_failed":
            return ""  # the model produced invalid JSON -> treated as "not found"
        detail = str(error.get("message", ""))[:200]
        raise AIServiceError(f"{model}: HTTP {resp.status_code} {detail}",
                             retryable=resp.status_code in RETRY_STATUS_CODES)
    try:
        return resp.json()["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, ValueError, TypeError):
        return ""  # no usable text -> treated as "not found"


def validate_reply(raw_text, faqs, api_key):
    """Check the model's JSON in code. Returns (answer, ids) if valid and found, else None (= not found)."""
    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("found") is not True:
        return None

    answer = data.get("answer")
    ids = data.get("faq_ids")
    if not isinstance(answer, str) or not answer.strip():
        return None
    if not isinstance(ids, list) or len(ids) == 0:
        return None

    known_ids = {f["id"] for f in faqs}
    clean_ids = []
    for faq_id in ids:
        if not isinstance(faq_id, str) or faq_id.strip() not in known_ids:
            return None  # unknown / made-up ID -> not found
        if faq_id.strip() not in clean_ids:
            clean_ids.append(faq_id.strip())

    # Extra safety: never show the API key, even if the model somehow echoes it.
    if api_key and api_key in answer:
        return None

    # Remove any "[FAQ-xx]" the model may have put inside the answer text (we add our own).
    answer = re.sub(r"\s*\[\s*FAQ-\d+(\s*,\s*FAQ-\d+)*\s*\]", "", answer).strip()
    return answer, clean_ids


# ---------------------------------------------------------------- API

app = FastAPI(title="AskSE")
init_db()


class ChatRequest(BaseModel):
    message: str = ""


class FaqRequest(BaseModel):
    category: str = ""
    question: str = ""
    answer: str = ""


class PinRequest(BaseModel):
    pin: str = ""


@app.post("/api/chat")
def chat(req: ChatRequest):
    message = req.message or ""
    if not message.strip() or len(message) > 300:
        return JSONResponse({"status": "invalid"}, status_code=400)

    faqs = load_faqs()  # read fresh every time -> new FAQs are used immediately
    api_key = get_api_key()
    try:
        raw = ask_ai(api_key, build_user_message(faqs, message.strip()))
    except AIServiceError as e:
        print("AI service error:", e)  # logged on server only, never the key
        return {"status": "error"}

    result = validate_reply(raw, faqs, api_key)
    if result is None:
        return {"status": "not_found"}
    answer, ids = result
    return {"status": "found", "answer": answer, "faq_ids": ids}


@app.get("/api/faqs")
def list_faqs():
    return {"faqs": load_faqs(), "categories": CATEGORIES}


@app.post("/api/admin/login")
def admin_login(req: PinRequest):
    if req.pin != ADMIN_PIN:
        return JSONResponse({"ok": False, "error": "Incorrect PIN"}, status_code=401)
    return {"ok": True}


def validate_faq(req: FaqRequest):
    errors = {}
    question = req.question.strip()
    answer = req.answer.strip()
    if req.category not in CATEGORIES:
        errors["category"] = "Please choose a category."
    if not 10 <= len(question) <= 150:
        errors["question"] = "Question must be 10 to 150 characters."
    if not 10 <= len(answer) <= 400:
        errors["answer"] = "Answer must be 10 to 400 characters."
    return errors, question, answer


@app.post("/api/faqs")
def add_faq(req: FaqRequest, x_admin_pin: str = Header(default="")):
    if x_admin_pin != ADMIN_PIN:
        return JSONResponse({"ok": False, "error": "Incorrect PIN"}, status_code=401)
    errors, question, answer = validate_faq(req)
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=400)

    with get_db() as conn:
        next_num = conn.execute("SELECT COALESCE(MAX(num), 0) + 1 FROM faqs").fetchone()[0]
        new_id = f"FAQ-{next_num:02d}"
        conn.execute(
            "INSERT INTO faqs (num, id, category, question, answer) VALUES (?, ?, ?, ?, ?)",
            (next_num, new_id, req.category, question, answer),
        )
    return {"ok": True, "id": new_id}


@app.post("/api/faqs/reset")
def reset_faqs(x_admin_pin: str = Header(default="")):
    if x_admin_pin != ADMIN_PIN:
        return JSONResponse({"ok": False, "error": "Incorrect PIN"}, status_code=401)
    with get_db() as conn:
        conn.execute("DELETE FROM faqs")
        insert_starter_faqs(conn)
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    print("AskSE running at http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
