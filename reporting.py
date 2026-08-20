"""Reusable filtering and report summary functions."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd


def apply_finding_filters(findings: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
    result = findings.copy()
    for field in ("branch", "rule_name", "severity", "status", "entity_type"):
        values = filters.get(field)
        if values and field in result.columns:
            result = result[result[field].astype(str).isin(values)]
    date_range = filters.get("date_range")
    date_field = "occurrence_date" if "occurrence_date" in result.columns else "detected_at"
    if date_range and date_field in result.columns:
        dates = pd.to_datetime(result[date_field], errors="coerce").dt.normalize()
        date_mask = dates.between(pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1]))
        if filters.get("include_undated", True):
            date_mask |= dates.isna()
        result = result[date_mask]
    search = str(filters.get("search", "")).strip().lower()
    if search:
        searchable = [column for column in ("customer_id", "account_id") if column in result.columns]
        if searchable:
            mask = pd.Series(False, index=result.index)
            for column in searchable:
                mask |= result[column].fillna("").astype(str).str.lower().str.contains(search, regex=False)
            result = result[mask]
    return result


def report_summary(sheets: dict[str, pd.DataFrame], findings: pd.DataFrame, rule_results: list[Any]) -> dict[str, Any]:
    return {
        "total_records": sum(len(frame) for frame in sheets.values()),
        "rules_executed": sum(result.status == "Executed" for result in rule_results),
        "rules_not_executed": [result for result in rule_results if result.status != "Executed"],
        "total_findings": len(findings),
        "unresolved_findings": int(findings["status"].isin(["Open", "Pending"]).sum()) if not findings.empty else 0,
        "by_severity": findings["severity"].value_counts() if not findings.empty else pd.Series(dtype=int),
        "by_rule": findings["rule_name"].value_counts() if not findings.empty else pd.Series(dtype=int),
        "by_branch": findings["branch"].dropna().value_counts() if not findings.empty else pd.Series(dtype=int),
    }


def compliance_review_summary(
    sheets: dict[str, pd.DataFrame], findings: pd.DataFrame, rule_results: list[Any]
) -> dict[str, list[str]]:
    """Create a deterministic narrative summary from rule outputs.

    Statements are strictly derived from counts and existing rule metadata; no
    external service, model, or inferred regulation is involved.
    """
    attention: list[str] = []
    positive: list[str] = []
    actions: list[str] = []
    executed = [result for result in rule_results if result.status == "Executed"]
    not_executed = [result for result in rule_results if result.status != "Executed"]
    passed = [result for result in executed if result.findings.empty]

    if findings.empty:
        positive.append("No compliance exceptions match the current analysis scope and filters.")
    else:
        open_count = int(findings["status"].isin(["Open", "Pending"]).sum())
        if open_count:
            attention.append(f"{open_count:,} findings remain unresolved in the current view.")
        rule_counts = findings["rule_name"].value_counts()
        top_rule = str(rule_counts.index[0])
        top_count = int(rule_counts.iloc[0])
        share = top_count / len(findings) * 100
        attention.append(f"{top_rule} is the largest problem area with {top_count:,} findings ({share:.1f}% of the current view).")
        configured = findings[findings["severity"].fillna("Unspecified") != "Unspecified"]
        if configured.empty:
            attention.append("Finding severity is not configured, so risk-based prioritisation is unavailable.")
            actions.append("Configure a severity for each rule in ComplianceRules or Parameters.")
        else:
            high_count = int(configured["severity"].isin(["Critical", "High"]).sum())
            if high_count:
                attention.append(f"{high_count:,} findings are rated Critical or High and should be reviewed first.")
                actions.append("Prioritise the open Critical and High findings for investigation.")
            else:
                positive.append("No Critical or High findings appear in the current view.")
        branches = findings["branch"].dropna().astype(str)
        if not branches.empty:
            branch_counts = branches.value_counts()
            positive.append(f"Branch information is available for {branches.notna().sum():,} findings, enabling branch-level follow-up.")
            actions.append(f"Review {branch_counts.index[0]} first; it has the highest current finding count ({int(branch_counts.iloc[0]):,}).")

        recommendations = (
            findings[["rule_name", "recommended_action"]]
            .dropna()
            .drop_duplicates("rule_name")
        )
        if not recommendations.empty:
            top_rules = set(rule_counts.head(2).index)
            for _, row in recommendations[recommendations["rule_name"].isin(top_rules)].iterrows():
                actions.append(f"{row['rule_name']}: {row['recommended_action']}")

    if executed:
        positive.append(f"{len(executed)} of {len(rule_results)} configured rules executed successfully.")
    if passed:
        names = ", ".join(result.rule_name for result in passed[:2])
        positive.append(f"{len(passed)} executed rule(s) produced no exceptions: {names}.")
    if not_executed:
        attention.append(f"{len(not_executed)} rule(s) could not execute because required data or parameters were unavailable.")
        for result in not_executed[:2]:
            actions.append(f"Enable {result.rule_name}: {result.reason}")
    if sheets:
        positive.append(f"The analysis processed {sum(len(frame) for frame in sheets.values()):,} rows across {len(sheets)} data entities.")

    # Preserve order while avoiding repeated recommendations.
    actions = list(dict.fromkeys(actions))[:5]
    return {"attention": attention[:4], "positive": positive[:4], "actions": actions}


def build_excel_report(
    sheets: dict[str, pd.DataFrame],
    filtered_findings: pd.DataFrame,
    all_findings: pd.DataFrame,
    rule_results: list[Any],
) -> bytes:
    """Build a portable review workbook without coupling reporting to Streamlit."""
    summary = report_summary(sheets, filtered_findings, rule_results)
    summary_frame = pd.DataFrame({
        "Metric": ["Total data processed", "Rules executed", "Rules not executed", "Filtered findings", "Unresolved findings"],
        "Value": [summary["total_records"], summary["rules_executed"], len(summary["rules_not_executed"]),
                  summary["total_findings"], summary["unresolved_findings"]],
    })
    rule_frame = pd.DataFrame([
        {"Rule ID": result.rule_id, "Rule Name": result.rule_name, "Status": result.status,
         "Findings": len(result.findings), "Reason": result.reason}
        for result in rule_results
    ])
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_frame.to_excel(writer, sheet_name="Summary", index=False)
        rule_frame.to_excel(writer, sheet_name="Rule Execution", index=False)
        filtered_findings.to_excel(writer, sheet_name="Filtered Findings", index=False)
        all_findings.to_excel(writer, sheet_name="All Findings", index=False)
    return output.getvalue()
