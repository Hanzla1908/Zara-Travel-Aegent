"""Query Planner — convert natural-language questions into validated query plans.

Claude returns a structured JSON object describing an analytical operation.
Every field is validated against the DataFrame's actual schema and an
allowlist of safe operations **before** any execution takes place.

No LLM-generated code is ever executed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.analytics.column_intelligence import ColumnIntel

# ── Allowlists ────────────────────────────────────────────────────────────────

ALLOWED_OPERATIONS = frozenset({
    "groupby_agg",   # group by 1+ columns, aggregate metrics
    "time_series",   # resample by time period, aggregate
    "top_n",         # sort by column, take top/bottom N rows
    "distribution",  # value_counts or numeric histogram
    "correlation",   # correlation matrix for numeric columns
    "describe",      # descriptive stats for selected columns
    "cross_tab",     # pivot / crosstab between two categoricals
    "filter_agg",    # filter rows then aggregate
})

ALLOWED_AGGS = frozenset({
    "sum", "mean", "count", "min", "max",
    "std", "median", "nunique", "first", "last",
})

ALLOWED_FILTER_OPS = frozenset({
    "eq", "ne", "gt", "lt", "gte", "lte", "isin", "not_isin",
})

ALLOWED_PERIODS = frozenset({"D", "W", "ME", "QE", "YE"})

ALLOWED_CHART_TYPES = frozenset({
    "bar", "line", "scatter", "pie", "heatmap",
    "histogram", "area", "box",
})

MAX_LIMIT = 500


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class FilterSpec:
    column: str
    op: str
    value: Any


@dataclass
class MetricSpec:
    column: str
    agg: str


@dataclass
class SortSpec:
    column: str
    ascending: bool = False


@dataclass
class QueryPlan:
    operation: str
    group_by: list[str]          = field(default_factory=list)
    date_column: str | None      = None
    period: str | None           = None
    metrics: list[MetricSpec]    = field(default_factory=list)
    columns: list[str]           = field(default_factory=list)
    filters: list[FilterSpec]    = field(default_factory=list)
    sort: SortSpec | None        = None
    limit: int                   = 20
    chart_hint: str              = "bar"
    intent: str                  = ""


# ── Claude planning system prompt ─────────────────────────────────────────────

PLANNER_SYSTEM = """\
You are a data analyst query planner. Convert a natural-language question into
a structured JSON query plan that a Python program will execute safely.

CRITICAL RULES:
1. Return ONLY a valid JSON object — no prose, no markdown fences, no code.
2. Only use column names that appear verbatim in the provided schema.
3. Only use the operations and aggregations listed below.
4. Keep "intent" ≤ 15 words.
5. If the question cannot be answered from the schema, return:
   {"operation":"describe","columns":[],"intent":"general question — no specific query"}

ALLOWED OPERATIONS:
  groupby_agg  — group by one or more columns, aggregate metrics
  time_series  — resample by date period, aggregate metrics
  top_n        — sort by a column, take top/bottom N rows
  distribution — value counts or histogram for one column
  correlation  — correlation matrix for numeric columns
  describe     — descriptive statistics for selected columns
  cross_tab    — cross-tabulation between two categorical columns
  filter_agg   — filter rows then aggregate

ALLOWED AGGREGATIONS: sum, mean, count, min, max, std, median, nunique, first, last
ALLOWED FILTER OPS:   eq, ne, gt, lt, gte, lte, isin, not_isin
ALLOWED PERIODS:      D (day), W (week), ME (month), QE (quarter), YE (year)
ALLOWED CHARTS:       bar, line, scatter, pie, heatmap, histogram, area, box

JSON SCHEMA — include only applicable fields:
{
  "operation":   "<one of the allowed operations>",
  "group_by":    ["col1"],
  "date_column": "col",
  "period":      "ME",
  "metrics":     [{"column": "col", "agg": "sum"}],
  "columns":     ["col1", "col2"],
  "filters":     [{"column": "col", "op": "eq", "value": "X"}],
  "sort":        {"column": "col", "ascending": false},
  "limit":       10,
  "chart_hint":  "bar",
  "intent":      "short description"
}
"""


# ── Schema summary builder ────────────────────────────────────────────────────

def build_schema_summary(df: pd.DataFrame, intel: ColumnIntel) -> str:
    """Return a compact schema string for Claude's planning prompt."""
    lines: list[str] = [
        f"Dataset: {len(df):,} rows × {len(df.columns)} columns",
    ]

    if intel.date_cols:
        lines.append(f"Date columns: {', '.join(intel.date_cols[:4])}")

    all_num = intel.kpi_cols + intel.mean_cols + intel.dist_cols
    num_in_df = [c for c in all_num if c in df.columns]
    if num_in_df:
        lines.append("Numeric columns:")
        for c in num_in_df[:8]:
            try:
                s = pd.to_numeric(df[c], errors="coerce").dropna()
                lines.append(f"  {c}  (min={_fmt(s.min())}, max={_fmt(s.max())}, mean={_fmt(s.mean())})")
            except Exception:
                lines.append(f"  {c}  (numeric)")

    cat_in_df = [c for c in intel.cat_cols if c in df.columns]
    if cat_in_df:
        lines.append("Categorical columns:")
        for c in cat_in_df[:6]:
            try:
                n = df[c].nunique()
                top = df[c].value_counts().index[:4].tolist()
                lines.append(f"  {c}  ({n} unique values: {top})")
            except Exception:
                lines.append(f"  {c}  (categorical)")

    return "\n".join(lines)


def build_suggestion_questions(df: pd.DataFrame, intel: ColumnIntel) -> list[str]:
    """Generate context-aware starter questions for the current dataset."""
    suggestions: list[str] = []
    cat = intel.primary_category
    date = intel.primary_date
    kpi = intel.kpi_cols[0] if intel.kpi_cols else (intel.mean_cols[0] if intel.mean_cols else None)

    kpi_nice = kpi.replace("_", " ") if kpi else None
    cat_nice = cat.replace("_", " ") if cat else None

    if cat and kpi:
        suggestions.append(f"Which {cat_nice} generated the highest {kpi_nice}?")
        suggestions.append(f"Compare {kpi_nice} across all {cat_nice} groups")
    if date and kpi:
        suggestions.append(f"Show the monthly trend of {kpi_nice}")
    if cat and kpi:
        suggestions.append(f"What are the top 10 {cat_nice} by {kpi_nice}?")
    if kpi:
        suggestions.append(f"Show the distribution of {kpi_nice}")
    if intel.kpi_cols and intel.mean_cols:
        suggestions.append("What correlations exist between numeric columns?")
    if not suggestions:
        suggestions = [
            "Summarise this dataset",
            "Show me the top 10 rows by value",
            "What are the key statistics?",
            "Show the data distribution",
        ]
    return suggestions[:5]


# ── Parse + validate ──────────────────────────────────────────────────────────

def parse_and_validate(
    raw_json: str,
    df: pd.DataFrame,
    intel: ColumnIntel,
) -> QueryPlan | str:
    """Parse Claude's JSON response and validate it against the DataFrame schema.

    Returns a QueryPlan on success, or an error string on failure.
    """
    text = raw_json.strip()
    # Strip markdown fences if Claude wrapped its response
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        d = json.loads(text)
    except json.JSONDecodeError as exc:
        return f"Could not parse query plan (invalid JSON): {exc}"

    if not isinstance(d, dict):
        return "Query plan must be a JSON object."

    operation = str(d.get("operation", ""))
    if operation not in ALLOWED_OPERATIONS:
        return (
            f"Unknown operation '{operation}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_OPERATIONS))}"
        )

    existing = set(df.columns)
    errors: list[str] = []

    def _check(col: str, ctx: str) -> bool:
        if col not in existing:
            errors.append(f"Column '{col}' not found (in {ctx})")
            return False
        return True

    # group_by
    group_by: list[str] = [c for c in d.get("group_by", []) if _check(c, "group_by")]

    # date_column
    date_column: str | None = d.get("date_column")
    if date_column and not _check(date_column, "date_column"):
        date_column = None

    # period
    period: str | None = d.get("period")
    if period and period not in ALLOWED_PERIODS:
        errors.append(f"Period '{period}' not in {sorted(ALLOWED_PERIODS)}")
        period = None

    # metrics
    metrics: list[MetricSpec] = []
    for m in d.get("metrics", []):
        col, agg = str(m.get("column", "")), str(m.get("agg", "sum"))
        if not _check(col, "metrics"):
            continue
        if agg not in ALLOWED_AGGS:
            errors.append(f"Aggregation '{agg}' not allowed (column '{col}')")
            continue
        metrics.append(MetricSpec(column=col, agg=agg))

    # columns
    columns: list[str] = [c for c in d.get("columns", []) if _check(c, "columns")]

    # filters
    filters: list[FilterSpec] = []
    for f in d.get("filters", []):
        col, op, val = str(f.get("column", "")), str(f.get("op", "")), f.get("value")
        if not _check(col, "filters"):
            continue
        if op not in ALLOWED_FILTER_OPS:
            errors.append(f"Filter op '{op}' not allowed")
            continue
        filters.append(FilterSpec(column=col, op=op, value=val))

    # sort — column may be in the result (aggregated), not necessarily in original df
    sort: SortSpec | None = None
    if raw_sort := d.get("sort"):
        sort = SortSpec(
            column=str(raw_sort.get("column", "")),
            ascending=bool(raw_sort.get("ascending", False)),
        )

    # limit
    try:
        limit = min(int(d.get("limit", 20)), MAX_LIMIT)
    except (TypeError, ValueError):
        limit = 20

    # chart_hint
    chart_hint = str(d.get("chart_hint", "bar"))
    if chart_hint not in ALLOWED_CHART_TYPES:
        chart_hint = "bar"

    intent = str(d.get("intent", ""))[:200]

    if errors:
        return "Query validation errors:\n" + "\n".join(f"  • {e}" for e in errors)

    return QueryPlan(
        operation=operation,
        group_by=group_by,
        date_column=date_column,
        period=period,
        metrics=metrics,
        columns=columns,
        filters=filters,
        sort=sort,
        limit=limit,
        chart_hint=chart_hint,
        intent=intent,
    )


# ── Explanation system prompt ─────────────────────────────────────────────────

EXPLAINER_SYSTEM = """\
You are a data analyst explaining the result of a computed query.
Rules:
- Be direct and concise: 2–4 sentences.
- Lead with the key finding.
- Reference specific values from the result when they support the finding.
- If there is a notable pattern, outlier, or trend, call it out.
- Do NOT restate the question or describe what you are about to do.
- Do NOT invent numbers — only reference what is in the RESULT section.
"""

FALLBACK_EXPLAINER_SYSTEM = """\
You are a data analyst assistant. The user asked a question about their dataset.
Answer helpfully and concisely using only the information in the schema.
If the question can't be answered from the schema, say so and suggest what data would be needed.
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(v: Any) -> str:
    try:
        f = float(v)
        if abs(f) >= 1_000_000:
            return f"{f/1_000_000:.1f}M"
        if abs(f) >= 1_000:
            return f"{f:,.0f}"
        return f"{f:.2f}"
    except Exception:
        return str(v)
