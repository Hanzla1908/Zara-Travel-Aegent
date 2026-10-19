"""Reusable HTML card components rendered via st.markdown."""

import streamlit as st


def metric_card(label: str, value: str, delta: str = "", delta_type: str = "neutral", icon: str = "") -> None:
    icon_html = f'<div class="mc-icon">{icon}</div>' if icon else ""
    delta_html = ""
    if delta:
        arrow = "▲" if delta_type == "positive" else ("▼" if delta_type == "negative" else "—")
        delta_html = f'<div class="mc-delta {delta_type}">{arrow} {delta}</div>'
    st.html(
        f'<div class="metric-card">{icon_html}'
        f'<div class="mc-label">{label}</div>'
        f'<div class="mc-value">{value}</div>'
        f'{delta_html}</div>'
    )


def metric_row(metrics: list[dict]) -> None:
    """Render a list of metric dicts inside a responsive grid row.

    Each dict: {label, value, delta?, delta_type?, icon?}
    """
    cards_html = ""
    for m in metrics:
        icon_html = f'<div class="mc-icon">{m.get("icon","")}</div>' if m.get("icon") else ""
        delta = m.get("delta", "")
        dt = m.get("delta_type", "neutral")
        arrow = "▲" if dt == "positive" else ("▼" if dt == "negative" else "—")
        delta_html = f'<div class="mc-delta {dt}">{arrow} {delta}</div>' if delta else ""
        cards_html += (
            f'<div class="metric-card">'
            f'{icon_html}'
            f'<div class="mc-label">{m["label"]}</div>'
            f'<div class="mc-value">{m["value"]}</div>'
            f'{delta_html}'
            f'</div>'
        )
    st.html(f'<div class="metric-row">{cards_html}</div>')


def content_card(title: str, subtitle: str = "", badge: str = "") -> None:
    badge_html = f'<span class="card-badge">{badge}</span>' if badge else ""
    subtitle_html = f'<div class="card-subtitle">{subtitle}</div>' if subtitle else ""
    st.html(
        f'<div class="card-header"><div>'
        f'<div class="card-title">{title}</div>{subtitle_html}'
        f'</div>{badge_html}</div>'
    )


def badge(text: str, style: str = "info") -> str:
    """Return inline badge HTML (use inside st.markdown)."""
    return f'<span class="badge {style}">{text}</span>'


def page_header(title: str, subtitle: str = "") -> None:
    sub_html = f'<div class="page-subtitle">{subtitle}</div>' if subtitle else ""
    st.html(
        f'<div class="page-header"><div class="page-title">{title}</div>{sub_html}</div>'
    )


def section_title(text: str) -> None:
    st.html(f'<div class="section-title">{text}</div>')


def empty_state(icon: str, title: str, desc: str) -> None:
    st.html(
        f'<div class="empty-state">'
        f'<div class="es-icon">{icon}</div>'
        f'<div class="es-title">{title}</div>'
        f'<div class="es-desc">{desc}</div>'
        f'</div>'
    )
