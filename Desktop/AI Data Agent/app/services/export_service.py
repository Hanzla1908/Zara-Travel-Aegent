"""Export utilities — bytes builders for all downloadable formats.

Public API
----------
  to_csv_bytes(df)                 -> bytes
  to_excel_bytes(df)               -> bytes
  to_chart_png(fig)                -> bytes | None
  get_filtered_view(df)            -> pd.DataFrame   (applies preview session filters)
"""

from __future__ import annotations

import io
import pandas as pd


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return buf.getvalue()


def to_chart_png(fig, width: int = 1100, height: int = 460) -> bytes | None:
    """Return PNG bytes for a Plotly figure. Returns None if kaleido is unavailable."""
    try:
        return fig.to_image(format="png", width=width, height=height, scale=1.5)
    except Exception:
        return None


def get_filtered_view(df: pd.DataFrame) -> pd.DataFrame:
    """Re-apply the Preview tab's current filter/sort/column state to df.

    Reads from Streamlit session_state; safe to call from any tab.
    Returns the full filtered+sorted subset (no row-count cap).
    """
    try:
        import streamlit as st

        all_cols  = df.columns.tolist()
        col_sel   = st.session_state.get("prev_cols") or all_cols
        # keep only columns that still exist in df
        col_sel   = [c for c in col_sel if c in df.columns]
        view      = df[col_sel] if col_sel else df.copy()

        search = st.session_state.get("prev_search", "")
        if search:
            mask = view.apply(
                lambda c: c.astype(str).str.contains(search, case=False, na=False)
            ).any(axis=1)
            view = view[mask]

        sort_col = st.session_state.get("prev_sort_col", "(none)")
        sort_dir = st.session_state.get("prev_sort_dir", "↑ Asc")
        if sort_col and sort_col != "(none)" and sort_col in view.columns:
            view = view.sort_values(sort_col, ascending=(sort_dir == "↑ Asc"))

        return view.reset_index(drop=True)
    except Exception:
        return df.copy()
