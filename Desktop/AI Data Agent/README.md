# AI Data Analyst Agent

A premium AI-powered data analysis application built with Python, Streamlit, Pandas, Plotly, and the Claude API.

## Quick Start

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux
# Edit .env and set ANTHROPIC_API_KEY

# 4. Run the app
streamlit run main.py
```

## Project Structure

```
AI Data Agent/
├── main.py                     # Streamlit entry point
├── requirements.txt
├── .env.example
├── README.md
│
├── app/
│   ├── components/             # Reusable UI widgets
│   │   ├── header.py
│   │   ├── sidebar.py
│   │   ├── chat.py
│   │   ├── data_table.py
│   │   └── chart_viewer.py
│   │
│   ├── services/               # External integrations & business logic
│   │   ├── claude_service.py   # Anthropic API wrapper
│   │   ├── data_loader.py      # CSV/Excel/Parquet ingestion
│   │   └── export_service.py
│   │
│   ├── analytics/              # Pure data analysis modules
│   │   ├── profiler.py         # Dataset profiling
│   │   ├── statistics.py       # Descriptive & inferential stats
│   │   └── visualizer.py       # Plotly chart builders
│   │
│   └── utils/                  # Shared helpers
│       ├── config.py           # Env/settings loader
│       ├── logger.py
│       └── validators.py
│
├── tests/                      # Pytest test suite
│   ├── test_analytics.py
│   ├── test_services.py
│   └── test_utils.py
│
└── assets/
    ├── icons/
    └── styles/
        └── custom.css
```

## Tech Stack

| Layer | Library |
|-------|---------|
| UI | Streamlit |
| Data | Pandas, NumPy |
| Visualization | Plotly |
| AI | Anthropic Claude API |
| Config | python-dotenv, Pydantic |

## Running Tests

```bash
pytest tests/ -v
```
