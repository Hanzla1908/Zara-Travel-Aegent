# Architecture Overview

## Request Flow

```
User (React UI)
    │
    ▼
FastAPI /api/chat
    │
    ▼
JobFinderAgent (Claude tool-use loop)
    ├── search_jobs tool  →  job board APIs / web scraping
    ├── parse_cv tool     →  CV parser service
    └── rank_jobs tool    →  Claude scoring against CV
    │
    ▼
SQLite (persisted jobs, sessions)
    │
    ▼
JSON response → React UI
```

## Key Components

| Component | Responsibility |
|-----------|---------------|
| `agents/job_finder_agent.py` | Agentic loop using Claude tool-use |
| `tools/job_search.py` | Fetch raw listings from external sources |
| `services/cv_parser.py` | Extract skills/experience from resume files |
| `services/matcher.py` | Score each job against the parsed CV |
| `models/job.py` | Persist and query saved job listings |
