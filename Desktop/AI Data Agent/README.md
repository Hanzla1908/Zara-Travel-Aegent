# AI Data Analyst Agent

A premium AI-powered data analysis application built with Python, Streamlit, Pandas,
Plotly, and the Claude API.  Upload any CSV, Excel, Parquet, or JSON file and get
instant KPIs, automated insights, interactive charts, a built-in data explorer with
cleaning tools, an AI chat analyst, and one-click HTML/Excel report exports.

---

## Features

| Feature | Description |
|---------|-------------|
| **Overview** | Auto-generated KPI cards, trend charts, top/bottom performers |
| **Dashboard** | Interactive charts — histograms, box plots, bar charts, scatter, time series |
| **Data Explorer** | Searchable preview table, column profiler, data-quality report, cleaning actions, statistics, correlation matrix, export |
| **AI Analyst** | One-click structured insight report; multi-turn Q&A chat (validated query pipeline — no arbitrary code execution) |
| **Reports** | Ready-to-share HTML and Excel analysis reports |
| **Export** | Current / filtered / original data as CSV or XLSX; chart PNGs; full HTML & Excel reports |

---

## Quick Start

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env          # Windows
# cp .env.example .env          # macOS / Linux
# Open .env and set ANTHROPIC_API_KEY

# 4. Run the app
streamlit run main.py
```

Open **http://localhost:8501** in your browser and upload a dataset from the sidebar.

> The AI Analyst features require an Anthropic API key.  All other features
> (Explorer, Dashboard, Reports, Export) work without one.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values. **Never commit `.env`.**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | For AI features | — | Your Anthropic API key (`sk-ant-…`) |
| `APP_ENV` | No | `development` | `development` or `production` |
| `LOG_LEVEL` | No | `INFO` | Python log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `MAX_UPLOAD_MB` | No | `200` | Maximum upload file size in megabytes |
| `DEFAULT_MODEL` | No | `claude-opus-4-5` | Claude model ID for AI features |

Example `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-api03-...
LOG_LEVEL=INFO
MAX_UPLOAD_MB=200
DEFAULT_MODEL=claude-opus-4-5
```

---

## Supported File Formats

| Format | Notes |
|--------|-------|
| CSV (`.csv`) | Auto-detects delimiter (`,` `;` `\t` `\|`), encoding |
| Excel (`.xlsx` / `.xls`) | Multi-sheet support; switch sheets without re-uploading |
| Parquet (`.parquet`) | Efficient binary format for large datasets |
| JSON (`.json`) | Standard JSON array or JSON Lines format |

---

## Architecture

```
main.py                         ← Streamlit entry point, page routing
│
├── app/
│   ├── pages/                  ← One file per page
│   │   ├── overview.py         KPI cards, trend charts
│   │   ├── dashboard.py        Interactive chart builder
│   │   ├── data_explorer.py    Preview / profile / clean / export (6-tab UI)
│   │   ├── ai_analyst.py       Auto insights + validated query chat
│   │   ├── reports.py          Report browser
│   │   └── settings.py         App settings
│   │
│   ├── analytics/              ← Pure computation, no Streamlit imports
│   │   ├── profiler.py         Deep per-column profiling, quality score
│   │   ├── statistics.py       describe(), correlation_matrix()
│   │   ├── chart_factory.py    Plotly figure builders
│   │   ├── kpi_engine.py       KPI card computation with period deltas
│   │   ├── column_intelligence.py  Auto-detect date / KPI / category cols
│   │   ├── query_executor.py   Allowlist-validated Pandas query runner
│   │   ├── query_planner.py    Claude → validated JSON query plan
│   │   ├── insight_builder.py  Rule-based + AI insight generation
│   │   └── visualizer.py       Legacy Plotly helpers
│   │
│   ├── services/               ← External I/O and business logic
│   │   ├── data_loader.py      File parsing, encoding detection, validation
│   │   ├── claude_service.py   Anthropic API wrapper, usage limits
│   │   ├── export_service.py   CSV / XLSX / PNG bytes builders
│   │   ├── report_builder.py   HTML & Excel multi-sheet report generation
│   │   └── filter_service.py   DataFrame filter helpers
│   │
│   ├── components/             ← Reusable Streamlit UI widgets
│   │   ├── sidebar.py          Navigation + file upload
│   │   ├── cards.py            page_header(), empty_state(), metric cards
│   │   ├── icons.py            Inline Lucide SVG icons
│   │   ├── chat.py             Chat message renderer
│   │   ├── data_table.py       Styled table component
│   │   └── chart_viewer.py     Chart display wrapper
│   │
│   └── utils/                  ← Shared helpers
│       ├── config.py           load_dotenv, get()
│       ├── logger.py           Centralised logging setup
│       └── validators.py       File type / size / dataframe validation
│
└── tests/                      ← Pytest suite (35 tests)
    ├── test_analytics.py       Profiler, statistics, visualizer
    ├── test_services.py        Data loader, export service
    └── test_utils.py           Validators
```

### Data flow

```
Upload → data_loader.validate → data_loader.load → session_state["df"]
                                                          │
              ┌───────────────────────────────────────────┤
              ▼                                            ▼
       profiler.profile()                         kpi_engine.compute_kpis()
              │                                            │
       column stats, quality score               KPICard list → overview.py
              │
       data_explorer.py (6 tabs)
         Preview │ Profile │ Quality │ Stats │ Clean │ Export
              │
       export_service / report_builder
         CSV, XLSX, PNG, HTML report, Excel report
```

### AI Analyst query pipeline

```
User question
    │
    ▼
query_planner (Claude, bump=False) → JSON plan
    │
    ▼
query_executor validates plan against frozenset allowlists
    │
    ▼
Pandas executes validated plan → result DataFrame / figure
    │
    ▼
Claude explains result (bump=True)
```

No LLM-generated code or SQL is ever executed — all operations go through a strict allowlist.

---

## Running Tests

```bash
# Install test dependencies (only pytest is needed beyond requirements.txt)
pip install pytest

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_analytics.py -v

# Run with coverage
pip install pytest-cov
pytest tests/ --cov=app --cov-report=term-missing
```

Current coverage: **35 tests** across analytics, services, and utilities.

---

## Deploying to Streamlit Community Cloud

1. **Push to GitHub**

   ```bash
   git add .
   git commit -m "Prepare for deployment"
   git push origin main
   ```

2. **Create a new app** on [share.streamlit.io](https://share.streamlit.io):
   - Repository: `your-org/your-repo`
   - Branch: `main`
   - Main file: `main.py`

3. **Set secrets** — in the Streamlit Cloud app settings under *Secrets*, add:

   ```toml
   ANTHROPIC_API_KEY = "sk-ant-api03-..."
   MAX_UPLOAD_MB = "200"
   DEFAULT_MODEL = "claude-opus-4-5"
   LOG_LEVEL = "WARNING"
   ```

   > Streamlit Cloud injects these as environment variables; the app reads them
   > via `os.environ` / `load_dotenv()` just like a local `.env` file.

4. **`requirements.txt`** must be at the repo root (already is). Streamlit Cloud
   auto-installs it on every deploy.

5. **File uploads** on Streamlit Cloud are ephemeral — files are not persisted
   across sessions. This is by design; no user data is stored server-side.

---

## Security Notes

- **API key** — read from `os.environ`; never hard-coded, never logged.
- **File validation** — extension allowlist + size limit enforced before any parsing.
- **AI query safety** — the query executor uses frozenset allowlists for every operation
  type, filter operator, and aggregation function. Claude's output is never `eval()`-ed.
- **HTML report** — all cell values are `html.escape()`-ed before embedding in the
  downloadable report, preventing stored XSS if the dataset contains HTML/JS.
- **Logging** — only metadata (model name, elapsed time, usage count) is logged at
  DEBUG level. Prompt content and API keys are never written to logs.
- **Secrets** — `.env` and `secrets.toml` are `.gitignore`-d; only `.env.example`
  (with placeholder values) is committed.

---

## Tech Stack

| Layer | Library | Version |
|-------|---------|---------|
| UI | Streamlit | ≥ 1.66 |
| Data | Pandas | ≥ 2.0 |
| Numerics | NumPy | ≥ 1.25 |
| Visualisation | Plotly | ≥ 5.18 |
| Chart export | kaleido | ≥ 1.0 |
| Excel I/O | openpyxl | ≥ 3.1 |
| AI | anthropic (Python SDK) | ≥ 0.25 |
| Env config | python-dotenv | ≥ 1.0 |
| Tests | pytest | ≥ 9.0 |

---

## Performance Notes

- **Profiler** — DataFrames with > 50,000 rows are profiled using a 50k-row random
  sample for per-column statistics (value counts, string lengths, issue detection).
  Null counts, duplicate counts, and shape statistics are always computed on the full
  dataset.
- **Export** — The Excel report embeds up to 10,000 rows of data per sheet to keep
  file size manageable. Use the CSV export for the full dataset.
- **Session caching** — Profile results are cached in `st.session_state` keyed by
  `id(df)`, so switching tabs doesn't re-profile the same DataFrame.
- **Large files** — Recommended maximum is 200 MB / ~5 M rows for CSV. Very wide
  DataFrames (1,000+ columns) may profile slowly; set `LOG_LEVEL=DEBUG` to
  measure profiling time.
