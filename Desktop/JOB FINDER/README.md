# AI Job Finder Agent

An AI-powered job search assistant that parses your CV, searches job boards, and ranks opportunities using Claude.

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite |
| Backend | Python 3.11 + FastAPI |
| AI | Anthropic Claude API |
| Database | SQLite (via SQLAlchemy async) |

## Project Structure

```
JOB FINDER/
├── frontend/               # React + Vite UI
│   └── src/
│       ├── components/
│       ├── pages/
│       ├── hooks/
│       └── utils/
├── backend/
│   ├── app/
│   │   ├── agents/         # AI agent orchestration
│   │   ├── tools/          # Job search tools
│   │   ├── services/       # CV parsing, matching, ranking
│   │   ├── models/         # SQLAlchemy models + DB session
│   │   └── api/            # FastAPI route handlers
│   └── tests/
├── docs/
├── .env.example
└── README.md
```

## Getting Started

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp ../.env.example ../.env    # then fill in ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on http://localhost:3000 and proxies `/api` requests to the backend on port 8000.

## Development Phases

1. **Structure** (done) — project scaffold
2. **CV Upload & Parsing** — PDF/DOCX → structured profile
3. **Job Search Tools** — query job boards via APIs/scraping
4. **AI Agent** — Claude orchestrates search + matching
5. **Ranking & UI** — scored results with explanations
