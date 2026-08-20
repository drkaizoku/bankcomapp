"""Framework-independent prototype compliance rule engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable
from uuid import uuid4

import pandas as pd

from data_utils import parse_date_series, truthy


FINDING_COLUMNS = [
    "finding_id", "rule_id", "rule_name", "entity_type", "entity_id",
    "customer_id", "account_id", "branch", "severity", "status",
    "expected_value", "actual_value", "evidence", "recommended_action",
    "occurrence_date", "detected_at",
]


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    name: str
    description: str
    required_data: str
    required_parameters: str
    confirmation_required: bool
    runner: Callable[[dict[str, pd.DataFrame], dict[str, Any]], pd.DataFrame]


@dataclass
class RuleResult:
    rule_id: str
    rule_name: str
    status: str
    reason: str
    findings: pd.DataFrame


class RuleCannotExecute(ValueError):
    """Raised when a workbook does not supply a rule prerequisite."""


def empty_findings() -> pd.DataFrame:
    return pd.DataFrame(columns=FINDING_COLUMNS)


def _require_sheet(sheets: dict[str, pd.DataFrame], name: str, columns: set[str]) -> pd.DataFrame:
    frame = sheets.get(name)
    if frame is None:
        # A consolidated CSV may represent several logical entities. Explicitly
        # named sheets win; otherwise select the widest uploaded table that has
        # every required field and collapse repeated entity rows.
        candidates = [candidate for candidate in sheets.values() if columns.issubset(candidate.columns)]
        if candidates:
            frame = max(candidates, key=lambda candidate: len(candidate.columns)).drop_duplicates(
                subset=sorted(columns)
            )
        else:
            raise RuleCannotExecute(
                f"Required entity '{name}' is unavailable. Upload a '{name}' sheet/CSV "
                f"or a consolidated CSV containing: {', '.join(sorted(columns))}."
            )
    if frame.empty:
        raise RuleCannotExecute(f"Required worksheet '{name}' is blank.")
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise RuleCannotExecute(f"Worksheet '{name}' is missing columns: {', '.join(missing)}.")
    return frame.copy()


def _number_parameter(parameters: dict[str, Any], name: str) -> float:
    if name not in parameters or pd.isna(parameters[name]):
        raise RuleCannotExecute(f"Required parameter '{name}' is missing.")
    try:
        return float(parameters[name])
    except (TypeError, ValueError) as exc:
        raise RuleCannotExecute(f"Parameter '{name}' must be numeric.") from exc


def _severity(parameters: dict[str, Any], rule_id: str) -> str:
    value = parameters.get(f"{rule_id.lower()}_severity")
    return str(value).strip().title() if pd.notna(value) and str(value).strip() else "Unspecified"


def _age(dob: pd.Series, as_of: pd.Timestamp | None = None) -> pd.Series:
    reference = as_of or pd.Timestamp(date.today())
    dates = parse_date_series(dob)
    return reference.year - dates.dt.year - (
        (reference.month < dates.dt.month)
        | ((reference.month == dates.dt.month) & (reference.day < dates.dt.day))
    ).astype("Int64")


def _finding(rule_id: str, rule_name: str, entity_type: str, entity_id: Any,
             severity: str, expected: Any, actual: Any, evidence: str,
             action: str, row: pd.Series | dict[str, Any],
             occurrence_date: Any = None) -> dict[str, Any]:
    get = row.get
    return {
        "finding_id": f"{rule_id}-{uuid4().hex[:10].upper()}",
        "rule_id": rule_id,
        "rule_name": rule_name,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "customer_id": get("customer_id", None),
        "account_id": get("account_id", None),
        "branch": get("branch", None),
        "severity": severity,
        "status": "Open",
        "expected_value": expected,
        "actual_value": actual,
        "evidence": evidence,
        "recommended_action": action,
        "occurrence_date": occurrence_date,
        "detected_at": pd.Timestamp.now().normalize(),
    }


def rule_minor_accounts(sheets: dict[str, pd.DataFrame], parameters: dict[str, Any]) -> pd.DataFrame:
    limit = _number_parameter(parameters, "minor_age_limit")
    accounts = _require_sheet(sheets, "Accounts", {"account_id", "customer_id", "is_minor"})
    customers = _require_sheet(sheets, "Customers", {"customer_id", "date_of_birth"})
    account_columns = [column for column in ("account_id", "customer_id", "is_minor", "branch") if column in accounts]
    data = accounts[account_columns].merge(
        customers[["customer_id", "date_of_birth"]], on="customer_id", how="left"
    )
    data["calculated_age"] = _age(data["date_of_birth"])
    exceptions = data[truthy(data["is_minor"]) & (data["calculated_age"] > limit)]
    rows = [_finding("R001", "Minor Account Validation", "Account", row["account_id"],
        _severity(parameters, "R001"), f"Age <= {limit:g}", row["calculated_age"],
        f"Account is marked minor; calculated customer age is {row['calculated_age']}.",
        "Review the minor designation and customer date of birth.", row) for _, row in exceptions.iterrows()]
    return pd.DataFrame(rows, columns=FINDING_COLUMNS)


def rule_duplicate_email(sheets: dict[str, pd.DataFrame], parameters: dict[str, Any]) -> pd.DataFrame:
    customers = _require_sheet(sheets, "Customers", {"customer_id", "email"})
    customers["normalised_email"] = customers["email"].fillna("").astype(str).str.strip().str.lower()
    valid = customers[customers["normalised_email"] != ""]
    duplicates = valid[valid.duplicated("normalised_email", keep=False)]
    rows = []
    for _, row in duplicates.iterrows():
        count = int((valid["normalised_email"] == row["normalised_email"]).sum())
        rows.append(_finding("R002", "Duplicate Email Address", "Customer", row["customer_id"],
            _severity(parameters, "R002"), "Unique non-blank email",
            row["normalised_email"], f"Normalised email occurs on {count} customer records.",
            "Verify customer identity and correct or document the shared email.", row))
    return pd.DataFrame(rows, columns=FINDING_COLUMNS)


def rule_mandatory_leave(sheets: dict[str, pd.DataFrame], parameters: dict[str, Any]) -> pd.DataFrame:
    # Prototype interpretation: transaction employee_id is treated as the associated employee.
    # This definition intentionally needs confirmation from a compliance stakeholder.
    transactions = _require_sheet(sheets, "Transactions", {"transaction_id", "posting_date"})
    leave = _require_sheet(sheets, "MandatoryLeave", {"employee_id", "start_date", "end_date"})
    employee_columns = [
        column for column in ("employee_id", "performed_by_employee_id", "approved_by_employee_id")
        if column in transactions
    ]
    if not employee_columns:
        raise RuleCannotExecute(
            "Transactions requires employee_id, performed_by_employee_id, or approved_by_employee_id."
        )
    transaction_columns = [
        column for column in (
            "transaction_id", "posting_date", "customer_id", "account_id", "branch", *employee_columns
        )
        if column in transactions
    ]
    transactions = transactions[transaction_columns]
    if employee_columns != ["employee_id"]:
        identity_columns = [column for column in transaction_columns if column not in employee_columns]
        transactions = transactions.melt(
            id_vars=identity_columns,
            value_vars=employee_columns,
            value_name="employee_id",
        ).drop(columns="variable")
        transactions = transactions[
            transactions["employee_id"].notna()
            & transactions["employee_id"].astype(str).str.strip().ne("")
        ].drop_duplicates()
    leave = leave[["employee_id", "start_date", "end_date"]]
    transactions["posting_date"] = parse_date_series(transactions["posting_date"])
    leave["start_date"] = parse_date_series(leave["start_date"])
    leave["end_date"] = parse_date_series(leave["end_date"])
    if transactions["posting_date"].notna().sum() == 0:
        raise RuleCannotExecute("Transactions contains no valid posting_date values.")
    if leave[["start_date", "end_date"]].notna().all(axis=1).sum() == 0:
        raise RuleCannotExecute("MandatoryLeave contains no valid leave date ranges.")
    merged = transactions.merge(leave[["employee_id", "start_date", "end_date"]], on="employee_id", how="inner")
    exceptions = merged[merged["posting_date"].between(merged["start_date"], merged["end_date"])]
    rows = [_finding("R003", "Employee Mandatory Leave Transaction", "Transaction", row["transaction_id"],
        _severity(parameters, "R003"), "No associated employee transaction during mandatory leave",
        str(row["posting_date"].date()),
        f"Employee {row['employee_id']} is recorded on leave from {row['start_date'].date()} to {row['end_date'].date()}.",
        "Confirm the transaction association and investigate access during leave.", row,
        row["posting_date"]) for _, row in exceptions.iterrows()]
    return pd.DataFrame(rows, columns=FINDING_COLUMNS)


def rule_bank_holiday(sheets: dict[str, pd.DataFrame], parameters: dict[str, Any]) -> pd.DataFrame:
    transactions = _require_sheet(sheets, "Transactions", {"transaction_id", "posting_date"})
    holidays = _require_sheet(sheets, "BankHolidays", {"holiday_date"})
    transactions["posting_date"] = parse_date_series(transactions["posting_date"])
    holiday_dates = parse_date_series(holidays["holiday_date"]).dropna().unique()
    if not len(holiday_dates):
        raise RuleCannotExecute("BankHolidays contains no valid holiday_date values.")
    exceptions = transactions[transactions["posting_date"].isin(holiday_dates)]
    rows = [_finding("R004", "Bank Holiday Transaction Posting", "Transaction", row["transaction_id"],
        _severity(parameters, "R004"), "Posting date is not a configured bank holiday",
        str(row["posting_date"].date()), "Posting date matches a date in BankHolidays.",
        "Review the posting reason and supporting authorisation.", row,
        row["posting_date"]) for _, row in exceptions.iterrows()]
    return pd.DataFrame(rows, columns=FINDING_COLUMNS)


def rule_senior_fixed_deposit(sheets: dict[str, pd.DataFrame], parameters: dict[str, Any]) -> pd.DataFrame:
    senior_age = _number_parameter(parameters, "senior_citizen_age")
    deposits = _require_sheet(sheets, "FixedDeposits", {"customer_id", "status"})
    customers = _require_sheet(sheets, "Customers", {"customer_id", "date_of_birth"})
    deposit_columns = [
        column for column in (
            "fixed_deposit_id", "customer_id", "account_id", "branch", "status", "interest_rate"
        ) if column in deposits
    ]
    data = deposits[deposit_columns].merge(
        customers[["customer_id", "date_of_birth"]], on="customer_id", how="left"
    )
    data["calculated_age"] = _age(data["date_of_birth"])
    active = data["status"].fillna("").astype(str).str.strip().str.lower().isin({"active", "open", "current"})
    senior_active = active & (data["calculated_age"] >= senior_age)
    minimum_rate = parameters.get("minimum_senior_fd_rate")
    if minimum_rate is not None and pd.notna(minimum_rate):
        if "interest_rate" not in data:
            raise RuleCannotExecute(
                "Parameter 'minimum_senior_fd_rate' is configured but FixedDeposits is missing interest_rate."
            )
        try:
            minimum_rate = float(minimum_rate)
        except (TypeError, ValueError) as exc:
            raise RuleCannotExecute("Parameter 'minimum_senior_fd_rate' must be numeric.") from exc
        numeric_rate = pd.to_numeric(data["interest_rate"], errors="coerce")
        exceptions = data[senior_active & (numeric_rate < minimum_rate)]
    else:
        exceptions = data[senior_active]
    rows = []
    for index, row in exceptions.iterrows():
        entity_id = row.get("fixed_deposit_id", f"row-{index + 2}")
        actual = f"Active; customer age {row['calculated_age']}"
        if "interest_rate" in row and pd.notna(row["interest_rate"]):
            actual += f"; interest rate {row['interest_rate']}"
        expected = f"Review at age {senior_age:g} or above"
        if minimum_rate is not None and pd.notna(minimum_rate):
            expected += f"; interest rate >= {minimum_rate:g}"
        rows.append(_finding("R005", "Senior Citizen Fixed Deposit Review", "Fixed Deposit", entity_id,
            _severity(parameters, "R005"), expected, actual,
            "Active fixed deposit belongs to a customer at or above the configured senior-citizen age.",
            "Review the deposit against the approved senior-citizen fixed-deposit policy.", row))
    return pd.DataFrame(rows, columns=FINDING_COLUMNS)


RULES = [
    RuleDefinition("R001", "Minor Account Validation", "Minor-marked accounts where customer age exceeds the configured limit.", "Accounts, Customers", "minor_age_limit", False, rule_minor_accounts),
    RuleDefinition("R002", "Duplicate Email Address", "Non-blank normalised email addresses used by multiple customers.", "Customers", "None", False, rule_duplicate_email),
    RuleDefinition("R003", "Employee Mandatory Leave Transaction", "Transactions associated with employees during recorded mandatory leave.", "Transactions, MandatoryLeave", "None", True, rule_mandatory_leave),
    RuleDefinition("R004", "Bank Holiday Transaction Posting", "Transactions posted on a configured bank holiday.", "Transactions, BankHolidays", "None", False, rule_bank_holiday),
    RuleDefinition("R005", "Senior Citizen Fixed Deposit Review", "Active fixed deposits requiring review after the customer reaches configured senior age.", "FixedDeposits, Customers", "senior_citizen_age", True, rule_senior_fixed_deposit),
]


def run_rules(sheets: dict[str, pd.DataFrame], parameters: dict[str, Any]) -> tuple[pd.DataFrame, list[RuleResult]]:
    """Run rules independently; a failure never prevents later rules from running."""
    results: list[RuleResult] = []
    all_findings: list[pd.DataFrame] = []
    for rule in RULES:
        try:
            findings = rule.runner(sheets, parameters)
            results.append(RuleResult(rule.rule_id, rule.name, "Executed", "", findings))
            all_findings.append(findings)
        except RuleCannotExecute as exc:
            results.append(RuleResult(rule.rule_id, rule.name, "Not Executed", str(exc), empty_findings()))
        except Exception as exc:  # isolate unexpected workbook/rule errors
            results.append(RuleResult(rule.rule_id, rule.name, "Not Executed", f"Rule execution failed: {exc}", empty_findings()))
    combined = pd.concat(all_findings, ignore_index=True) if all_findings else empty_findings()
    return combined, results
