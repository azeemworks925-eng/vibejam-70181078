# AskSE

Help-desk chatbot for a university Software Engineering department. Students ask questions in English or Roman Urdu, and AskSE answers only from the department FAQ.

## Team

| | |
|---|---|
| Entry ID | 70181078 |
| Team name | TEAMNAME |
| Members | Muhammad Azeem, MEMBER2 |
| Repo | https://github.com/azeemworks925-eng/vibejam-70181078 |
| LLM API & model | Groq API (openai/gpt-oss-120b, fallback: qwen/qwen3.8-27b) |
| AI tools used | Claude Code (Opus 5.5), Claude |

## How to run (Windows lab PC)

Needs Python 3.10+ and an internet connection.

```powershell
cd vibejam-70181078
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
notepad .env          # set LLM_API_KEY=<your Groq API key, gsk_...>
python main.py
```

Then open **http://127.0.0.1:8000** in the browser.

On first run, `askse.db` is created with the 8 starter FAQs. Admin PIN: `2026`.

## How it works

- **Backend:** Python FastAPI (`main.py`), SQLite database `askse.db` for FAQs.
- **Frontend:** plain HTML/JS + Bootstrap 5 (`static/`), served by FastAPI.
- **LLM:** Groq chat completions API (OpenAI-compatible), model `openai/gpt-oss-120b` with low reasoning effort and JSON mode (`response_format: json_object`). If a call times out, is rate-limited (429) or the server is overloaded (5xx), it retries once with `qwen/qwen3.8-27b`; both attempts together stay under 30 seconds. The single API key `LLM_API_KEY` is read from `.env` on every request (never sent to the browser), so changing it takes effect without a restart.
- **System prompt:** `prompt.py`. Every question is sent with *all* FAQs; the model must reply `{"found": true/false, "answer": "...", "faq_ids": [...]}`.
- **Checks in code:** invalid JSON, `found=true` with no IDs, or any unknown FAQ ID → treated as not found, and the app shows its own fixed not-found message.
- **Chat history:** saved in the browser's localStorage (survives closing the browser). "Clear chat" never touches FAQs.

## Project files

```
main.py           FastAPI app, database, Groq call, validation
prompt.py         LLM system prompt + user message builder
static/           index.html, app.js, style.css, logo.svg
requirements.txt
.env.example      copy to .env and add your key
PROMPTS.md        prompt log
```
