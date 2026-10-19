"""Report builder — HTML and Excel analysis reports.

Public API
----------
  build_html_report(df, orig_df, prof, lr, history) -> bytes
  build_excel_report(df, orig_df, prof, lr, history) -> bytes
  fig_to_png_bytes(fig, width, height)               -> bytes | None
"""

from __future__ import annotations

import io
import base64
from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go

import app.analytics.chart_factory as cf
from app.analytics.statistics import correlation_matrix


# ── Chart helpers ────────────────────────────────────────────────────────────

def fig_to_png_bytes(
    fig: go.Figure,
    width: int = 900,
    height: int = 380,
    scale: float = 1.5,
) -> bytes | None:
    """Return PNG bytes using kaleido; None if kaleido unavailable or error."""
    try:
        return fig.to_image(format="png", width=width, height=height, scale=scale)
    except Exception:
        return None


def fig_to_png_b64(fig: go.Figure, **kwargs) -> str | None:
    """Return PNG as base64 string for HTML embedding, or None."""
    raw = fig_to_png_bytes(fig, **kwargs)
    if raw is None:
        return None
    return base64.b64encode(raw).decode()


# ── Rule-based key insights ──────────────────────────────────────────────────

def _insights(
    df: pd.DataFrame,
    prof: dict,
    history: list[dict],
) -> list[str]:
    """Generate plain-language insights from profile data."""
    out: list[str] = []
    summary = prof["summary"]
    quality = prof["quality"]
    col_profs = prof["columns"]

    # Quality grade
    score = quality["score"]
    grade = "A (Excellent)" if score >= 90 else (
            "B (Good)" if score >= 75 else (
            "C (Fair)" if score >= 60 else "D (Poor)"))
    out.append(f"Dataset quality score: {score}/100 — {grade}.")

    # Missing values
    total_cells = df.shape[0] * df.shape[1]
    null_cells   = int(df.isna().sum().sum())
    if null_cells > 0:
        null_pct = null_cells / total_cells * 100
        null_cols = sum(1 for cp in col_profs.values() if cp["null_count"] > 0)
        out.append(
            f"{null_cells:,} missing values across {null_cols} column(s) "
            f"({null_pct:.1f}% of all cells)."
        )
    else:
        out.append("No missing values — dataset is complete.")

    # Duplicates
    n_dup = int(df.duplicated().sum())
    if n_dup > 0:
        out.append(
            f"{n_dup:,} duplicate row(s) detected ({n_dup/len(df)*100:.1f}% of rows)."
        )
    else:
        out.append("No duplicate rows found.")

    # Type issues
    type_issues = [
        col for col, cp in col_profs.items()
        if any(i in cp["issues"] for i in ("numeric_as_string", "datetime_as_string"))
    ]
    if type_issues:
        out.append(
            f"{len(type_issues)} column(s) have data-type issues "
            f"({', '.join(type_issues[:4])}"
            f"{'…' if len(type_issues) > 4 else ''})."
        )

    # High null columns
    severe_null = [
        col for col, cp in col_profs.items()
        if cp["null_pct"] >= 50
    ]
    if severe_null:
        out.append(
            f"{len(severe_null)} column(s) are over 50% null: "
            f"{', '.join(severe_null[:4])}."
        )

    # Correlation highlight
    num_df = df.select_dtypes("number")
    if num_df.shape[1] >= 2:
        try:
            corr = correlation_matrix(df).abs()
            best_val = 0.0
            best_pair: tuple[str, str] | None = None
            seen: set[frozenset] = set()
            for a in corr.columns:
                for b in corr.columns:
                    pair = frozenset([a, b])
                    if a == b or pair in seen:
                        continue
                    seen.add(pair)
                    v = float(corr.loc[a, b])
                    if not pd.isna(v) and v > best_val:
                        best_val = v
                        best_pair = (a, b)
            if best_pair and best_val >= 0.3:
                direction = "positively" if correlation_matrix(df).loc[best_pair[0], best_pair[1]] > 0 else "negatively"
                out.append(
                    f"Strongest correlation: {best_pair[0]} and {best_pair[1]} "
                    f"are {direction} correlated (r = {best_val:.2f})."
                )
        except Exception:
            pass

    # Cleaning summary
    if history:
        out.append(
            f"{len(history)} cleaning operation(s) applied; "
            f"{history[0]['rows_before'] - history[-1]['rows_after']:,} rows removed in total."
        )

    return out


# ── HTML helpers ─────────────────────────────────────────────────────────────

def _df_to_html(df: pd.DataFrame, max_rows: int = 50, na_rep: str = "—") -> str:
    """Render a DataFrame as a styled HTML table (no classes needed — inline styles)."""
    cols   = df.columns.tolist()
    header = "".join(f"<th>{c}</th>" for c in cols)

    rows_html = ""
    for i, (_, row) in enumerate(df.head(max_rows).iterrows()):
        bg = " style='background:#f8fafc'" if i % 2 == 1 else ""
        cells = ""
        for c in cols:
            v = row[c]
            cells += f"<td>{na_rep if pd.isna(v) else v}</td>"
        rows_html += f"<tr{bg}>{cells}</tr>"

    return (
        "<table style='width:100%;border-collapse:collapse;font-size:12px;'>"
        f"<thead><tr style='background:#2563eb;color:white;'>{header}</tr></thead>"
        f"<tbody>{rows_html}</tbody></table>"
    )


_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: #1a2332; background: #fff; padding: 40px;
  max-width: 1120px; margin: 0 auto; font-size: 14px; line-height: 1.6;
}
h1 { font-size: 22px; font-weight: 800; }
h2 { font-size: 15px; font-weight: 700; margin: 28px 0 10px;
     border-bottom: 2px solid #2563eb; padding-bottom: 6px; color: #1a2332; }
h3 { font-size: 13px; font-weight: 600; margin: 14px 0 6px; color: #64748b; }
.header { background: #2563eb; color: #fff; padding: 28px 32px;
          border-radius: 12px; margin-bottom: 28px; }
.header h1 { color: #fff; }
.header .meta { font-size: 12px; opacity: .8; margin-top: 4px; }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
            gap: 12px; margin: 14px 0; }
.kpi { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
       padding: 14px; text-align: center; }
.kpi-v { font-size: 20px; font-weight: 800; color: #1a2332; }
.kpi-l { font-size: 10px; color: #64748b; text-transform: uppercase;
         letter-spacing: .06em; margin-top: 2px; }
.badge { display: inline-block; padding: 2px 7px; border-radius: 99px;
         font-size: 10px; font-weight: 700; }
.be { background: #fee2e2; color: #991b1b; }
.bw { background: #fef3c7; color: #92400e; }
.bi { background: #dbeafe; color: #1e40af; }
.bg { background: #d1fae5; color: #065f46; }
.insight { background: #fffbeb; border: 1px solid #fde68a;
           border-left: 4px solid #f59e0b; border-radius: 0 8px 8px 0;
           padding: 10px 14px; margin: 6px 0; font-size: 13px; }
.chart-img { max-width: 100%; border: 1px solid #e2e8f0; border-radius: 8px;
             margin: 10px 0; display: block; }
table { width: 100%; border-collapse: collapse; font-size: 12px; margin: 10px 0; }
th { background: #2563eb; color: #fff; padding: 8px 10px; text-align: left;
     font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
td { padding: 6px 10px; border-bottom: 1px solid #f0f4f8; }
tr:nth-child(even) td { background: #f8fafc; }
.section { margin-bottom: 30px; }
.footer { margin-top: 48px; padding-top: 16px; border-top: 1px solid #e2e8f0;
          font-size: 11px; color: #94a3b8; text-align: center; }
@media print { @page { margin: 1.5cm; } body { padding: 0; max-width: none; } }
"""


# ── HTML report ──────────────────────────────────────────────────────────────

def build_html_report(
    df: pd.DataFrame,
    orig_df: pd.DataFrame,
    prof: dict,
    lr: Any,
    history: list[dict],
) -> bytes:
    """Return a self-contained HTML analysis report as UTF-8 bytes."""
    now   = datetime.now()
    fname = lr.filename if lr else "dataset"
    rows, cols_n = df.shape
    null_cells   = int(df.isna().sum().sum())
    dup_rows     = int(df.duplicated().sum())
    mem_kb       = round(df.memory_usage(deep=True).sum() / 1024, 1)
    score        = prof["quality"]["score"]
    score_color  = "#10b981" if score >= 80 else ("#f59e0b" if score >= 60 else "#ef4444")

    is_cleaned = (len(df) != len(orig_df) or list(df.columns) != list(orig_df.columns))
    col_profs  = prof["columns"]

    # ── KPI strip ──────────────────────────────────────────────────────────
    def kpi(label: str, value: str) -> str:
        return (
            f'<div class="kpi">'
            f'<div class="kpi-v">{value}</div>'
            f'<div class="kpi-l">{label}</div>'
            f'</div>'
        )

    kpi_html = (
        kpi("Rows",       f"{rows:,}") +
        kpi("Columns",    str(cols_n)) +
        kpi("Missing",    f"{null_cells:,}") +
        kpi("Duplicates", f"{dup_rows:,}") +
        kpi("Quality",    f"<span style='color:{score_color}'>{score}</span>") +
        kpi("Memory",     f"{mem_kb} KB")
    )

    # ── Insights ───────────────────────────────────────────────────────────
    insights_html = "".join(
        f'<div class="insight">• {i}</div>'
        for i in _insights(df, prof, history)
    )

    # ── Dataset metadata table ─────────────────────────────────────────────
    meta_rows = [
        ("File", fname),
        ("File type", lr.file_type.upper() if lr else "—"),
        ("Active sheet", lr.active_sheet or "—" if lr else "—"),
        ("Analysis date", now.strftime("%Y-%m-%d %H:%M")),
        ("Rows (current)", f"{rows:,}"),
        ("Rows (original)", f"{len(orig_df):,}"),
        ("Columns", str(cols_n)),
        ("Cleaning applied", "Yes" if is_cleaned else "No"),
    ]
    meta_html = (
        "<table>"
        + "".join(f"<tr><td style='font-weight:600;width:140px;'>{k}</td><td>{v}</td></tr>"
                  for k, v in meta_rows)
        + "</table>"
    )

    # ── Data quality issues ────────────────────────────────────────────────
    checks = prof["quality"]["checks"]
    if checks:
        sev_map = {"error": "be", "warning": "bw", "info": "bi"}
        quality_rows = "".join(
            f"<tr>"
            f"<td><span class='badge {sev_map.get(c['severity'],'bi')}'>{c['severity']}</span></td>"
            f"<td style='font-weight:600'>{c['name']}</td>"
            f"<td>{c['description']}</td>"
            f"<td style='color:#64748b'>{', '.join(c['columns'][:6])}</td>"
            f"</tr>"
            for c in checks
        )
        quality_html = (
            "<table>"
            "<thead><tr><th>Severity</th><th>Issue</th><th>Description</th><th>Columns</th></tr></thead>"
            "<tbody>" + quality_rows + "</tbody></table>"
        )
    else:
        quality_html = "<p style='color:#10b981;font-size:13px;'>✓ No quality issues detected.</p>"

    # ── Descriptive statistics ─────────────────────────────────────────────
    num_df = df.select_dtypes("number")
    if not num_df.empty:
        from app.analytics.statistics import describe
        desc = num_df.describe().T.round(3)
        extra = describe(df)
        for col in ("skew", "kurtosis"):
            if col in extra.columns:
                desc[col] = extra[col].round(3)
        stats_html = _df_to_html(desc.reset_index().rename(columns={"index": "column"}))
    else:
        stats_html = "<p style='color:#64748b;font-size:13px;'>No numeric columns.</p>"

    # ── Correlation ────────────────────────────────────────────────────────
    num_cols = num_df.columns.tolist()
    corr_html = ""
    corr_chart_html = ""
    if len(num_cols) >= 2:
        try:
            corr = correlation_matrix(df).round(3)
            corr_html = _df_to_html(corr.reset_index().rename(columns={"index": ""}))

            if len(num_cols) >= 3:
                fig_heat = cf.correlation_heatmap(df, num_cols[:12], height=380)
                if fig_heat:
                    b64 = fig_to_png_b64(fig_heat, width=900, height=380)
                    if b64:
                        corr_chart_html = (
                            f'<img src="data:image/png;base64,{b64}" '
                            f'class="chart-img" alt="Correlation heatmap">'
                        )
        except Exception:
            pass

    # ── Column profile table ───────────────────────────────────────────────
    profile_rows = []
    for col, cp in col_profs.items():
        sev = "be" if "all_null" in cp["issues"] else (
              "bw" if any(i in cp["issues"] for i in ("high_null_severe", "constant")) else
              "bi" if cp["issues"] else "bg")
        issues_str = ", ".join(cp["issues"][:3]) if cp["issues"] else "—"
        sample = ", ".join(str(v) for v in cp.get("sample_values", [])[:3])[:60]
        profile_rows.append(
            f"<tr>"
            f"<td style='font-weight:600'>{col}</td>"
            f"<td>{cp['dtype_category']}</td>"
            f"<td>{cp['dtype']}</td>"
            f"<td>{cp['null_count']:,} ({cp['null_pct']:.1f}%)</td>"
            f"<td>{cp['unique_count']:,} ({cp['unique_pct']:.1f}%)</td>"
            f"<td><span class='badge {sev}'>{issues_str}</span></td>"
            f"<td style='color:#64748b;font-size:11px;'>{sample}</td>"
            f"</tr>"
        )
    profile_html = (
        "<table>"
        "<thead><tr>"
        "<th>Column</th><th>Category</th><th>Dtype</th>"
        "<th>Missing</th><th>Unique</th><th>Issues</th><th>Sample</th>"
        "</tr></thead><tbody>" + "".join(profile_rows) + "</tbody></table>"
    )

    # ── Column distribution charts ─────────────────────────────────────────
    dist_charts_html = ""
    numeric_top = num_cols[:4]
    chart_pairs = []
    for nc in numeric_top:
        fig = cf.histogram(df, nc, height=260)
        if fig:
            b64 = fig_to_png_b64(fig, width=440, height=260)
            if b64:
                chart_pairs.append(
                    f'<div style="flex:1;min-width:200px;">'
                    f'<h3>{nc} distribution</h3>'
                    f'<img src="data:image/png;base64,{b64}" class="chart-img" alt="{nc}">'
                    f'</div>'
                )
    if chart_pairs:
        dist_charts_html = (
            "<div style='display:flex;flex-wrap:wrap;gap:16px;'>"
            + "".join(chart_pairs)
            + "</div>"
        )

    # ── Categorical value-count charts ─────────────────────────────────────
    cat_charts_html = ""
    cat_cols = [
        c for c in df.select_dtypes("object").columns
        if 2 <= df[c].nunique() <= 20
    ][:2]
    cat_chart_pairs = []
    for cc in cat_cols:
        vc = df[cc].value_counts().head(12).reset_index()
        vc.columns = [cc, "count"]
        fig = cf.bar_ranked(vc, cc, "count", top_n=12, height=260)
        if fig:
            b64 = fig_to_png_b64(fig, width=440, height=260)
            if b64:
                cat_chart_pairs.append(
                    f'<div style="flex:1;min-width:200px;">'
                    f'<h3>{cc} value counts</h3>'
                    f'<img src="data:image/png;base64,{b64}" class="chart-img" alt="{cc}">'
                    f'</div>'
                )
    if cat_chart_pairs:
        cat_charts_html = (
            "<div style='display:flex;flex-wrap:wrap;gap:16px;'>"
            + "".join(cat_chart_pairs)
            + "</div>"
        )

    # ── Cleaning history ───────────────────────────────────────────────────
    history_html = ""
    if history:
        h_rows = "".join(
            f"<tr><td style='font-weight:600'>{i+1}</td>"
            f"<td>{op['description']}</td>"
            f"<td>{op['rows_before']:,}</td>"
            f"<td>{op['rows_after']:,}</td>"
            f"<td>{op['rows_before'] - op['rows_after']:,}</td></tr>"
            for i, op in enumerate(history)
        )
        history_html = (
            "<table>"
            "<thead><tr><th>#</th><th>Operation</th>"
            "<th>Rows Before</th><th>Rows After</th><th>Removed</th></tr></thead>"
            "<tbody>" + h_rows + "</tbody></table>"
        )

    # ── Data sample ────────────────────────────────────────────────────────
    sample_html = _df_to_html(df.head(50))

    # ── Assemble HTML ──────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Analysis Report — {fname}</title>
<style>{_CSS}</style>
</head>
<body>

<div class="header">
  <h1>Analysis Report</h1>
  <div class="meta">
    Dataset: <strong>{fname}</strong>
    &nbsp;·&nbsp; Generated: {now.strftime("%Y-%m-%d %H:%M")}
    &nbsp;·&nbsp; AI Data Agent
  </div>
</div>

<div class="section">
  <h2>Key Metrics</h2>
  <div class="kpi-grid">{kpi_html}</div>
</div>

<div class="section">
  <h2>Key Insights</h2>
  {insights_html}
</div>

<div class="section">
  <h2>Dataset Info</h2>
  {meta_html}
</div>

<div class="section">
  <h2>Data Quality</h2>
  <p style="font-size:13px;margin-bottom:10px;">
    Quality score: <strong style="color:{score_color}">{score}/100</strong>
  </p>
  {quality_html}
</div>

<div class="section">
  <h2>Descriptive Statistics</h2>
  {stats_html}
</div>

{"<div class='section'><h2>Correlation Analysis</h2>" + corr_chart_html + corr_html + "</div>" if corr_html else ""}

<div class="section">
  <h2>Column Profiles</h2>
  {profile_html}
</div>

{"<div class='section'><h2>Numeric Distributions</h2>" + dist_charts_html + "</div>" if dist_charts_html else ""}

{"<div class='section'><h2>Category Distributions</h2>" + cat_charts_html + "</div>" if cat_charts_html else ""}

{"<div class='section'><h2>Cleaning History</h2>" + history_html + "</div>" if history_html else ""}

<div class="section">
  <h2>Data Sample (first 50 rows)</h2>
  {sample_html}
</div>

<div class="footer">
  Generated by AI Data Agent &nbsp;·&nbsp; {now.strftime("%Y-%m-%d %H:%M")}
  &nbsp;·&nbsp; {rows:,} rows &times; {cols_n} columns
</div>

</body>
</html>"""

    return html.encode("utf-8")


# ── Excel report ─────────────────────────────────────────────────────────────

def build_excel_report(
    df: pd.DataFrame,
    orig_df: pd.DataFrame,
    prof: dict,
    lr: Any,
    history: list[dict],
) -> bytes:
    """Return a multi-sheet Excel report as bytes."""
    import openpyxl
    from openpyxl.styles import (
        PatternFill, Font, Alignment, Border, Side, numbers as xl_numbers,
    )
    from openpyxl.utils import get_column_letter

    now  = datetime.now()
    fname = lr.filename if lr else "dataset"

    # Helper style sets
    _HEADER_FILL = PatternFill("solid", fgColor="2563EB")
    _HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
    _HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=False)
    _ALT_FILL    = PatternFill("solid", fgColor="F8FAFC")
    _BORDER      = Border(
        bottom=Side(style="thin", color="E2E8F0"),
    )

    def _style_header(ws, row: int = 1) -> None:
        for cell in ws[row]:
            cell.fill  = _HEADER_FILL
            cell.font  = _HEADER_FONT
            cell.alignment = _HEADER_ALIGN

    def _style_rows(ws, start: int = 2) -> None:
        for i, row in enumerate(ws.iter_rows(min_row=start)):
            if i % 2 == 1:
                for cell in row:
                    cell.fill = _ALT_FILL
            for cell in row:
                cell.border = _BORDER
                cell.alignment = Alignment(vertical="center")

    def _auto_width(ws, min_w: int = 8, max_w: int = 40) -> None:
        for col in ws.columns:
            best = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[get_column_letter(col[0].column)].width = max(
                min_w, min(max_w, best + 2)
            )

    def _write_df(ws, frame: pd.DataFrame, start_row: int = 1) -> None:
        for c_idx, col_name in enumerate(frame.columns, 1):
            ws.cell(start_row, c_idx, str(col_name))
        for r_idx, (_, row) in enumerate(frame.iterrows(), start_row + 1):
            for c_idx, val in enumerate(row, 1):
                v = None if pd.isna(val) else val
                if isinstance(v, float) and v == int(v):
                    v = int(v)
                ws.cell(r_idx, c_idx, v)
        _style_header(ws, start_row)
        _style_rows(ws, start_row + 1)
        _auto_width(ws)
        ws.freeze_panes = ws.cell(start_row + 1, 1)

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove default sheet

    # ── Sheet 1: Summary ───────────────────────────────────────────────────
    ws_sum = wb.create_sheet("Summary")
    quality = prof["quality"]
    null_cells = int(df.isna().sum().sum())
    tot_cells  = df.shape[0] * df.shape[1]
    n_dup      = int(df.duplicated().sum())
    mem_kb     = round(df.memory_usage(deep=True).sum() / 1024, 1)

    summary_data = [
        ("Property", "Value"),
        ("File", fname),
        ("File type", lr.file_type.upper() if lr else "—"),
        ("Active sheet", lr.active_sheet or "—" if lr else "—"),
        ("Analysis date", now.strftime("%Y-%m-%d %H:%M")),
        ("", ""),
        ("Rows (current)", df.shape[0]),
        ("Rows (original)", len(orig_df)),
        ("Columns", df.shape[1]),
        ("", ""),
        ("Missing cells", null_cells),
        ("Missing %", f"{null_cells/tot_cells*100:.2f}%" if tot_cells else "0%"),
        ("Duplicate rows", n_dup),
        ("Memory (KB)", mem_kb),
        ("", ""),
        ("Quality score", quality["score"]),
        ("Quality grade", ("A – Excellent" if quality["score"] >= 90 else
                            "B – Good"      if quality["score"] >= 75 else
                            "C – Fair"      if quality["score"] >= 60 else
                            "D – Poor")),
        ("Errors", sum(1 for c in quality["checks"] if c["severity"] == "error")),
        ("Warnings", sum(1 for c in quality["checks"] if c["severity"] == "warning")),
        ("", ""),
        ("Cleaning operations applied", len(history)),
    ]

    for r_idx, (label, value) in enumerate(summary_data, 1):
        ws_sum.cell(r_idx, 1, label)
        ws_sum.cell(r_idx, 2, value)
        if label in ("Property",):
            for c in (ws_sum.cell(r_idx, 1), ws_sum.cell(r_idx, 2)):
                c.fill = _HEADER_FILL
                c.font = _HEADER_FONT
                c.alignment = _HEADER_ALIGN
    _auto_width(ws_sum)

    # Key insights
    ws_sum.cell(len(summary_data) + 2, 1, "Key Insights").font = Font(bold=True, size=11)
    for i, insight in enumerate(_insights(df, prof, history), len(summary_data) + 3):
        ws_sum.cell(i, 1, f"• {insight}")
    _auto_width(ws_sum)

    # ── Sheet 2: Data Quality ──────────────────────────────────────────────
    ws_q = wb.create_sheet("Data Quality")
    checks = quality["checks"]
    if checks:
        q_frame = pd.DataFrame([{
            "Severity": c["severity"].upper(),
            "Issue":    c["name"],
            "Description": c["description"],
            "Affected columns": ", ".join(c["columns"][:8]),
            "Count": c.get("count", len(c["columns"])),
        } for c in checks])
        _write_df(ws_q, q_frame)
    else:
        ws_q["A1"] = "No quality issues detected."
        ws_q["A1"].font = Font(bold=True, color="10B981")

    # ── Sheet 3: Column Profiles ───────────────────────────────────────────
    ws_prof = wb.create_sheet("Column Profiles")
    col_profs = prof["columns"]
    prof_rows = []
    for col, cp in col_profs.items():
        row: dict[str, Any] = {
            "Column":    col,
            "Category":  cp["dtype_category"],
            "Dtype":     cp["dtype"],
            "Null count": cp["null_count"],
            "Null %":    round(cp["null_pct"], 2),
            "Unique":    cp["unique_count"],
            "Unique %":  round(cp["unique_pct"], 2),
            "Issues":    ", ".join(cp["issues"]) if cp["issues"] else "—",
            "Sample values": ", ".join(str(v) for v in cp.get("sample_values", [])[:3])[:80],
        }
        if cp["dtype_category"] == "numeric":
            row.update({
                "Min":   cp.get("min"),   "Max":  cp.get("max"),
                "Mean":  cp.get("mean"),  "Std":  cp.get("std"),
            })
        prof_rows.append(row)
    if prof_rows:
        _write_df(ws_prof, pd.DataFrame(prof_rows))

    # ── Sheet 4: Statistics ────────────────────────────────────────────────
    ws_stats = wb.create_sheet("Statistics")
    num_df = df.select_dtypes("number")
    if not num_df.empty:
        from app.analytics.statistics import describe
        desc = num_df.describe().T.round(4)
        extra = describe(df)
        for col in ("skew", "kurtosis"):
            if col in extra.columns:
                desc[col] = extra[col].round(3)
        desc = desc.reset_index().rename(columns={"index": "Column"})
        _write_df(ws_stats, desc)

        # Correlation — start below stats + 2 blank rows
        stat_end_row = len(desc) + 3
        ws_stats.cell(stat_end_row, 1, "Correlation Matrix").font = Font(bold=True, size=11)
        try:
            corr = correlation_matrix(df).round(3)
            corr_frame = corr.reset_index().rename(columns={"index": ""})
            _write_df(ws_stats, corr_frame, start_row=stat_end_row + 1)
        except Exception:
            pass
    else:
        ws_stats["A1"] = "No numeric columns in dataset."

    # ── Sheet 5: Data (current, up to 10 000 rows) ─────────────────────────
    ws_data = wb.create_sheet("Data")
    _write_df(ws_data, df.head(10_000))

    # ── Sheet 6: Original (if cleaned) ────────────────────────────────────
    if len(history) > 0 and not orig_df.equals(df):
        ws_orig = wb.create_sheet("Original Data")
        _write_df(ws_orig, orig_df.head(10_000))

    # ── Sheet 7: Cleaning History ──────────────────────────────────────────
    if history:
        ws_hist = wb.create_sheet("Cleaning History")
        hist_frame = pd.DataFrame([{
            "Step":        i + 1,
            "Operation":   op["description"],
            "Rows before": op["rows_before"],
            "Rows after":  op["rows_after"],
            "Rows removed": op["rows_before"] - op["rows_after"],
        } for i, op in enumerate(history)])
        _write_df(ws_hist, hist_frame)

    # ── Chart images sheet ─────────────────────────────────────────────────
    try:
        from openpyxl.drawing.image import Image as XLImage
        chart_imgs: list[tuple[str, bytes]] = []

        if len(num_df.columns) >= 3:
            fig = cf.correlation_heatmap(df, num_df.columns[:12].tolist(), height=380)
            if fig:
                png = fig_to_png_bytes(fig, width=900, height=380)
                if png:
                    chart_imgs.append(("Correlation Heatmap", png))

        for nc in num_df.columns[:3].tolist():
            fig = cf.histogram(df, nc, height=260)
            if fig:
                png = fig_to_png_bytes(fig, width=600, height=260)
                if png:
                    chart_imgs.append((f"Distribution: {nc}", png))

        if chart_imgs:
            ws_charts = wb.create_sheet("Charts")
            row_cursor = 1
            for title, png_bytes in chart_imgs:
                ws_charts.cell(row_cursor, 1, title).font = Font(bold=True, size=11)
                row_cursor += 1
                img_buf = io.BytesIO(png_bytes)
                xl_img = XLImage(img_buf)
                xl_img.anchor = f"A{row_cursor}"
                ws_charts.add_image(xl_img)
                row_cursor += 22
    except Exception:
        pass  # chart sheet is optional

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
