"""Streamlit entry point for the Bank Compliance Analysis prototype."""

from __future__ import annotations

from html import escape
import pandas as pd
import plotly.express as px
import streamlit as st

from compliance_engine import FINDING_COLUMNS, RULES, RuleResult, run_rules
from data_utils import EXPECTED_SHEETS, load_data_files, load_parameters, schema_issues
from reporting import (
    apply_finding_filters,
    build_excel_report,
    compliance_review_summary,
    report_summary,
)


st.set_page_config(
    page_title="Bank Compliance Analysis",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

NAVIGATION = [
    "Dashboard", "Data Import / Data Overview", "Compliance Findings",
    "Compliance Rules", "Reports", "AI Copilot", "Settings / Parameters",
]
SEVERITY_COLOURS = {
    "Critical": "#991b1b", "High": "#dc2626", "Medium": "#b45309",
    "Low": "#2563eb", "Unspecified": "#64748b",
}
IMPORT_PIPELINE_VERSION = "2026-08-12.4"
FINDING_LABELS = {
    "finding_id": "Finding ID", "rule_id": "Rule ID", "rule_name": "Rule Name",
    "entity_type": "Entity Type", "entity_id": "Entity ID", "customer_id": "Customer ID",
    "account_id": "Account ID", "branch": "Branch", "severity": "Severity", "status": "Status",
    "expected_value": "Expected Value", "actual_value": "Actual Value", "evidence": "Evidence",
    "recommended_action": "Recommended Action", "detected_at": "Detection Date",
    "occurrence_date": "Occurrence Date",
}


def inject_styles() -> None:
    st.markdown("""
    <style>
    :root { color-scheme: light; }
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] { background: #f5f7fa; color: #183b56; }
    [data-testid="stHeader"], .stAppHeader { background: #f5f7fa; }
    [data-testid="stAppDeployButton"] { display: none; }
    [data-testid="stToolbar"] { display:flex !important; visibility:visible !important; }
    [data-testid="stSidebarCollapseButton"], [data-testid="stExpandSidebarButton"] {
        display:flex !important;
        visibility:visible !important;
        opacity:1 !important;
        z-index:999999 !important;
    }
    [data-testid="stSidebarCollapseButton"] button {
        color:#edf4fb !important;
        background:#173650 !important;
        border:1px solid #55738b !important;
        border-radius:7px !important;
    }
    [data-testid="stExpandSidebarButton"] button {
        color:#173b56 !important;
        background:#ffffff !important;
        border:1px solid #cbd8e2 !important;
        border-radius:7px !important;
        box-shadow:0 2px 8px rgba(15,39,64,.12) !important;
    }
    [data-testid="stSidebarCollapseButton"] button:hover,
    [data-testid="stExpandSidebarButton"] button:hover { border-color:#2b6f9f !important; }
    [data-testid="stMainBlockContainer"] { padding-top: 3.5rem; padding-bottom: 3rem; }
    [data-testid="stSidebarContent"] { padding-top: 2.25rem; }
    [data-testid="stMain"] p, [data-testid="stMain"] li,
    [data-testid="stMain"] label, [data-testid="stMain"] h1,
    [data-testid="stMain"] h2, [data-testid="stMain"] h3,
    [data-testid="stMain"] h4 { color: #183b56; }
    [data-testid="stSidebar"] { background: #0d2238; }
    [data-testid="stSidebar"] * { color: #edf4fb; }
    [data-testid="stSidebar"] input { color: #17283a; }
    [data-testid="stSidebar"] [data-baseweb="select"] * { color: #17283a; }
    [data-testid="stSidebar"] .stButton button {
        background: #173650;
        border: 1px solid #55738b;
        color: #f4f8fb !important;
    }
    [data-testid="stSidebar"] .stButton button * { color: #f4f8fb !important; }
    [data-testid="stSidebar"] .stButton button:hover { background: #204763; border-color: #7d98ad; }
    [data-testid="stMain"] [data-testid="stFileUploaderDropzone"] {
        background: #ffffff;
        border: 2px dashed #7b9bb3;
        border-radius: 12px;
        min-height: 132px;
        padding: 1.25rem 1.5rem;
        box-shadow: 0 3px 12px rgba(15,39,64,.04);
    }
    [data-testid="stMain"] [data-testid="stFileUploaderDropzone"] button {
        background: #1f628f !important;
        border: 1px solid #1f628f !important;
        color: white !important;
        font-weight: 700;
        min-width: 135px;
    }
    [data-testid="stMain"] [data-testid="stFileUploaderDropzone"] button * { color: white !important; }
    [data-testid="stMain"] [data-testid="stFileUploaderDropzone"] small,
    [data-testid="stMain"] [data-testid="stFileUploaderDropzoneInstructions"] * { color: #526b7f !important; }
    .app-title { color:#102a43; letter-spacing:-.02em; margin-bottom:.1rem; }
    .eyebrow { color:#587086; text-transform:uppercase; letter-spacing:.12em; font-size:.72rem; font-weight:700; }
    .kpi { background:white; border:1px solid #dde5ed; border-top:3px solid var(--accent,#3f789e); border-radius:10px; padding:16px 18px 15px; min-height:110px; box-shadow:0 3px 12px rgba(15,39,64,.05); }
    .kpi-label { color:#63778b; font-size:.78rem; font-weight:650; text-transform:uppercase; letter-spacing:.04em; }
    .kpi-value { color:#102a43; font-size:1.75rem; font-weight:720; margin-top:.35rem; }
    .notice { background:#eaf2f9; border-left:4px solid #2b6f9f; border-radius:6px; padding:1rem 1.2rem; color:#183b56; line-height:1.55; overflow-wrap:anywhere; }
    .notice, .notice * { color:#183b56 !important; }
    .entity-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.65rem; margin:.7rem 0 1.8rem; }
    .entity-chip { background:#fff; border:1px solid #dce6ee; border-radius:8px; padding:.72rem .85rem; color:#23445e; font-weight:650; }
    .entity-chip:before { content:'✓'; color:#2b7a62; margin-right:.55rem; }
    .step-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.8rem; margin-top:.7rem; }
    .step-card { background:#fff; border:1px solid #dce6ee; border-radius:9px; padding:1rem 1.1rem; color:#526b7f; line-height:1.45; }
    .step-card b { color:#173b56; display:block; margin-bottom:.3rem; }
    .source-summary { background:#142f48; border:1px solid #405f78; border-radius:8px; padding:.75rem .85rem; margin:.55rem 0 .65rem; line-height:1.4; }
    .source-summary, .source-summary * { color:#dce8f1 !important; }
    .source-summary b { font-size:1.1rem; }
    .chart-placeholder { height:310px; background:#fff; border:1px solid #e1e7ed; border-radius:8px; padding:1rem; display:flex; flex-direction:column; justify-content:center; align-items:center; text-align:center; color:#526b7f; box-shadow:0 2px 8px rgba(15,39,64,.04); }
    .chart-placeholder b { color:#173b56; font-size:1rem; margin-bottom:.7rem; }
    .chart-placeholder span { max-width:430px; line-height:1.5; }
    .summary-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.8rem; margin:.8rem 0 1.5rem; }
    .summary-card { background:#fff; border:1px solid #dce6ee; border-radius:10px; padding:1rem 1.1rem; min-height:180px; box-shadow:0 2px 8px rgba(15,39,64,.04); }
    .summary-card.attention { border-top:3px solid #b45309; }
    .summary-card.positive { border-top:3px solid #2f7d5a; }
    .summary-card.actions { border-top:3px solid #2b6f9f; }
    .summary-title { color:#173b56; font-weight:750; font-size:1rem; margin-bottom:.65rem; }
    .summary-item { color:#526b7f; line-height:1.45; margin:.48rem 0; padding-left:1rem; position:relative; }
    .summary-item:before { content:'•'; position:absolute; left:0; color:#6b8294; font-weight:800; }
    .quality-ok { display:inline-flex; align-items:center; gap:.5rem; margin:.8rem 0 .2rem; padding:.45rem .7rem; background:#edf7f2; border:1px solid #b9ddcc; border-radius:7px; color:#236149; font-size:.86rem; font-weight:650; }
    @media (max-width: 900px) { .entity-grid { grid-template-columns:repeat(2,1fr); } .step-grid, .summary-grid { grid-template-columns:1fr; } }
    div[data-testid="stPlotlyChart"], div[data-testid="stDataFrame"] { background:white; border:1px solid #e1e7ed; border-radius:8px; padding:.35rem; }
    </style>
    """, unsafe_allow_html=True)


def page_header(title: str, subtitle: str) -> None:
    st.markdown('<div class="eyebrow">Risk & Compliance</div>', unsafe_allow_html=True)
    st.markdown(f'<h1 class="app-title">{title}</h1>', unsafe_allow_html=True)
    st.caption(subtitle)


def kpi_cards(values: list[tuple[str, str] | tuple[str, str, str]]) -> None:
    columns = st.columns(len(values))
    for column, item in zip(columns, values):
        label, value = item[:2]
        accent = item[2] if len(item) == 3 else "#3f789e"
        column.markdown(
            f'<div class="kpi" style="--accent:{accent}"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>',
            unsafe_allow_html=True,
        )


@st.cache_data(show_spinner="Reading and analysing uploaded files…")
def analyse_files(files: tuple[tuple[str, bytes], ...], pipeline_version: str) -> tuple[dict[str, pd.DataFrame], list[str], dict, list[str], pd.DataFrame, list[RuleResult]]:
    del pipeline_version  # Included in the cache key when import behaviour changes.
    sheets, warnings = load_data_files(list(files))
    parameters, parameter_warnings = load_parameters(sheets)
    findings, results = run_rules(sheets, parameters)
    return sheets, warnings, parameters, parameter_warnings, findings, results


def sidebar_filters(findings: pd.DataFrame) -> dict:
    st.sidebar.markdown("---")
    st.sidebar.markdown("#### Global filters")
    if st.sidebar.button("Reset filters", width="stretch"):
        for key in list(st.session_state):
            if key.startswith("filter_"):
                del st.session_state[key]
        st.rerun()
    filters: dict = {}
    if findings.empty:
        st.sidebar.caption("Filters appear when findings are available.")
        return filters
    if "occurrence_date" in findings and pd.to_datetime(findings["occurrence_date"], errors="coerce").nunique() > 1:
        dates = pd.to_datetime(findings["occurrence_date"], errors="coerce").dropna().dt.date
        selected = st.sidebar.date_input("Occurrence date", value=(dates.min(), dates.max()), key="filter_date")
        if isinstance(selected, tuple) and len(selected) == 2:
            filters["date_range"] = selected
            filters["include_undated"] = st.sidebar.checkbox(
                "Include findings without occurrence date",
                value=True,
                key="filter_include_undated",
                help="Minor, duplicate-email, and current-state reviews do not have a source event date.",
            )
    labels = {
        "branch": "Branch", "rule_name": "Compliance rule", "severity": "Severity",
        "status": "Finding status", "entity_type": "Entity type",
    }
    for field, label in labels.items():
        if field in findings and findings[field].notna().any():
            options = sorted(findings[field].dropna().astype(str).unique())
            filters[field] = st.sidebar.multiselect(label, options, key=f"filter_{field}")
    if any(field in findings and findings[field].notna().any() for field in ("customer_id", "account_id")):
        filters["search"] = st.sidebar.text_input("Customer / Account search", key="filter_search")
    return filters


def style_figure(fig, height: int = 310) -> None:
    """Apply a compact, consistent BI-dashboard treatment to Plotly figures."""
    fig.update_layout(
        height=height,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(family="Arial, sans-serif", color="#526b7f", size=12),
        title_font=dict(color="#173b56", size=16),
        margin=dict(l=12, r=18, t=52, b=28),
        hoverlabel=dict(bgcolor="#173b56", font_color="#ffffff"),
    )
    fig.update_xaxes(title=None, gridcolor="#e9eff4", zeroline=False, automargin=True)
    fig.update_yaxes(title=None, gridcolor="#e9eff4", zeroline=False, automargin=True)


def chart_block(findings: pd.DataFrame, rule_results: list[RuleResult]) -> None:
    if findings.empty:
        st.info("No findings match the active filters.")
        return
    left, right = st.columns(2)
    by_rule = findings["rule_name"].value_counts().rename_axis("Rule").reset_index(name="Findings")
    fig = px.bar(by_rule.sort_values("Findings"), x="Findings", y="Rule", orientation="h",
                 title="Compliance Findings by Rule", text="Findings", color_discrete_sequence=["#28678f"])
    style_figure(fig)
    fig.update_traces(textposition="outside", cliponaxis=False, hovertemplate="%{y}<br>%{x:,} findings<extra></extra>")
    fig.update_layout(showlegend=False)
    left.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    by_severity = findings["severity"].value_counts().rename_axis("Severity").reset_index(name="Findings")
    configured_severity = findings["severity"].fillna("Unspecified").ne("Unspecified").any()
    if configured_severity:
        fig = px.pie(by_severity, values="Findings", names="Severity", hole=.62, title="Findings by Severity",
                     color="Severity", color_discrete_map=SEVERITY_COLOURS)
        style_figure(fig)
        fig.update_traces(textinfo="percent", hovertemplate="%{label}<br>%{value:,} findings (%{percent})<extra></extra>")
        fig.add_annotation(text=f"<b>{len(findings):,}</b><br>Findings", showarrow=False,
                           font=dict(size=15, color="#173b56"))
        fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-.12, xanchor="center", x=.5))
        right.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    else:
        right.markdown(
            '<div class="chart-placeholder"><b>Findings by Severity</b><span>'
            'Severity is not configured. Add <code>Rule ID</code> and <code>Severity</code> columns to '
            '<code>ComplianceRules</code>, or add severity parameters.</span></div>',
            unsafe_allow_html=True,
        )
    left, right = st.columns(2)
    if findings["branch"].notna().any():
        branch = findings["branch"].dropna().value_counts().head(12).rename_axis("Branch").reset_index(name="Findings")
        fig = px.bar(branch, x="Branch", y="Findings", text="Findings", title="Findings by Branch",
                     color_discrete_sequence=["#4f7d66"])
        style_figure(fig)
        fig.update_traces(textposition="outside", hovertemplate="%{x}<br>%{y:,} findings<extra></extra>")
        left.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    else:
        left.info("Branch chart unavailable: no branch values in findings.")
    dates = pd.to_datetime(findings["occurrence_date"], errors="coerce")
    if dates.dropna().dt.normalize().nunique() > 1:
        dated = findings.loc[dates.notna(), ["rule_name"]].copy()
        dated["Date"] = dates[dates.notna()].dt.normalize().values
        span_days = (dated["Date"].max() - dated["Date"].min()).days
        if span_days > 120:
            dated["Period"] = dated["Date"].dt.to_period("M").dt.to_timestamp()
            granularity = "Monthly"
        elif span_days > 45:
            dated["Period"] = dated["Date"].dt.to_period("W").dt.start_time
            granularity = "Weekly"
        else:
            dated["Period"] = dated["Date"]
            granularity = "Daily"
        timeline = dated.groupby(["Period", "rule_name"]).size().reset_index(name="Findings")
        fig = px.line(
            timeline, x="Period", y="Findings", color="rule_name", markers=True,
            title=f"Findings Over Time · {granularity}",
            color_discrete_sequence=["#28678f", "#b45309", "#2f7d5a", "#7c3aed"],
        )
        style_figure(fig)
        fig.update_traces(line_width=2.5, marker_size=6)
        fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-.23, xanchor="center", x=.5))
        right.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    else:
        entity_counts = (
            findings["entity_type"].fillna("Unspecified").value_counts()
            .rename_axis("Entity Type").reset_index(name="Findings")
        )
        fig = px.bar(
            entity_counts.sort_values("Findings"), x="Findings", y="Entity Type",
            orientation="h", text="Findings", title="Findings by Entity Type",
            color_discrete_sequence=["#58758f"],
        )
        style_figure(fig)
        fig.update_traces(
            textposition="outside", cliponaxis=False,
            hovertemplate="%{y}<br>%{x:,} findings<extra></extra>",
        )
        fig.update_layout(showlegend=False)
        right.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    passed = sum(result.status == "Executed" and result.findings.empty for result in rule_results)
    failed = sum(result.status == "Executed" and not result.findings.empty for result in rule_results)
    not_executed = sum(result.status != "Executed" for result in rule_results)
    status = pd.DataFrame({
        "Outcome": ["Passed", "Exception", "Not Executed"],
        "Rules": [passed, failed, not_executed],
    })
    fig = px.bar(status, x="Outcome", y="Rules", title="Compliance Status", color="Outcome",
                 color_discrete_map={"Passed": "#2f7d5a", "Exception": "#b45309", "Not Executed": "#64748b"})
    style_figure(fig)
    fig.update_layout(showlegend=False)
    left.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    heatmap_tab, ranking_tab = right.tabs(["Rule × Branch heatmap", "Top problem areas"])
    with heatmap_tab:
        heatmap_data = findings.dropna(subset=["branch"]).pivot_table(
            index="rule_name", columns="branch", aggfunc="size", fill_value=0
        )
        if not heatmap_data.empty:
            fig = px.imshow(
                heatmap_data,
                text_auto=True,
                aspect="auto",
                title="Finding concentration",
                color_continuous_scale=[[0, "#eef4f8"], [1, "#28678f"]],
                labels=dict(x="Branch", y="Rule", color="Findings"),
            )
            style_figure(fig)
            fig.update_layout(coloraxis_showscale=False)
            fig.update_traces(hovertemplate="%{y}<br>%{x}<br>%{z:,} findings<extra></extra>")
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        else:
            st.info("Branch-level concentration is unavailable.")
    with ranking_tab:
        st.dataframe(
            by_rule.sort_values("Findings", ascending=False).head(5),
            width="stretch", hide_index=True, height=310,
        )


def findings_table(findings: pd.DataFrame, all_findings: pd.DataFrame, heading: bool = True) -> None:
    if heading:
        st.markdown("### Detailed findings")
    display_columns = [
        column for column in FINDING_COLUMNS
        if column in findings.columns and (findings.empty or findings[column].notna().any())
    ]
    display = findings[display_columns].rename(columns=FINDING_LABELS)
    for column in display.columns:
        if column not in {"Detection Date", "Occurrence Date"}:
            display[column] = display[column].fillna("").astype(str)
    st.caption(f"Showing {len(findings):,} finding(s) with the active filters.")
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        height=390,
        column_config={
            "Detection Date": st.column_config.DateColumn(format="DD MMM YYYY"),
            "Occurrence Date": st.column_config.DateColumn(format="DD MMM YYYY"),
            "Evidence": st.column_config.TextColumn(width="large"),
            "Recommended Action": st.column_config.TextColumn(width="large"),
        },
    )
    left, right, _ = st.columns([1, 1, 2])
    left.download_button("Download filtered CSV", findings.to_csv(index=False).encode("utf-8"),
                         "filtered_compliance_findings.csv", "text/csv", width="stretch")
    right.download_button("Download all CSV", all_findings.to_csv(index=False).encode("utf-8"),
                          "all_compliance_findings.csv", "text/csv", width="stretch")


def render_review_summary(
    sheets: dict[str, pd.DataFrame], findings: pd.DataFrame, results: list[RuleResult]
) -> None:
    summary = compliance_review_summary(sheets, findings, results)

    def items(values: list[str], empty_message: str) -> str:
        content = values or [empty_message]
        return "".join(f'<div class="summary-item">{escape(value)}</div>' for value in content)

    st.markdown("### Compliance review summary")
    st.caption("Automatically calculated from the uploaded data and active filters. This is rule-based analysis, not an AI-generated summary.")
    st.markdown(
        '<div class="summary-grid">'
        '<div class="summary-card attention"><div class="summary-title">Needs attention</div>'
        f'{items(summary["attention"], "No immediate exceptions identified in the current view.")}</div>'
        '<div class="summary-card positive"><div class="summary-title">What is going well</div>'
        f'{items(summary["positive"], "No positive control outcome is available yet.")}</div>'
        '<div class="summary-card actions"><div class="summary-title">Recommended next steps</div>'
        f'{items(summary["actions"], "Continue monitoring and retain evidence of the review.")}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_dashboard(sheets: dict[str, pd.DataFrame], findings: pd.DataFrame, filtered: pd.DataFrame, results: list[RuleResult]) -> None:
    page_header("Compliance Dashboard", "Consolidated exception monitoring from uploaded CSV and Excel data")
    total_records = sum(len(frame) for frame in sheets.values())
    executed = sum(result.status == "Executed" for result in results)
    has_severity = not filtered.empty and filtered["severity"].fillna("Unspecified").ne("Unspecified").any()
    high_risk = int(filtered["severity"].isin(["Critical", "High"]).sum()) if has_severity else None
    open_count = int(filtered["status"].eq("Open").sum()) if not filtered.empty else 0
    compliance_rate = max(0.0, ((total_records - len(filtered)) / total_records) * 100) if total_records else 100.0
    kpi_cards([("Total Records Scanned", f"{total_records:,}"), ("Rules Executed", f"{executed} / {len(results)}"),
               ("Total Compliance Findings", f"{len(filtered):,}", "#7c5c24"),
               ("High-Risk Findings", f"{high_risk:,}" if high_risk is not None else "—",
                "#b42318" if high_risk is not None else "#64748b"),
               ("Open Findings", f"{open_count:,}", "#b45309"),
               ("Compliance Rate", f"{compliance_rate:.1f}%", "#2f7d5a")])
    not_executed = [result for result in results if result.status == "Not Executed"]
    if not_executed:
        with st.expander(f"Why {len(not_executed)} rule(s) could not execute", expanded=executed == 0):
            st.dataframe(
                pd.DataFrame([{"Rule": result.rule_name, "Reason": result.reason} for result in not_executed]),
                width="stretch",
                hide_index=True,
            )
    if not has_severity and not filtered.empty:
        st.warning("Finding severity is not configured, so High-Risk Findings cannot be calculated yet.")
    render_review_summary(sheets, filtered, results)
    st.markdown("### Compliance summary")
    chart_block(filtered, results)
    findings_table(filtered, findings)


def render_data_overview(filenames: list[str], sheets: dict[str, pd.DataFrame], warnings: list[str]) -> None:
    page_header("Data Import / Data Overview", "Source inventory and schema diagnostics")
    total_rows = sum(len(frame) for frame in sheets.values())
    blank_cells = sum(int(frame.isna().sum().sum()) for frame in sheets.values())
    total_cells = sum(int(frame.shape[0] * frame.shape[1]) for frame in sheets.values())
    duplicate_rows = sum(int(frame.duplicated().sum()) for frame in sheets.values())
    completeness = (100 * (total_cells - blank_cells) / total_cells) if total_cells else 100.0
    kpi_cards([
        ("Source Files", f"{len(filenames):,}"), ("Data Entities", f"{len(sheets):,}"),
        ("Imported Rows", f"{total_rows:,}"), ("Cell Completeness", f"{completeness:.1f}%"),
        ("Duplicate Rows", f"{duplicate_rows:,}", "#b45309" if duplicate_rows else "#2f7d5a"),
    ])
    if warnings:
        with st.expander(f"Import notices ({len(warnings)})"):
            st.dataframe(
                pd.DataFrame({"Notice": warnings}), width="stretch", hide_index=True
            )
    else:
        st.markdown(
            '<div class="quality-ok">✓ All selected files imported without normalisation notices</div>',
            unsafe_allow_html=True,
        )
    overview = pd.DataFrame([{
        "Data Entity": name, "Rows": len(frame), "Columns": len(frame.columns),
        "Blank Cells": int(frame.isna().sum().sum()), "Duplicate Rows": int(frame.duplicated().sum()),
    } for name, frame in sheets.items()]).sort_values("Rows", ascending=False)
    st.markdown("### Imported data entities")
    st.caption("Row counts and basic quality checks for every loaded worksheet or CSV entity.")
    st.dataframe(
        overview,
        width="stretch",
        hide_index=True,
        height=min(420, 38 + len(overview) * 35),
        column_config={
            "Data Entity": st.column_config.TextColumn(width="large"),
            "Rows": st.column_config.NumberColumn(format="localized"),
            "Columns": st.column_config.NumberColumn(format="localized"),
            "Blank Cells": st.column_config.NumberColumn(format="localized"),
            "Duplicate Rows": st.column_config.NumberColumn(format="localized"),
        },
    )
    issues = schema_issues(sheets)
    if issues:
        st.markdown("#### Missing expected fields")
        st.caption("Only rules that require these fields are affected; other rules continue normally.")
        st.dataframe(
            pd.DataFrame([
                {"Data entity": sheet, "Missing fields": ", ".join(fields)}
                for sheet, fields in issues.items()
            ]),
            width="stretch",
            hide_index=True,
        )
    st.markdown("### Data inspector")
    selector_column, limit_column = st.columns([3, 1])
    selected = selector_column.selectbox("Data entity", list(sheets))
    row_limit = limit_column.selectbox("Rows to preview", [25, 50, 100], index=0)
    frame = sheets[selected]
    default_columns = list(frame.columns[: min(8, len(frame.columns))])
    selected_columns = st.multiselect(
        "Columns to display",
        list(frame.columns),
        default=default_columns,
        help="Select fewer columns for a cleaner preview; all columns remain available.",
    )
    preview_tab, profile_tab = st.tabs(["Data preview", "Column profile"])
    with preview_tab:
        if not selected_columns:
            st.info("Select at least one column to preview.")
        else:
            st.caption(f"Showing the first {min(row_limit, len(frame)):,} of {len(frame):,} rows and {len(selected_columns)} of {len(frame.columns)} columns.")
            try:
                st.dataframe(frame[selected_columns].head(row_limit), width="stretch", hide_index=True, height=420)
            except Exception as exc:
                st.error(f"Preview unavailable for this source: {exc}")
    with profile_tab:
        profile = pd.DataFrame({
            "Column": frame.columns,
            "Detected Type": frame.dtypes.astype(str).values,
            "Populated": [int(frame[column].notna().sum()) for column in frame.columns],
            "Blank": [int(frame[column].isna().sum()) for column in frame.columns],
            "Unique Values": [int(frame[column].nunique(dropna=True)) for column in frame.columns],
        })
        st.dataframe(profile, width="stretch", hide_index=True, height=420)


def render_rules(results: list[RuleResult]) -> None:
    page_header("Compliance Rules", "Execution status and rule prerequisites")
    result_map = {result.rule_id: result for result in results}
    executed = sum(result.status == "Executed" for result in results)
    exceptions = sum(result.status == "Executed" and not result.findings.empty for result in results)
    kpi_cards([
        ("Rules Available", str(len(RULES))), ("Rules Executed", str(executed), "#2f7d5a"),
        ("Rules with Exceptions", str(exceptions), "#b45309"),
        ("Not Executed", str(len(results) - executed), "#64748b"),
    ])
    st.markdown("### Rule catalogue")
    for rule in RULES:
        result = result_map[rule.rule_id]
        status_label = "Executed" if result.status == "Executed" else "Not Executed"
        with st.container(border=True):
            title_column, status_column, count_column = st.columns([5, 1.4, 1.2])
            title_column.markdown(f"#### {rule.rule_id} · {rule.name}")
            status_column.markdown(f"**{status_label}**")
            count_column.metric("Findings", len(result.findings))
            st.write(rule.description)
            data_column, parameter_column, confirmation_column = st.columns(3)
            data_column.caption("REQUIRED DATA")
            data_column.write(rule.required_data)
            parameter_column.caption("REQUIRED PARAMETERS")
            parameter_column.write(rule.required_parameters)
            confirmation_column.caption("STAKEHOLDER CONFIRMATION")
            confirmation_column.write("Required" if rule.confirmation_required else "Not required")
            if result.reason:
                st.warning(result.reason)
            if rule.rule_id == "R003":
                st.caption("Prototype interpretation — rule requires confirmation from compliance stakeholder.")
            elif rule.rule_id == "R005":
                st.caption("Prototype interpretation — exact senior-citizen fixed-deposit policy requires stakeholder confirmation.")


def render_reports(sheets: dict[str, pd.DataFrame], findings: pd.DataFrame, filtered: pd.DataFrame, results: list[RuleResult]) -> None:
    page_header("Compliance Reports", "Export-ready summaries based on active global filters")
    summary = report_summary(sheets, filtered, results)
    kpi_cards([("Total Data Processed", f"{summary['total_records']:,}"),
               ("Rules Executed", str(summary["rules_executed"])),
               ("Rules Not Executed", str(len(summary["rules_not_executed"]))),
               ("Unresolved Findings", f"{summary['unresolved_findings']:,}")])
    not_executed = summary["rules_not_executed"]
    if not_executed:
        st.markdown("### Rules that could not execute")
        st.dataframe(pd.DataFrame([{"Rule": item.rule_name, "Reason": item.reason} for item in not_executed]),
                     width="stretch", hide_index=True)
    st.markdown("### Findings overview")
    chart_block(filtered, results)
    findings_table(filtered, findings, heading=False)
    st.download_button(
        "Download compliance report (Excel)",
        build_excel_report(sheets, filtered, findings, results),
        "compliance_report.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="content",
    )


def render_parameters(parameters: dict, warnings: list[str]) -> None:
    page_header("Settings / Parameters", "Read-only compliance configuration supplied by uploaded data")
    if warnings:
        st.warning("Some parameter-dependent rules may not execute.")
        with st.expander("Parameter diagnostics", expanded=True):
            for warning in warnings:
                st.write(f"• {warning}")
    if parameters:
        st.dataframe(pd.DataFrame([{"Parameter": key, "Value": value} for key, value in parameters.items()]),
                     width="stretch", hide_index=True)
    else:
        st.info("No parameters are available. Parameter-dependent rules will be marked Not Executed.")
    st.caption("Parameters cannot be edited in this prototype. Update the source file and upload it again.")


def welcome() -> list:
    page_header("Bank Compliance Analysis", "File-driven compliance review prototype")
    st.markdown('<div class="notice"><b>Start a compliance review</b><br>Select all CSV and Excel sources for this review together. Files are processed locally and no sample findings are created.</div>', unsafe_allow_html=True)
    st.markdown("### Upload source files")
    uploaded = st.file_uploader(
        "Choose or drag files here",
        type=["csv", "xlsx", "xlsm", "xls", "xlsb"],
        accept_multiple_files=True,
        help="Matching sheets and CSV entities are combined automatically.",
        key="welcome_file_uploader",
    )
    st.caption("Accepted formats: CSV, XLSX, XLSM, XLS and XLSB · Multiple files allowed · Maximum 200 MB per file")
    st.markdown("### Expected data entities")
    entity_cards = "".join(f'<div class="entity-chip">{sheet}</div>' for sheet in EXPECTED_SHEETS)
    st.markdown(f'<div class="entity-grid">{entity_cards}</div>', unsafe_allow_html=True)
    st.markdown("### What happens next")
    st.markdown("""
    <div class="step-grid">
      <div class="step-card"><b>1 · Import and validate</b>Files are combined, columns normalised, and missing inputs identified.</div>
      <div class="step-card"><b>2 · Execute rules</b>Each eligible compliance rule runs independently so one issue cannot stop the review.</div>
      <div class="step-card"><b>3 · Review and export</b>Filter findings, inspect evidence, and download report-ready CSV results.</div>
    </div>
    """, unsafe_allow_html=True)
    st.caption("Tip: use entity names in CSV filenames, such as Customers.csv or bank_compliance_parameters.csv. Consolidated CSV exports are also supported.")
    return uploaded


def main() -> None:
    inject_styles()
    st.sidebar.markdown("## ◈ Bank Compliance")
    st.sidebar.caption("Analysis prototype")
    page = st.sidebar.radio("Navigation", NAVIGATION, label_visibility="collapsed")
    file_payloads = st.session_state.get("uploaded_file_payloads")
    if not file_payloads:
        uploaded = welcome()
        if uploaded:
            st.session_state.uploaded_file_payloads = tuple((item.name, item.getvalue()) for item in uploaded)
            st.rerun()
        return
    st.sidebar.markdown("---")
    st.sidebar.markdown("#### Active data sources")
    source_names = [name for name, _ in file_payloads]
    if st.sidebar.button("Replace uploaded files", width="stretch"):
        del st.session_state.uploaded_file_payloads
        for key in list(st.session_state):
            if key.startswith("filter_") or key == "welcome_file_uploader":
                del st.session_state[key]
        st.rerun()
    try:
        sheets, warnings, parameters, parameter_warnings, findings, results = analyse_files(
            file_payloads, IMPORT_PIPELINE_VERSION
        )
    except Exception as exc:
        page_header("Files could not be loaded", "Check the files and try again")
        st.error(f"The uploaded data could not be processed: {exc}")
        return
    if not sheets:
        page_header("No readable data found", "Review the selected source files")
        st.error("None of the selected files contained readable CSV or Excel data. Replace the files and try again.")
        return
    st.sidebar.markdown(
        f'<div class="source-summary"><b>{len(source_names)} files selected</b><br>'
        f'{len(sheets)} data entities loaded · {len(warnings)} import notices</div>',
        unsafe_allow_html=True,
    )
    with st.sidebar.expander("View source filenames"):
        for source_name in source_names:
            st.caption(f"• {escape(source_name)}")
    filter_pages = {"Dashboard", "Compliance Findings", "Reports"}
    filters = sidebar_filters(findings) if page in filter_pages else {}
    filtered = apply_finding_filters(findings, filters)
    if page == "Dashboard":
        render_dashboard(sheets, findings, filtered, results)
    elif page == "Data Import / Data Overview":
        render_data_overview(source_names, sheets, warnings)
    elif page == "Compliance Findings":
        page_header("Compliance Findings", "Detailed exceptions based on active global filters")
        findings_table(filtered, findings, heading=False)
    elif page == "Compliance Rules":
        render_rules(results)
    elif page == "Reports":
        render_reports(sheets, findings, filtered, results)
    elif page == "AI Copilot":
        page_header("AI Compliance Copilot", "Planned capability")
        st.markdown('<div class="notice">AI Compliance Copilot will be added in a later phase. It will explain findings, answer compliance questions, summarise risk, and assist with audit reporting.</div>', unsafe_allow_html=True)
        st.caption("No external AI service is connected in this prototype.")
    else:
        render_parameters(parameters, parameter_warnings)


if __name__ == "__main__":
    main()
