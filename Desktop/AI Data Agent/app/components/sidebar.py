import streamlit as st
from app.components.icons import icon as svg_icon

NAV_ITEMS = [
    ("📊", "Overview"),
    ("🏠", "Dashboard"),
    ("🔍", "Data Explorer"),
    ("🤖", "AI Analyst"),
    ("📋", "Reports"),
    ("⚙️", "Settings"),
]

NAV_LABELS = [f"  {icon}  {label}" for icon, label in NAV_ITEMS]
NAV_KEYS   = [label for _, label in NAV_ITEMS]


def render_sidebar() -> str:
    """Render the sidebar and return the selected page name."""
    with st.sidebar:
        # ── Logo / branding ──────────────────────────────────────────
        st.markdown("""
        <div style="padding:20px 14px 16px;border-bottom:1px solid rgba(255,255,255,0.07);">
            <div style="display:flex;align-items:center;gap:10px;">
                <div style="width:34px;height:34px;background:linear-gradient(135deg,#2563eb,#7c3aed);
                            border-radius:8px;display:flex;align-items:center;justify-content:center;
                            font-size:18px;flex-shrink:0;">📊</div>
                <div>
                    <div style="color:#e2eaf2;font-weight:700;font-size:14px;line-height:1.2;">DataAgent</div>
                    <div style="color:#506070;font-size:11px;font-weight:500;">AI Analytics</div>
                </div>
            </div>
        </div>""", unsafe_allow_html=True)

        st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)

        # ── Navigation ───────────────────────────────────────────────
        st.markdown(
            '<div style="padding:0 6px 4px;color:#3d5060;font-size:10.5px;'
            'font-weight:700;letter-spacing:0.1em;text-transform:uppercase;">Navigation</div>',
            unsafe_allow_html=True,
        )

        default_idx = NAV_KEYS.index(st.session_state.get("page", "Overview"))
        selected_label = st.radio(
            "nav",
            options=NAV_LABELS,
            index=default_idx,
            label_visibility="collapsed",
        )
        page = NAV_KEYS[NAV_LABELS.index(selected_label)]
        st.session_state["page"] = page

        # ── Divider ──────────────────────────────────────────────────
        st.markdown('<hr style="border-color:rgba(255,255,255,0.07);margin:12px 0"/>', unsafe_allow_html=True)

        # ── Upload ───────────────────────────────────────────────────
        st.markdown(
            '<div style="padding:0 6px 6px;color:#3d5060;font-size:10.5px;'
            'font-weight:700;letter-spacing:0.1em;text-transform:uppercase;">Data Source</div>',
            unsafe_allow_html=True,
        )

        uploaded = st.file_uploader(
            "Upload file",
            type=["csv", "xlsx", "xls", "parquet", "json"],
            label_visibility="collapsed",
        )

        if uploaded:
            _handle_upload(uploaded)

        df = st.session_state.get("df")
        if df is not None:
            lr = st.session_state.get("load_result")
            filename = getattr(lr, "filename", "") if lr else ""
            fname_html = (
                f'<div style="color:#3d5060;font-size:10px;margin-top:1px;overflow:hidden;'
                f'text-overflow:ellipsis;white-space:nowrap;" title="{filename}">{filename}</div>'
                if filename else ""
            )
            st.html(
                f'<div style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.2);'
                f'border-radius:6px;padding:8px 10px;margin-top:4px;">'
                f'<div style="color:#34d399;font-size:11px;font-weight:600;">✓ Dataset loaded</div>'
                f'<div style="color:#506070;font-size:11px;margin-top:2px;">'
                f'{len(df):,} rows · {len(df.columns)} cols</div>'
                f'{fname_html}</div>'
            )

        # ── Dashboard Filters (only on Dashboard page with data) ──────
        if page == "Dashboard" and df is not None:
            st.markdown(
                '<hr style="border-color:rgba(255,255,255,0.07);margin:14px 0 0"/>',
                unsafe_allow_html=True,
            )
            _render_filters(df)

        # ── Footer ───────────────────────────────────────────────────
        st.markdown('<div style="height:48px"></div>', unsafe_allow_html=True)
        st.markdown("""
        <div style="border-top:1px solid rgba(255,255,255,0.06);padding:12px 14px 8px;">
            <div style="color:#2d4050;font-size:11px;font-weight:500;">v0.1.0 · DataAgent</div>
        </div>""", unsafe_allow_html=True)

    return page


# ── Filter panel ─────────────────────────────────────────────────────────────

def _render_filters(df) -> None:
    """Render the Filters pane inside the sidebar (Dashboard page only)."""
    from app.analytics.column_intelligence import analyze
    from app.services.filter_service import (
        build_options, active_count, all_filter_keys,
        key_date, key_cat, key_num,
    )

    # ── Get or compute column intel ──────────────────────────────────
    intel_key = f"_intel_{id(df)}"
    if intel_key not in st.session_state:
        with st.spinner("Analysing columns…"):
            st.session_state[intel_key] = analyze(df)
    intel = st.session_state[intel_key]

    opts = build_options(df, intel)
    n_active = active_count(st.session_state, opts)

    # ── Section header + Reset button ────────────────────────────────
    label_html = (
        '<span style="color:#3d5060;font-size:10.5px;font-weight:700;'
        'letter-spacing:0.1em;text-transform:uppercase;">Filters</span>'
    )
    if n_active:
        label_html += (
            f'<span style="background:#2563eb;color:#fff;font-size:10px;'
            f'font-weight:700;border-radius:9px;padding:1px 6px;margin-left:6px;">'
            f'{n_active}</span>'
        )

    header_col, reset_col = st.columns([3, 1])
    with header_col:
        st.markdown(
            f'<div style="padding:6px 0 4px;">{label_html}</div>',
            unsafe_allow_html=True,
        )
    with reset_col:
        if st.button(
            "↺",
            key="_filter_reset_btn",
            help="Reset all filters",
            use_container_width=True,
        ):
            for k in all_filter_keys(st.session_state):
                del st.session_state[k]
            st.rerun()

    # ── No filterable columns ────────────────────────────────────────
    if not opts["date"] and not opts["categoricals"] and not opts["numerics"]:
        st.markdown(
            '<div style="color:#3d5060;font-size:11px;padding:4px 0 8px;">'
            'No filterable columns detected.</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown('<div style="height:2px"></div>', unsafe_allow_html=True)

    # ── Date range ───────────────────────────────────────────────────
    if opts["date"]:
        info = opts["date"]
        _filter_label(svg_icon("calendar", 14, "#8099ae"), info["col"])
        st.date_input(
            info["col"],
            value=(info["min"], info["max"]),
            min_value=info["min"],
            max_value=info["max"],
            key=key_date(),
            label_visibility="collapsed",
        )
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)

    # ── Categorical multiselects ──────────────────────────────────────
    for info in opts["categoricals"]:
        col  = info["col"]
        vals = info["values"]
        _filter_label(svg_icon("tag", 14, "#8099ae"), col, count=len(vals))
        st.multiselect(
            col,
            options=vals,
            default=[],
            key=key_cat(col),
            label_visibility="collapsed",
            placeholder=f"All ({len(vals)})",
        )
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)

    # ── Numeric sliders ──────────────────────────────────────────────
    for info in opts["numerics"]:
        col  = info["col"]
        lo   = info["min"]
        hi   = info["max"]
        step = info["step"]
        _filter_label(svg_icon("sliders-horizontal", 14, "#8099ae"), col)
        k = key_num(col)
        # Default to full range when not yet set or after reset
        default = st.session_state.get(k, (lo, hi))
        if not isinstance(default, (tuple, list)) or len(default) != 2:
            default = (lo, hi)
        st.slider(
            col,
            min_value=lo,
            max_value=hi,
            value=(float(default[0]), float(default[1])),
            step=step,
            key=k,
            label_visibility="collapsed",
            format=_slider_format(lo, hi),
        )
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)


def _filter_label(icon: str, col: str, count: int | None = None) -> None:
    count_html = (
        f'<span style="color:#3d5060;font-size:10px;"> ({count})</span>'
        if count else ""
    )
    label = col.replace("_", " ").replace("-", " ").title()
    st.markdown(
        f'<div style="color:#8099ae;font-size:11px;font-weight:600;'
        f'margin-bottom:2px;">{icon} {label}{count_html}</div>',
        unsafe_allow_html=True,
    )


def _slider_format(lo: float, hi: float) -> str:
    """Pick a printf-style format for the slider based on the value range."""
    if hi >= 10_000:
        return "%,.0f"
    if hi >= 100:
        return "%.1f"
    return "%.2f"


# ── Upload handler ────────────────────────────────────────────────────────────

def _handle_upload(uploaded_file) -> None:
    from app.services.data_loader import load_from_upload, _FakeUpload
    key = f"_uploaded_{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.get("_upload_key") == key:
        return
    try:
        raw_bytes: bytes = uploaded_file.read()
        fake = _FakeUpload(uploaded_file.name, uploaded_file.size, raw_bytes)
        lr = load_from_upload(fake)

        st.session_state["_raw_bytes"]   = raw_bytes
        st.session_state["df"]           = lr.df
        st.session_state["load_result"]  = lr
        st.session_state["_upload_key"]  = key
        st.session_state["_upload_name"] = uploaded_file.name

        # Invalidate all caches that depend on the previous file
        for k in list(st.session_state.keys()):
            if k.startswith(("_profile_", "_intel_", "_filter_")):
                del st.session_state[k]

        st.rerun()
    except Exception as exc:
        st.error(str(exc))
