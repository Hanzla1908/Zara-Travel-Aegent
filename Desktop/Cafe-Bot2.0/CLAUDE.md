# CLAUDE.md — CafeBot 2.0

## Project Purpose

CafeBot is a beginner-friendly AI chatbot for a fictional cafe.
Customers can ask about the menu, get recommendations, and place orders
through a simple browser chat UI backed by a lightweight Python server.

---

## Architecture

```
frontend/index.html   →  POST /chat  →  backend/app.py  →  Anthropic API
                                              ↑
                                    prompts/system_prompt.txt
                                    data/menu.json
```

| Layer    | File                        | Role                          |
|----------|-----------------------------|-------------------------------|
| Frontend | `frontend/index.html`       | Single-page chat UI           |
| Backend  | `backend/app.py`            | Flask server, calls Claude    |
| Prompts  | `prompts/system_prompt.txt` | Bot persona and instructions  |
| Data     | `data/menu.json`            | Menu items and prices         |
| Config   | `.env`                      | API key and runtime settings  |

---

## Coding Rules

- Use plain Python (Flask) and vanilla JS — no frameworks unless the user asks.
- Keep functions short; one function, one job.
- Name variables and functions clearly; avoid single-letter names outside loops.
- No unused imports, dead code, or commented-out blocks left behind.
- Backend returns JSON; frontend handles display only.

---

## Security Rules

- Never commit `.env`; it is in `.gitignore`.
- Never log or print the API key, even partially.
- Sanitize user input before including it in any prompt or file operation.
- Do not expose internal error details to the frontend — return a generic message.
- Keep the API key only in `os.getenv("ANTHROPIC_API_KEY")`; never hard-code it.

---

## Token-Saving Rules

- Default model: `claude-haiku-4-5` (cheapest capable model). Only upgrade if the user asks.
- Set `max_tokens` to 512 or less unless the task clearly needs more.
- Pass only the last 6 conversation turns in the `messages` list; drop older history.
- Load `system_prompt.txt` once at startup — do not re-read it per request.
- Do not send the full menu in every message; inject it into the system prompt once.

---

## Scope Rule

**Modify only the files needed for the current task.**
If a task touches only `backend/app.py`, do not edit `frontend/index.html` or
`prompts/system_prompt.txt` unless explicitly asked. Make the smallest change
that satisfies the requirement.
