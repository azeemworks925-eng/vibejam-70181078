# AskSE

Help-desk chatbot for a university Software Engineering department. Students ask questions in English or Roman Urdu, and AskSE answers only from the department FAQ.

## Team

| | |
|---|---|
| Entry ID | 70181078 |
| Team name | Muhammad Azeem (Solo) |
| Members | Muhammad Azeem |
| Repo | https://github.com/azeemworks925-eng/vibejam-70181078 |
| LLM API & model | Groq API (openai/gpt-oss-120b, fallback: qwen/qwen3.8-27b) |
| AI tools used | Claude Code (Opus 5.5), Claude |

## Documentation

- **[AskSE_Project_Guide.docx](AskSE_Project_Guide.docx):** project guide for judges: how to run, the two modes and the API key, how it works, must-have coverage, and a demo script with test questions and expected results.
- **[PROMPTS.md](PROMPTS.md):** vibe log of every prompt with its time, bug fixes, the app's AI prompt and what the AI got wrong.

> **No API key needed to try it.** The key is kept out of the repository for security, so a fresh download runs in **demo mode** (offline FAQ matching). Add your own Groq key in `.env` to use **AI mode**.

## How to run (Windows lab PC)

Needs Python 3.10+. The page loads Bootstrap from a CDN, so an internet connection is recommended.

```powershell
cd vibejam-70181078
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Then open **http://127.0.0.1:8000** in the browser.

On first run, `askse.db` is created with the 8 starter FAQs. Admin PIN: `2026`.

### Two modes

| Mode | When | Answers come from |
|---|---|---|
| **Demo mode** | No `.env` file, or `LLM_API_KEY` empty / still the placeholder | Offline FAQ matching in `demo.py` (keywords + Roman Urdu synonyms). No AI and no API key needed. A blue banner on the Chat page says so. |
| **AI mode** | `LLM_API_KEY` is set in `.env` | Groq AI (`openai/gpt-oss-120b`, fallback `qwen/qwen3.8-27b`) |

To switch on AI mode (no restart needed, `.env` is re-read on every question):

```powershell
copy .env.example .env
notepad .env          # set LLM_API_KEY=<your Groq API key, gsk_...>
```

Any key that is set is used for AI mode: a wrong key (e.g. `INVALID-KEY-123`) shows "AI service unavailable. Check your connection or API key and try again." The About page shows the current mode.

## How it works

- **Backend:** Python FastAPI (`main.py`), SQLite database `askse.db` for FAQs.
- **Frontend:** plain HTML/JS + Bootstrap 5 (`static/`), served by FastAPI.
- **LLM:** Groq chat completions API (OpenAI-compatible), model `openai/gpt-oss-120b` with low reasoning effort and JSON mode (`response_format: json_object`). If a call times out, is rate-limited (429) or the server is overloaded (5xx), it retries once with `qwen/qwen3.8-27b`; both attempts together stay under 30 seconds. The single API key `LLM_API_KEY` is read from `.env` on every request (never sent to the browser), so changing it takes effect without a restart.
- **System prompt:** `prompt.py`. Every question is sent with *all* FAQs; the model must reply `{"found": true/false, "answer": "...", "faq_ids": [...]}`.
- **Checks in code:** invalid JSON, `found=true` with no IDs, or any unknown FAQ ID → treated as not found, and the app shows its own fixed not-found message.
- **Demo mode (`demo.py`):** without a key, questions are matched offline: lowercase, strip punctuation, drop stop words, map Roman Urdu / spelling variants (mids → midterm, bimar → ill, kab khulti → open), then score each FAQ's question + answer + category. Low score, or a question mostly about words no FAQ mentions → the same not-found message. Prompt-injection phrases → not found. Roman Urdu questions get hand-written Roman Urdu answers for the 8 starter FAQs. `/api/status` tells the page which mode is active (never the key).
- **Chat history:** saved in the browser's localStorage (survives closing the browser). "Clear chat" never touches FAQs.

## Project files

```
main.py           FastAPI app, database, Groq call, validation
prompt.py         LLM system prompt + user message builder + shared Roman Urdu word list
demo.py           demo mode: offline FAQ matcher used when there is no API key
static/           index.html, app.js, style.css, logo.svg
requirements.txt
.env.example      copy to .env and add your key
PROMPTS.md        prompt log
AskSE_Project_Guide.docx   project guide and demo script
```
