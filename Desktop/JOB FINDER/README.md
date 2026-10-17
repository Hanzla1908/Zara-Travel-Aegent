# AI Job Finder Agent

A full-stack AI-powered job-finding application built with FastAPI (Python) and React.

Upload your CV, get deterministic match scores against job listings, run a multi-agent workflow powered by Claude, and set up scheduled job alerts with configurable minimum scores and optional email delivery.

---

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Setup](#setup)
- [Environment variables](#environment-variables)
- [Running the application](#running-the-application)
- [API reference](#api-reference)
- [Tests](#tests)
- [Deployment notes](#deployment-notes)

---

## Features

- **CV upload** — PDF and DOCX; Claude extracts structured skills, experience years, job titles, and location. Falls back to regex extraction when the API key is absent.
- **Deterministic match scoring** — 0–100 score using configurable weights (skills 50 %, experience 25 %, title 15 %, location 10 %); pure Python, no AI guesswork.
- **Multi-agent workflow** — `POST /api/workflow/run` runs a Claude tool-calling loop (SearchAgent → CVAnalysisAgent → MatchingAgent) and falls back to a direct sequential path when no API key is set.
- **Job alerts** — scheduled checks every 5 minutes; configurable frequency (Hourly / Daily / Weekly), minimum match score, per-source filtering, and optional email delivery via SMTP.
- **Deduplication** — each `(alert_id, job_external_id)` pair produces at most one notification, enforced at both the application and database levels.
- **External job sources** — LinkedIn Jobs Partner API and Rozee.pk adapter; both degrade gracefully when credentials are absent.
- **Rate limiting** — in-process sliding-window rate limiter (no extra dependencies).
- **Input validation** — CV magic-byte verification (PDF/DOCX), filename sanitisation, user_id length check.

---

## Architecture

```
JOB FINDER/
├── backend/
│   ├── app/
│   │   ├── adapters/       # LinkedIn + Rozee.pk adapter pattern
│   │   ├── agents/         # SearchAgent, CVAnalysisAgent, MatchingAgent, Coordinator
│   │   ├── api/            # FastAPI routers: jobs, cv, saved, alerts, workflow
│   │   ├── middleware/     # RateLimitMiddleware
│   │   ├── models/         # SQLAlchemy ORM models + database setup
│   │   ├── schemas/        # Pydantic request/response schemas
│   │   ├── services/       # cv_parser, matcher, seeder, alert_checker, scheduler
│   │   ├── config.py       # pydantic-settings; reads .env
│   │   └── main.py         # FastAPI app + lifespan (DB init, seed, scheduler)
│   ├── tests/              # 151 pytest tests (asyncio, in-memory SQLite)
│   └── requirements.txt
├── frontend/               # Vite + React
│   └── src/
│       ├── api/            # axios API modules: jobs, cv, saved, alerts
│       ├── components/     # TopBar, Sidebar, JobCard, CVUpload, SearchFilters, SkillGap, StatCard
│       └── pages/          # Dashboard, Jobs, JobDetail, Saved, Alerts
├── .env.example
└── README.md
```

**Database**: SQLite via `aiosqlite` + SQLAlchemy 2.0 async. Tables are created on startup with `metadata.create_all`; additive column migrations use `ALTER TABLE ADD COLUMN` (idempotent).

**Scoring** is fully deterministic Python — Claude is invoked only for natural-language *explanations*, never for score decisions.

---

## Setup

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11 + |
| Node.js | 18 + |
| pip | any recent |

### 1. Clone and enter the project

```bash
git clone <repo-url>
cd "JOB FINDER"
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
```

### 3. Frontend

```bash
cd ../frontend
npm install
```

### 4. Environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in at minimum `ANTHROPIC_API_KEY`. All other variables have safe defaults or can be left blank to disable the corresponding feature.

---

## Environment variables

All variables are optional except `ANTHROPIC_API_KEY` (required for CV parsing and match explanations; the app runs in fallback mode without it).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | recommended | `""` | Anthropic API key from [console.anthropic.com](https://console.anthropic.com/). App uses regex fallback when absent. |
| `DATABASE_URL` | no | `sqlite+aiosqlite:///./job_finder.db` | SQLAlchemy async database URL. |
| `DEBUG` | no | `false` | Enable debug mode. |
| `LINKEDIN_ACCESS_TOKEN` | no | `""` | LinkedIn Jobs Partner API OAuth token. Requires [partner programme approval](https://developer.linkedin.com/product-catalog/jobs). Leave blank to disable LinkedIn adapter. |
| `ROZEE_API_KEY` | no | `""` | Rozee.pk Partner API key. Contact api@rozee.pk for access. Leave blank to disable. |
| `ROZEE_API_BASE` | no | `https://api.rozee.pk/v1` | Rozee.pk API base URL. |
| `SMTP_HOST` | no | `""` | SMTP server hostname. All five SMTP fields must be set for email delivery. |
| `SMTP_PORT` | no | `587` | SMTP port (STARTTLS). |
| `SMTP_USER` | no | `""` | SMTP username. |
| `SMTP_PASS` | no | `""` | SMTP password. |
| `SMTP_FROM` | no | `""` | From address for alert emails. |

**Security rules:**
- Never commit `.env` to git — it is gitignored by default.
- Real API keys belong only in `.env`, never in `.env.example`.
- Email is only sent when `SMTP_HOST` is set **and** the user sets `email_enabled=true` on their alert.

---

## Running the application

### Backend (FastAPI + uvicorn)

Run from the `backend/` directory:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

The server starts at `http://localhost:8000`. Interactive API docs: `http://localhost:8000/docs`.

On startup, the server:
1. Creates all database tables.
2. Seeds 6 example jobs (idempotent — skips if already present).
3. Starts the background alert scheduler (5-minute poll interval).

### Frontend (Vite + React)

Run from the `frontend/` directory:

```bash
npm run dev
```

The UI starts at `http://localhost:3000` (proxied to the backend).

---

## API reference

All responses use JSON. Error responses follow `{ "detail": "..." }`.

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Returns `{ "status": "ok", "version": "0.1.0" }` |

### Jobs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/jobs/` | List jobs with filters: `keyword`, `location`, `experience[]`, `type`, `source[]`, `sort` (match/date/salary), `page`, `page_size` |
| GET | `/api/jobs/{id}` | Get a single job |
| POST | `/api/jobs/seed` | Re-seed example jobs |
| POST | `/api/jobs/refresh` | Fetch jobs from external adapters and save new listings |

### CV

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/cv/upload` | Upload a PDF or DOCX CV (multipart/form-data `file` field). Returns the extracted profile. |
| GET | `/api/cv/profile` | Get the current user's CV profile |
| DELETE | `/api/cv/profile` | Delete the current user's CV profile |
| GET | `/api/cv/matches` | Score and rank all jobs against the CV. Query params: `explain` (bool), `skills_weight`, `experience_weight`, `title_weight`, `location_weight`, `limit` |

**CV upload security:** The endpoint verifies file magic bytes (not just the declared content-type), enforces a 10 MB size limit, and sanitises the filename before storage.

### Saved Jobs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/saved/` | List saved jobs for a user |
| POST | `/api/saved/{job_id}` | Save a job |
| DELETE | `/api/saved/{job_id}` | Unsave a job |

### Alerts

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/alerts/setup` | Plain-English setup instructions for the alerts feature |
| GET | `/api/alerts/` | List alerts |
| POST | `/api/alerts/` | Create an alert. Body: `name`, `keywords`, `location`, `frequency` (Hourly/Daily/Weekly), `sources[]`, `min_score` (0–100), `email_enabled`, `email_address` |
| PATCH | `/api/alerts/{id}` | Update an alert (all fields optional) |
| DELETE | `/api/alerts/{id}` | Delete an alert |
| GET | `/api/alerts/{id}/results` | List notifications generated by an alert. Query: `unseen_only` (bool) |
| PATCH | `/api/alerts/{id}/results/{nid}/seen` | Mark a notification as seen |
| POST | `/api/alerts/{id}/check` | Trigger an immediate check for this alert |

### Workflow (Multi-agent)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/workflow/run` | Run the multi-agent job-finding workflow. Body: `WorkflowPreferences`. Without `confirmed=true` returns `status="pending_confirmation"` and a plan. With `confirmed=true` runs the full external search + matching. |

`WorkflowPreferences` fields: `keyword`, `location`, `experience[]`, `job_type`, `sources[]`, `limit` (1–100), `explain` (bool), `user_id`, `confirmed` (bool).

---

## Tests

Run from the `backend/` directory:

```bash
python -m pytest tests/ -v
```

151 tests covering:
- Job listing, filtering, sorting, pagination
- CV upload (content-type validation, size limit, profile parsing)
- CV profile retrieval and deletion
- Match scoring weights, normalization, breakdowns
- Adapter infrastructure (LinkedIn, Rozee, registry deduplication)
- Multi-agent workflow: preferences validation, result schema, CV agent, search agent, matching agent, deduplication, coordinator direct path
- Alert CRUD, frequency validation, scheduler timing logic
- Alert checker: `_is_due`, `_deduplicate`, `_score_and_filter`, `check_alert` with mocked DB
- Alert notification schema validation

All tests use an in-memory SQLite database — no network access, no real files.

```bash
# Run a specific test file
python -m pytest tests/test_matcher.py -v

# Run with short traceback on first failure
python -m pytest tests/ -x --tb=short
```

---

## Deployment notes

This is a development / demo project. Before production deployment:

1. **Database**: Replace SQLite with PostgreSQL (`DATABASE_URL=postgresql+asyncpg://...`). Install `asyncpg`.
2. **Rate limiting**: Replace the in-memory rate limiter (`app/middleware/rate_limit.py`) with a Redis-backed implementation (e.g. `slowapi` with `redis://`).
3. **CORS**: Restrict `allow_origins` in `main.py` to your actual frontend domain.
4. **Secret management**: Use environment variables or a secrets manager — never commit `.env`.
5. **Multiple workers**: The in-memory rate limiter and alert scheduler are single-process. Use a process manager (e.g., Gunicorn + uvicorn workers) only after migrating both to a shared store.
6. **File storage**: CV files are parsed and then discarded — only the structured profile is stored. If you need the original file, add object storage (S3, GCS).
7. **Auth**: All endpoints accept a `user_id` query param without authentication. Add OAuth2 / JWT before exposing to the internet.

### Taking screenshots for documentation

1. Start both servers (`uvicorn` on 8000, Vite on 3000).
2. Navigate to `http://localhost:3000`.
3. Upload a PDF CV from the Dashboard page.
4. Browse the Jobs page to see match scores.
5. Create an alert on the Alerts page.
6. Hit `POST /api/alerts/{id}/check` to trigger an immediate check and view results.
