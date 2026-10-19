"""KPI Engine — auto-generate meaningful KPI cards from a DataFrame.

Selects the best numeric columns, computes aggregate values, and optionally
computes period-over-period deltas when a date column is available.

All computation is read-only; the original DataFrame is never modified.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import pandas as pd

from app.analytics.column_intelligence import ColumnIntel
from app.components.icons import icon as svg_icon


# ── Output dataclass ─────────────────────────────────────────────────────────

@dataclass
class KPICard:
    label: str           # human-readable column name
    value: str           # formatted value (e.g. "1,234,567" or "3.45%")
    delta: str           # formatted delta (e.g. "+12.3%") — empty if n/a
    delta_positive: bool # True when increase is good
    icon: str            # inline SVG HTML
    sublabel: str        # "Total" / "Mean" / "Count" / "Unique" / "Range"


# ── Public entry point ───────────────────────────────────────────────────────

def compute_kpis(
    df: pd.DataFrame,
    intel: ColumnIntel,
    full_df: pd.DataFrame | None = None,
    max_cards: int = 5,
) -> list[KPICard]:
    """Return up to max_cards KPICard objects.

    df        — the (possibly filtered) DataFrame to show values for
    full_df   — unfiltered DataFrame used to calculate period comparison
                (when None, no delta is computed)
    intel     — pre-computed ColumnIntel from analyze(full_df or df)
    """
    cards: list[KPICard] = []

    # ── Row count card ───────────────────────────────────────────────────
    if full_df is not None and len(full_df) != len(df):
        pct = len(df) / len(full_df) * 100
        cards.append(KPICard(
            label="Rows selected",
            value=f"{len(df):,}",
            delta=f"of {len(full_df):,} ({pct:.0f}%)",
            delta_positive=True,
            icon=svg_icon("list", 20, "#2563eb"),
            sublabel="Count",
        ))
    else:
        cards.append(KPICard(
            label="Total rows",
            value=f"{len(df):,}",
            delta="",
            delta_positive=True,
            icon=svg_icon("list", 20, "#2563eb"),
            sublabel="Count",
        ))

    # ── KPI sum columns ──────────────────────────────────────────────────
    for col in intel.kpi_cols[:3]:
        if col not in df.columns:
            continue
        card = _sum_card(col, df, full_df, intel)
        if card:
            cards.append(card)
        if len(cards) >= max_cards:
            break

    # ── Mean columns ─────────────────────────────────────────────────────
    if len(cards) < max_cards:
        for col in intel.mean_cols[:2]:
            if col not in df.columns:
                continue
            card = _mean_card(col, df, full_df)
            if card:
                cards.append(card)
            if len(cards) >= max_cards:
                break

    # ── Category unique count ────────────────────────────────────────────
    if len(cards) < max_cards and intel.primary_category:
        col = intel.primary_category
        if col in df.columns:
            n_unique = int(df[col].nunique())
            cards.append(KPICard(
                label=_display_name(col),
                value=f"{n_unique:,}",
                delta="",
                delta_positive=True,
                icon=svg_icon("layers", 20, "#7c3aed"),
                sublabel="Unique values",
            ))

    # ── Date range ───────────────────────────────────────────────────────
    if len(cards) < max_cards and intel.primary_date:
        card = _date_range_card(intel.primary_date, df)
        if card:
            cards.append(card)

    return cards[:max_cards]


# ── Card builders ─────────────────────────────────────────────────────────────

def _sum_card(
    col: str,
    df: pd.DataFrame,
    full_df: pd.DataFrame | None,
    intel: ColumnIntel,
) -> KPICard | None:
    series = pd.to_numeric(df[col], errors="coerce").dropna()
    if series.empty:
        return None
    total = float(series.sum())

    # period-over-period delta via date column
    delta = ""
    delta_positive = True
    if full_df is not None and intel.primary_date and len(df) < len(full_df) * 0.95:
        # Filtered — compare filtered total vs full total
        full_series = pd.to_numeric(full_df[col], errors="coerce").dropna()
        full_total = float(full_series.sum()) if not full_series.empty else 0.0
        if full_total > 0:
            pct = (total / full_total - 1) * 100
            sign = "+" if pct >= 0 else ""
            delta = f"{sign}{pct:.1f}% of total"
            delta_positive = pct >= 0
    elif full_df is not None and intel.primary_date:
        # Full data — compute last-third vs prior-third
        delta_val = _period_delta(col, intel.primary_date, full_df)
        if delta_val is not None:
            sign = "+" if delta_val >= 0 else ""
            delta = f"{sign}{delta_val:.1f}% vs prior period"
            delta_positive = delta_val >= 0

    return KPICard(
        label=_display_name(col),
        value=_fmt_number(total),
        delta=delta,
        delta_positive=delta_positive,
        icon=_icon_for_col(col),
        sublabel="Total",
    )


def _mean_card(
    col: str,
    df: pd.DataFrame,
    full_df: pd.DataFrame | None,
) -> KPICard | None:
    series = pd.to_numeric(df[col], errors="coerce").dropna()
    if series.empty:
        return None
    mean_val = float(series.mean())

    delta = ""
    delta_positive = True
    if full_df is not None and len(df) < len(full_df) * 0.95:
        full_series = pd.to_numeric(full_df[col], errors="coerce").dropna()
        full_mean = float(full_series.mean()) if not full_series.empty else 0.0
        if full_mean > 0:
            pct = (mean_val / full_mean - 1) * 100
            sign = "+" if pct >= 0 else ""
            delta = f"{sign}{pct:.1f}% vs all"
            delta_positive = pct >= 0

    return KPICard(
        label=_display_name(col),
        value=_fmt_number(mean_val),
        delta=delta,
        delta_positive=delta_positive,
        icon=_icon_for_col(col),
        sublabel="Mean",
    )


def _date_range_card(col: str, df: pd.DataFrame) -> KPICard | None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            dates = pd.to_datetime(df[col], errors="coerce", format="mixed").dropna()
        except Exception:
            dates = pd.to_datetime(df[col], errors="coerce").dropna()
    if len(dates) < 2:
        return None
    days = int((dates.max() - dates.min()).days)
    start = str(dates.min().date())
    end = str(dates.max().date())
    return KPICard(
        label=_display_name(col),
        value=f"{days:,} days",
        delta=f"{start} → {end}",
        delta_positive=True,
        icon=svg_icon("calendar-range", 20, "#f59e0b"),
        sublabel="Date range",
    )


# ── Period delta helper ───────────────────────────────────────────────────────

def _period_delta(
    value_col: str,
    date_col: str,
    df: pd.DataFrame,
    split_pct: float = 0.33,
) -> float | None:
    """Compare last split_pct of time range vs prior split_pct.  Returns % change."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            dates = pd.to_datetime(df[date_col], errors="coerce", format="mixed")
        except Exception:
            dates = pd.to_datetime(df[date_col], errors="coerce")

    values = pd.to_numeric(df[value_col], errors="coerce")
    mask = dates.notna() & values.notna()
    if mask.sum() < 8:
        return None

    d = dates[mask]
    v = values[mask]
    d_min, d_max = d.min(), d.max()
    span = d_max - d_min
    if span.days < 7:
        return None

    cutoff_recent = d_max - span * split_pct
    cutoff_prior  = d_min + span * split_pct

    recent = float(v[d >= cutoff_recent].sum())
    prior  = float(v[d <= cutoff_prior].sum())

    if prior == 0:
        return None
    return (recent / prior - 1) * 100


# ── Formatters ────────────────────────────────────────────────────────────────

def _fmt_number(v: float) -> str:
    if abs(v) >= 1_000_000_000:
        return f"{v/1_000_000_000:.2f}B"
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"{v:,.0f}"
    if abs(v) < 1 and v != 0:
        return f"{v:.4f}"
    return f"{v:,.2f}"


def _display_name(col: str) -> str:
    return col.replace("_", " ").replace("-", " ").title()


def _icon_for_col(col: str) -> str:
    col_l = col.lower()
    if any(k in col_l for k in ("revenue", "sales", "income", "profit")):
        return svg_icon("trending-up", 20, "#10b981")
    if any(k in col_l for k in ("cost", "expense", "spend", "loss")):
        return svg_icon("trending-down", 20, "#ef4444")
    if any(k in col_l for k in ("user", "customer", "visit", "session", "view")):
        return svg_icon("users", 20, "#2563eb")
    if any(k in col_l for k in ("order", "transaction", "conversion")):
        return svg_icon("shopping-cart", 20, "#f59e0b")
    if any(k in col_l for k in ("score", "rating", "nps", "csat")):
        return svg_icon("star", 20, "#f59e0b")
    if any(k in col_l for k in ("rate", "ratio", "pct", "percent")):
        return svg_icon("percent", 20, "#7c3aed")
    if any(k in col_l for k in ("qty", "quantity", "unit", "count")):
        return svg_icon("package", 20, "#64748b")
    return svg_icon("bar-chart-2", 20, "#2563eb")
