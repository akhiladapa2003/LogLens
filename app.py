"""Three-page LogLens dashboard."""
import html
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analytics import filter_rejections, processed_records, summary
from export_utils import dataframe_to_safe_csv
from generator import generate
from upload_workflow import process_uploaded_file, upload_digest


NAVIGATION = ["Overview", "Run Pipeline", "Data Quality"]
COLORS = {
    "midnight": "#10172A",
    "navy": "#17233B",
    "teal": "#14B8A6",
    "violet": "#8B5CF6",
    "gold": "#F4B860",
    "red": "#EF6461",
    "background": "#F1F5F9",
    "white": "#FFFFFF",
    "text": "#172033",
    "muted": "#64748B",
    "border": "#E2E8F0",
    "grid": "#E9EEF5",
    # Semantic aliases keep page behavior intact while sharing the palette.
    "blue": "#14B8A6",
    "blue_light": "#E8F8F5",
    "amber": "#F4B860",
    "purple": "#8B5CF6",
}
CATEGORY_COLORS = {
    "VALIDATION": COLORS["amber"],
    "MALFORMED": COLORS["red"],
    "DUPLICATE": COLORS["purple"],
}
CHART_COLORS = [COLORS["teal"], COLORS["violet"], COLORS["gold"], COLORS["red"], COLORS["navy"]]

px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = CHART_COLORS
dark_mode = bool(st.session_state.get("dark_mode", False))

st.set_page_config(
    page_title="LogLens | Log Analytics",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
      --ll-midnight: #10172A;
      --ll-navy: #17233B;
      --ll-teal: #14B8A6;
      --ll-violet: #8B5CF6;
      --ll-gold: #F4B860;
      --ll-red: #EF6461;
      --ll-text: #172033;
      --ll-muted: #64748B;
      --ll-border: #E2E8F0;
      --ll-surface: #FFFFFF;
      --ll-canvas: #F1F5F9;
    }
    html, body, [class*="css"] {
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
                   "Segoe UI", sans-serif;
      color: var(--ll-text);
    }
    .stApp { background: var(--ll-canvas); }
    [data-testid="stMainBlockContainer"] {
      max-width: 1480px;
      padding-top: 2.2rem;
      padding-bottom: 3rem;
    }
    h1, h2, h3 { color: var(--ll-text); letter-spacing: -0.025em; }
    h1 { font-size: 2rem !important; font-weight: 720 !important; margin-bottom: .25rem !important; }
    h2 { font-size: 1.3rem !important; font-weight: 680 !important; }
    h3 { font-size: 1.02rem !important; font-weight: 650 !important; }
    p, label, .stCaption { color: var(--ll-muted); }

    /* Sidebar */
    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {
      background: var(--ll-midnight);
      border-right: 1px solid #27324a;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] label { color: #c8d2e2 !important; }
    [data-testid="stSidebar"] [data-testid="stRadio"] > div { gap: .35rem; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label {
      border-radius: 10px;
      padding: .62rem .72rem;
      transition: background .15s ease;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background: #1a2540; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
      background: #202c46;
      color: #ffffff !important;
      box-shadow: inset 3px 0 0 var(--ll-teal);
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] input { accent-color: var(--ll-teal); }
    .sidebar-brand { display: flex; align-items: center; gap: .72rem; padding: .35rem .1rem 1.7rem; }
    .brand-mark {
      width: 2.55rem; height: 2.55rem; border-radius: .8rem;
      display: grid; place-items: center; color: #fff; font-weight: 800; font-size: 1.2rem;
      background: linear-gradient(145deg, #14B8A6, #0F766E);
      box-shadow: 0 8px 22px #07152b88;
    }
    .brand-name { color: white; font-size: 1.08rem; font-weight: 730; line-height: 1.1; }
    .brand-subtitle { color: #91a1bb; font-size: .68rem; letter-spacing: .105em; margin-top: .28rem; }
    .sidebar-section-label {
      color: #7789a6; font-size: .65rem; font-weight: 700;
      letter-spacing: .13em; margin: 0 0 .45rem .72rem;
    }
    .sidebar-footer {
      border-top: 1px solid #293752; margin-top: 2.2rem; padding: 1rem .25rem;
      color: #97a7bf; font-size: .75rem;
    }

    /* Page hierarchy */
    .page-heading { margin: 0 0 1.5rem; }
    .eyebrow {
      color: #0F766E; font-size: .68rem; font-weight: 750;
      letter-spacing: .14em; text-transform: uppercase; margin-bottom: .4rem;
    }
    .page-description { color: var(--ll-muted); font-size: .94rem; margin-top: .2rem; }
    .section-kicker {
      color: var(--ll-muted); font-size: .72rem; font-weight: 700;
      letter-spacing: .095em; text-transform: uppercase; margin: .5rem 0 .7rem;
    }
    .subtle-note { color: var(--ll-muted); font-size: .82rem; }

    /* Surfaces and metrics */
    div[data-testid="stMetric"] {
      min-height: 112px; background: var(--ll-surface); padding: 1.05rem 1.15rem;
      border: 1px solid var(--ll-border); border-radius: 14px;
      box-shadow: 0 5px 18px rgba(16, 23, 42, .055);
    }
    div[data-testid="stMetricLabel"] p { color: var(--ll-muted); font-size: .78rem; font-weight: 620; }
    div[data-testid="stMetricValue"] { color: var(--ll-navy); font-size: 1.75rem; font-weight: 730; }
    div[data-testid="stPlotlyChart"], div[data-testid="stDataFrame"] {
      background: var(--ll-surface); border: 1px solid var(--ll-border);
      border-radius: 14px; padding: .45rem; box-shadow: 0 3px 12px rgba(20, 33, 59, .025);
    }
    [data-testid="stFileUploader"] section {
      background: #fff; border: 1.5px dashed #8BCFC6; border-radius: 14px;
      padding: 1rem; box-shadow: 0 6px 20px rgba(16, 23, 42, .04);
    }
    [data-testid="stFileUploader"] section:hover { border-color: var(--ll-teal); background: #F7FFFD; }

    /* Controls */
    .stButton > button, .stDownloadButton > button {
      min-height: 2.7rem; border-radius: 9px; font-weight: 650;
      border: 1px solid #d5deea; transition: all .15s ease;
    }
    .stButton > button[kind="primary"] {
      background: #0F766E; border-color: #0F766E; color: #fff;
      box-shadow: 0 4px 12px rgba(20, 184, 166, .24);
    }
    .stButton > button[kind="primary"]:hover { background: #115E59; border-color: #115E59; }
    .stDownloadButton > button { background: #fff; color: var(--ll-navy); }
    [data-testid="stTextInput"] input, [data-testid="stSelectbox"] [data-baseweb="select"] > div {
      border-radius: 9px;
    }
    .status-banner {
      display: flex; align-items: center; gap: .65rem; padding: .85rem 1rem;
      border-radius: 11px; border: 1px solid; margin: .6rem 0 1rem; font-size: .88rem;
    }
    .status-success { color: #0F5F56; background: #E8F8F5; border-color: #9ADFD4; }
    .status-partial { color: #80520A; background: #FFF8E9; border-color: #F2D69B; }
    .status-failed { color: #9F3434; background: #FFF1F0; border-color: #F4C0BD; }
    .category-chip {
      background: #fff; border: 1px solid var(--ll-border); border-radius: 11px;
      padding: .85rem 1rem; min-height: 72px;
    }
    .category-chip-label { color: var(--ll-muted); font-size: .72rem; font-weight: 650; }
    .category-chip-value { color: var(--ll-navy); font-size: 1.35rem; font-weight: 730; margin-top: .18rem; }
    .latency-card {
      background: #fff; border: 1px solid var(--ll-border); border-radius: 12px;
      padding: .9rem 1rem; min-height: 74px;
    }
    .latency-label { color: var(--ll-muted); font-size: .73rem; font-weight: 650; }
    .latency-value { color: var(--ll-navy); font-size: 1.25rem; font-weight: 720; margin-top: .18rem; }
    @media (max-width: 900px) {
      [data-testid="stMainBlockContainer"] { padding: 1.35rem 1.1rem 2rem; }
      h1 { font-size: 1.65rem !important; }
      div[data-testid="stMetric"] { min-height: 100px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# The theme switch is intentionally presentation-only. It does not affect
# database contents, pipeline settings, or analytical calculations.
if dark_mode:
    st.markdown(
        """
        <style>
        :root {
          --ll-navy: #E7EDF8; --ll-text: #E7EDF8; --ll-muted: #A8B4C8;
          --ll-border: #33415B; --ll-surface: #1B2740; --ll-canvas: #10172A;
          --ll-grid: #34425B;
        }
        [data-testid="stFileUploader"] section,
        [data-testid="stFileUploader"] section:hover { background: #17233B; }
        .stDownloadButton > button { background: #1B2740; color: #E7EDF8; border-color: #33415B; }
        .stButton > button:not([kind="primary"]) { background: #1B2740; color: #E7EDF8; border-color: #33415B; }
        [data-testid="stTextInput"] input,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div {
          background: #1B2740; color: #E7EDF8; border-color: #465570;
        }
        div[data-testid="stMetricValue"], .category-chip-value, .latency-value { color: #E7EDF8; }
        .category-chip, .latency-card { background: #1B2740; }
        .status-success { color: #9DE7D9; background: #123B3B; border-color: #21645D; }
        .status-partial { color: #F5D28F; background: #3D321D; border-color: #6A542A; }
        .status-failed { color: #FFB4AE; background: #442629; border-color: #753B40; }
        [data-testid="stDataFrame"] { background: #1B2740; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_heading(eyebrow: str, title: str, description: str) -> None:
    st.markdown(
        f'<div class="page-heading"><div class="eyebrow">{html.escape(eyebrow)}</div>'
        f'<h1>{html.escape(title)}</h1><div class="page-description">{html.escape(description)}</div></div>',
        unsafe_allow_html=True,
    )


def section_heading(title: str, note: str | None = None) -> None:
    st.markdown(f'<div class="section-kicker">{html.escape(title)}</div>', unsafe_allow_html=True)
    if note:
        st.caption(note)


def style_figure(figure: go.Figure, height: int = 330) -> go.Figure:
    surface = "#1B2740" if dark_mode else COLORS["white"]
    text_color = "#A8B4C8" if dark_mode else COLORS["muted"]
    title_color = "#E7EDF8" if dark_mode else COLORS["navy"]
    grid_color = "#34425B" if dark_mode else COLORS["grid"]
    figure.update_layout(
        height=height,
        paper_bgcolor=surface,
        plot_bgcolor=surface,
        font={"family": "Inter, system-ui, sans-serif", "color": text_color, "size": 12},
        margin={"l": 18, "r": 18, "t": 54, "b": 28},
        title={"font": {"size": 15, "color": title_color}, "x": 0.03, "xanchor": "left"},
        legend={"bgcolor": "rgba(255,255,255,0)", "font": {"size": 11}},
        hoverlabel={"bgcolor": COLORS["midnight"], "font": {"color": COLORS["white"]}},
    )
    figure.update_xaxes(showgrid=True, gridcolor=grid_color, zeroline=False, linecolor=grid_color)
    figure.update_yaxes(showgrid=False, zeroline=False, linecolor=grid_color)
    return figure


def latency_card(label: str, value: float | None) -> str:
    display = "—" if value is None else f"{value:,.2f} ms"
    return (
        '<div class="latency-card">'
        f'<div class="latency-label">{html.escape(label)}</div>'
        f'<div class="latency-value">{display}</div></div>'
    )


def render_overview(db_path: str) -> None:
    page_heading("Workspace / Overview", "Log health at a glance", "Monitor ingestion quality, severity patterns, and service health.")
    data = summary(db_path)
    runs = data["runs"]
    input_rows = int(runs["input_count"].fillna(0).sum()) if not runs.empty else 0

    first_row = st.columns(3, gap="medium")
    first_row[0].metric("Input rows", f"{input_rows:,}", help="Cumulative input rows across recorded pipeline runs.")
    first_row[1].metric("Accepted unique", f"{data['total_records']:,}")
    first_row[2].metric("Invalid / rejected", f"{data['rejected_records']:,}")
    second_row = st.columns(3, gap="medium")
    second_row[0].metric("Duplicates", f"{data['duplicate_records']:,}")
    second_row[1].metric("Error rate", f"{data['error_rate']:.1f}%", help="ERROR and CRITICAL records divided by accepted unique records.")
    latency_value = data["average_latency"]
    second_row[2].metric("Average latency", f"{latency_value:,.1f} ms" if latency_value is not None else "—")

    if not data["total_records"]:
        st.info("No processed records yet. Open Run Pipeline to upload a file or generate the sample dataset.")
        return

    st.markdown("<div style='height:.4rem'></div>", unsafe_allow_html=True)
    left, right = st.columns([1, 1], gap="large")
    with left:
        section_heading("Severity distribution", "Accepted unique events by normalized severity.")
        severity_fig = px.pie(
            data["severity"], names="severity", values="count", hole=0.64,
            color="severity",
            color_discrete_map={
                "DEBUG": COLORS["navy"], "INFO": COLORS["teal"], "WARNING": COLORS["gold"],
                "ERROR": COLORS["red"], "CRITICAL": "#B4233C",
            },
        )
        severity_fig.update_traces(textposition="outside", textinfo="percent", textfont={"color": "#A8B4C8" if dark_mode else COLORS["muted"], "size": 11})
        severity_fig.update_layout(title="Severity mix", legend={"orientation": "h", "y": -0.12, "x": 0.02})
        st.plotly_chart(style_figure(severity_fig, 340), use_container_width=True, config={"displayModeBar": False})

    with right:
        section_heading("Service-level error analysis", "ERROR and CRITICAL events grouped by service.")
        service_fig = px.bar(
            data["services"].sort_values("errors"), x="errors", y="service_name", orientation="h",
            color="error_rate", color_continuous_scale=["#D7F4EF", COLORS["teal"], COLORS["navy"]],
            hover_data={"count": True, "error_rate": ":.1f"},
            labels={"errors": "Error events", "service_name": "Service", "error_rate": "Error rate (%)"},
        )
        service_fig.update_layout(coloraxis_colorbar={"title": "Rate", "ticksuffix": "%", "thickness": 10})
        st.plotly_chart(style_figure(service_fig, 340), use_container_width=True, config={"displayModeBar": False})

    section_heading("Error trends over time", "Hourly event-time counts; late events remain in their original hour.")
    trends = data["trends"]
    trend_fig = go.Figure()
    trend_fig.add_trace(go.Scatter(
        x=trends["hour"], y=trends["count"], mode="lines+markers", name="All events",
        line={"color": COLORS["violet"], "width": 2.5}, marker={"size": 6},
    ))
    trend_fig.add_trace(go.Scatter(
        x=trends["hour"], y=trends["errors"], mode="lines+markers", name="Error events",
        line={"color": COLORS["red"], "width": 2.2}, marker={"size": 6},
    ))
    trend_fig.update_layout(title="Hourly event volume", xaxis_title="UTC hour", yaxis_title="Records", legend={"orientation": "h", "y": 1.12, "x": 0.02})
    st.plotly_chart(style_figure(trend_fig, 360), use_container_width=True, config={"displayModeBar": False})

    section_heading("Latency summary", f"Based on {data['latency_count']:,} records with valid latency. Percentiles use Pandas linear interpolation.")
    latency_columns = st.columns(5, gap="small")
    latency_values = [
        ("Median", data["median_latency"]), ("p95", data["p95_latency"]),
        ("p99", data["p99_latency"]), ("Minimum", data["min_latency"]),
        ("Maximum", data["max_latency"]),
    ]
    for column, (label, value) in zip(latency_columns, latency_values):
        with column:
            st.markdown(latency_card(label, value), unsafe_allow_html=True)

    st.markdown("<div style='height:.7rem'></div>", unsafe_allow_html=True)
    section_heading("Recent pipeline runs", "Latest executions and their reconciliation counts.")
    recent_columns = ["run_id", "start_time", "source_file", "status", "input_count", "accepted_count", "rejected_count", "duplicate_count"]
    st.dataframe(runs[recent_columns].head(6), hide_index=True, use_container_width=True)


def render_pipeline(db_path: str) -> None:
    page_heading("Workspace / Ingestion", "Run Pipeline", "Upload a log file, validate every source row, and review its outcome.")
    st.markdown("<div class='section-kicker'>Upload log data</div>", unsafe_allow_html=True)
    st.caption("Choose a JSON, JSONL, NDJSON, CSV, TXT, or LOG file. Files are processed locally into the LogLens SQLite database.")
    uploaded = st.file_uploader(
        "Drop a file here or browse", type=["json", "jsonl", "ndjson", "csv", "txt", "log"],
        help="Supported formats: JSON, JSONL, NDJSON, CSV, TXT, and LOG.",
    )
    upload_hash = upload_digest(uploaded.getvalue()) if uploaded else None

    processed_upload_hashes = set(st.session_state.get("processed_upload_hashes", ()))
    previous_hash = st.session_state.get("processed_upload_hash")
    if previous_hash:
        processed_upload_hashes.add(previous_hash)
    already_processed = bool(upload_hash and upload_hash in processed_upload_hashes)

    if uploaded:
        file_columns = st.columns([2, 1, 1], gap="medium")
        with file_columns[0]:
            st.markdown("<div class='section-kicker'>Selected file</div>", unsafe_allow_html=True)
            st.write(uploaded.name)
        with file_columns[1]:
            st.markdown("<div class='section-kicker'>File size</div>", unsafe_allow_html=True)
            st.write(f"{uploaded.size / 1024:,.1f} KB" if uploaded.size >= 1024 else f"{uploaded.size:,} bytes")
        with file_columns[2]:
            st.markdown("<div class='section-kicker'>File type</div>", unsafe_allow_html=True)
            st.write(Path(uploaded.name).suffix.upper().lstrip(".") or "Unknown")

    if already_processed:
        st.info("This upload has already run in this session. Remove and reselect it to run again.")

    generate_col, run_col, _ = st.columns([1, 1.2, 2.8], gap="medium")
    with generate_col:
        if st.button("Generate sample dataset", type="secondary", use_container_width=True):
            generate()
            st.success("Created data/sample/sample.jsonl")
    with run_col:
        run_clicked = st.button(
            "Run Pipeline", type="primary", use_container_width=True,
            disabled=uploaded is None or already_processed,
        )

    if run_clicked:
        with st.spinner("Processing file and reconciling source rows…"):
            result, upload_hash, skipped = process_uploaded_file(uploaded, db_path, processed_upload_hashes)
        if skipped:
            st.info("This upload has already run in this session.")
        else:
            st.session_state["last_run"] = result
            st.session_state["processed_upload_hashes"] = processed_upload_hashes

    if st.session_state.get("last_run"):
        result = st.session_state.last_run
        status = result["status"]
        status_class = "status-failed" if status == "FAILED" else "status-partial" if status == "PARTIAL_SUCCESS" else "status-success"
        status_symbol = "!" if status == "FAILED" else "✓"
        st.markdown(
            f'<div class="status-banner {status_class}"><strong>{status_symbol}</strong>'
            f'<span><b>{html.escape(status)}</b> · {html.escape(result["source_file"])}</span></div>',
            unsafe_allow_html=True,
        )
        result_columns = st.columns(4, gap="medium")
        result_columns[0].metric("Input rows", f"{result['input_count']:,}")
        result_columns[1].metric("Accepted", f"{result['accepted_count']:,}")
        result_columns[2].metric("Rejected", f"{result['rejected_count']:,}")
        result_columns[3].metric("Duplicates", f"{result['duplicate_count']:,}")
        metadata_columns = st.columns([2, 1, 1], gap="medium")
        with metadata_columns[0]:
            st.caption("RUN ID")
            st.code(result["run_id"], language=None)
        with metadata_columns[1]:
            st.caption("EXECUTION TIME")
            st.write(f"{result['duration_seconds']:,.3f} sec")
        with metadata_columns[2]:
            st.caption("RECONCILIATION")
            if result["reconciliation_ok"]:
                st.success("Passed")
            else:
                st.error("Failed")
        if result.get("failure_reason"):
            st.error(result["failure_reason"])
        with st.expander("Run details"):
            st.json(result)

    st.markdown("<div style='height:.7rem'></div>", unsafe_allow_html=True)
    section_heading("Run history", "Recent and previous pipeline executions.")
    data = summary(db_path)
    st.dataframe(data["runs"], hide_index=True, use_container_width=True)
    st.download_button(
        "Download run history CSV", dataframe_to_safe_csv(data["runs"]),
        "run_history.csv", "text/csv",
    )


def render_data_quality(db_path: str) -> None:
    page_heading("Workspace / Data Quality", "Quality & quarantine", "Investigate rejected events, duplicates, and observed schema changes.")
    data = summary(db_path)
    all_rejected = data["rejections"]
    invalid_count = int((all_rejected["category"] != "DUPLICATE").sum()) if not all_rejected.empty else 0
    duplicate_count = int((all_rejected["category"] == "DUPLICATE").sum()) if not all_rejected.empty else 0

    metrics = st.columns(3, gap="medium")
    metrics[0].metric("Quarantined rows", f"{len(all_rejected):,}")
    metrics[1].metric("Invalid / malformed", f"{invalid_count:,}")
    metrics[2].metric("Duplicate events", f"{duplicate_count:,}")

    if data["total_records"]:
        section_heading("Accepted records", "Export normalized, accepted events from the local SQLite database.")
        accepted_csv, accepted_json, _ = st.columns([1, 1, 3], gap="small")
        with accepted_csv:
            st.download_button(
                "Export accepted CSV",
                lambda: dataframe_to_safe_csv(processed_records(db_path)).encode("utf-8-sig"),
                "accepted_records.csv", "text/csv", use_container_width=True,
            )
        with accepted_json:
            st.download_button(
                "Export accepted JSON",
                lambda: processed_records(db_path).to_json(orient="records", indent=2).encode("utf-8"),
                "accepted_records.json", "application/json", use_container_width=True,
            )

    if all_rejected.empty:
        st.info("No rejected records yet. Run a file to see validation results.")
    else:
        section_heading("Rejection categories", "Use category counts to focus the review.")
        category_counts = all_rejected.groupby("category").size().rename("count").reset_index()
        chips = st.columns(max(1, len(category_counts)), gap="small")
        for column, row in zip(chips, category_counts.itertuples(index=False)):
            with column:
                count_color = CATEGORY_COLORS.get(row.category, COLORS["blue"])
                st.markdown(
                    f'<div class="category-chip"><div class="category-chip-label">'
                    f'<span style="color:{count_color}">●</span> {html.escape(str(row.category))}'
                    f'</div><div class="category-chip-value">{int(row.count):,}</div></div>',
                    unsafe_allow_html=True,
                )

        category_chart = px.bar(
            category_counts.sort_values("count"), x="count", y="category", orientation="h",
            color="category", color_discrete_map=CATEGORY_COLORS,
            labels={"count": "Records", "category": "Category"},
        )
        category_chart.update_layout(title="Quarantine by category", showlegend=False)
        st.plotly_chart(style_figure(category_chart, 260), use_container_width=True, config={"displayModeBar": False})

        controls = st.columns([1, 2], gap="medium")
        with controls[0]:
            category_filter = st.selectbox("Category", ["All"] + sorted(all_rejected["category"].dropna().unique().tolist()))
        with controls[1]:
            query = st.text_input("Search records", placeholder="Reason, source filename, category, or code")
        rejected = all_rejected
        if category_filter != "All":
            rejected = rejected[rejected["category"] == category_filter]
        rejected, search_error = filter_rejections(rejected, query)

        if search_error:
            st.error(f"{search_error}. Escape special characters such as (, [, or * when searching for them literally.")
        else:
            section_heading("Quarantined records", f"Showing {len(rejected):,} matching rows. Exports include all columns for the displayed filter.")
            st.dataframe(
                rejected, hide_index=True, use_container_width=True,
                column_config={
                    "category": st.column_config.TextColumn("Category", help="VALIDATION, MALFORMED, or DUPLICATE"),
                    "rejection_reason": st.column_config.TextColumn("Reason", width="large"),
                    "raw_payload": st.column_config.TextColumn("Raw payload", width="medium"),
                    "rejection_id": st.column_config.NumberColumn("ID", format="%d"),
                },
            )
            csv_col, json_col, _ = st.columns([1, 1, 3], gap="small")
            with csv_col:
                st.download_button(
                    "Export filtered CSV", dataframe_to_safe_csv(rejected),
                    "rejected_records.csv", "text/csv", use_container_width=True,
                )
            with json_col:
                st.download_button(
                    "Export filtered JSON", rejected.to_json(orient="records", indent=2),
                    "rejected_records.json", "application/json", use_container_width=True,
                )

    st.markdown("<div style='height:.7rem'></div>", unsafe_allow_html=True)
    section_heading("Schema observations", "Source shape changes recorded during ingestion.")
    observations = data["observations"]
    if observations.empty:
        st.info("No schema drift or missing-field observations recorded.")
    else:
        incompatible = observations[observations["observation"].str.startswith("INCOMPATIBLE")]
        additive = observations[observations["observation"].str.startswith("ADDITIVE")]
        warning_col, additive_col = st.columns(2, gap="medium")
        warning_col.metric("Missing required fields", f"{len(incompatible):,}")
        additive_col.metric("Additive field observations", f"{len(additive):,}")
        if len(incompatible):
            st.warning(f"{len(incompatible):,} incompatible required-field observations need review.")
        st.dataframe(observations, hide_index=True, use_container_width=True)


st.sidebar.markdown(
    '<div class="sidebar-brand"><div class="brand-mark">L</div><div>'
    '<div class="brand-name">LogLens</div><div class="brand-subtitle">LOG OBSERVABILITY</div>'
    '</div></div><div class="sidebar-section-label">WORKSPACE</div>',
    unsafe_allow_html=True,
)
st.sidebar.toggle("Dark mode", key="dark_mode", help="Switch the dashboard between light and dark themes.")
page = st.sidebar.radio(
    "Workspace",
    NAVIGATION,
    format_func=lambda item: {
        "Overview": "▦  Overview",
        "Run Pipeline": "↥  Run Pipeline",
        "Data Quality": "◉  Data Quality",
    }[item],
    label_visibility="collapsed",
)
st.sidebar.markdown(
    '<div class="sidebar-footer">LOCAL WORKSPACE<br><strong>SQLite analytics</strong></div>',
    unsafe_allow_html=True,
)
database_path = "data/loglens.db"

if page == "Run Pipeline":
    render_pipeline(database_path)
elif page == "Data Quality":
    render_data_quality(database_path)
else:
    render_overview(database_path)
