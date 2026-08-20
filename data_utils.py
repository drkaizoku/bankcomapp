"""Workbook loading, schema normalisation, and parameter utilities."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO

import pandas as pd


EXPECTED_SHEETS = [
    "Customers",
    "Accounts",
    "Transactions",
    "Employees",
    "MandatoryLeave",
    "FixedDeposits",
    "Parameters",
    "BankHolidays",
]
OPTIONAL_SHEETS = ["ComplianceRules", "Branches", "FeeWaivers"]

SHEET_REQUIRED_FIELDS: dict[str, list[str]] = {
    "Customers": ["customer_id"],
    "Accounts": ["account_id", "customer_id"],
    "Transactions": ["transaction_id", "posting_date"],
    "Employees": ["employee_id"],
    "MandatoryLeave": ["employee_id", "start_date", "end_date"],
    "FixedDeposits": ["customer_id", "status"],
    "Parameters": ["parameter", "value"],
    "BankHolidays": ["holiday_date"],
}

COLUMN_ALIASES: dict[str, set[str]] = {
    "customer_id": {"customerid", "customer_number", "customerno", "cust_id"},
    "account_id": {"accountid", "account_number", "accountno", "acct_id"},
    "transaction_id": {"transactionid", "transaction_number", "txn_id", "reference"},
    "employee_id": {"employeeid", "staff_id", "staffid", "user_id"},
    "date_of_birth": {"dob", "birth_date", "birthdate", "customer_dob"},
    "email": {"email_address", "emailaddress", "customer_email"},
    "is_minor": {
        "minor", "minor_flag", "account_is_minor", "minor_account_flag",
        "customer_minor_flag", "account_minor_indicator", "account_classification",
    },
    "branch": {"branch_id", "branch_name", "branch_code", "location"},
    "posting_date": {"transaction_date", "posted_date", "txn_date", "date"},
    "start_date": {"leave_start", "leave_start_date", "from_date"},
    "end_date": {"leave_end", "leave_end_date", "to_date"},
    "holiday_date": {"bank_holiday_date", "date"},
    "fixed_deposit_id": {"fixeddepositid", "deposit_id", "fd_id"},
    "status": {"deposit_status", "fd_status", "fixed_deposit_status", "account_status"},
    "interest_rate": {"rate", "fd_interest_rate"},
    "parameter": {"parameter_name", "parameter_key", "parameter_id", "key", "name", "setting"},
    "value": {"parameter_value", "configured_value", "setting_value"},
    "severity": {"risk", "risk_level", "severity_level", "default_severity", "risk_rating"},
}


def normalise_name(value: Any) -> str:
    """Convert labels to stable snake_case identifiers."""
    text = re.sub(r"[^a-zA-Z0-9]+", "_", str(value).strip()).strip("_").lower()
    for canonical, aliases in COLUMN_ALIASES.items():
        if text == canonical or text in aliases:
            return canonical
    return text


def normalise_frame_columns(
    frame: pd.DataFrame, entity_name: str | None = None
) -> tuple[pd.DataFrame, list[str]]:
    """Normalise labels and safely coalesce aliases that map to one column.

    Exports often contain both ``Transaction Date`` and ``Posting Date``. Both
    are valid aliases for ``posting_date``; retaining duplicate labels causes
    Arrow/Streamlit rendering failures. The first non-blank value is retained.
    """
    raw_names = [
        re.sub(r"[^a-zA-Z0-9]+", "_", str(column).strip()).strip("_").lower()
        for column in frame.columns
    ]
    normalised = [normalise_name(column) for column in frame.columns]
    # Resolve generic labels using the source entity. A global alias cannot know
    # whether "Date" means a transaction posting date or a bank holiday date.
    if entity_name == "BankHolidays":
        normalised = ["holiday_date" if name == "posting_date" else name for name in normalised]
    elif entity_name == "Branches":
        normalised = [
            raw if raw in {"branch_id", "branch_name"} else name
            for raw, name in zip(raw_names, normalised)
        ]
    elif entity_name == "Transactions" and any(
        raw in {"posted_date", "posting_date"} for raw in raw_names
    ):
        normalised = [
            "transaction_date" if raw == "transaction_date" else name
            for raw, name in zip(raw_names, normalised)
        ]
    positions: dict[str, list[int]] = {}
    for index, name in enumerate(normalised):
        positions.setdefault(name, []).append(index)
    output: dict[str, pd.Series] = {}
    duplicates: list[str] = []
    for name, indexes in positions.items():
        combined = frame.iloc[:, indexes[0]].copy()
        if len(indexes) > 1:
            duplicates.append(name)
            for index in indexes[1:]:
                candidate = frame.iloc[:, index]
                blank = combined.isna() | combined.map(
                    lambda value: isinstance(value, str) and not value.strip()
                )
                combined = combined.where(~blank, candidate)
        output[name] = combined
    return pd.DataFrame(output, index=frame.index), duplicates


def _canonical_sheet_name(name: str) -> str:
    known_sheets = EXPECTED_SHEETS + OPTIONAL_SHEETS
    lookup = {normalise_name(expected): expected for expected in known_sheets}
    normalised = normalise_name(name)
    if normalised in lookup:
        return lookup[normalised]
    # Accept descriptive names such as bank_compliance_parameters.csv.
    compact_name = normalised.replace("_", "")
    embedded = [
        expected
        for expected in known_sheets
        if normalise_name(expected).replace("_", "") in compact_name
    ]
    return embedded[-1] if embedded else name.strip()


def load_workbook(file: BinaryIO | BytesIO, extension: str = ".xlsx") -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Read every worksheet and normalise columns without enforcing a fixed schema."""
    engines = {".xlsx": "openpyxl", ".xlsm": "openpyxl", ".xls": "xlrd", ".xlsb": "pyxlsb"}
    engine = engines.get(extension.lower())
    if engine is None:
        raise ValueError(f"Unsupported Excel format: {extension}")
    workbook = pd.ExcelFile(file, engine=engine)
    sheets: dict[str, pd.DataFrame] = {}
    warnings: list[str] = []
    for original_name in workbook.sheet_names:
        canonical_name = _canonical_sheet_name(original_name)
        frame = pd.read_excel(workbook, sheet_name=original_name, dtype=object)
        frame, duplicates = normalise_frame_columns(frame, canonical_name)
        if duplicates:
            warnings.append(
                f"Worksheet '{original_name}' coalesced duplicate normalized columns: {', '.join(duplicates)}."
            )
        sheets[canonical_name] = frame
    for expected in EXPECTED_SHEETS:
        if expected not in sheets:
            warnings.append(f"Missing worksheet: {expected}")
    return sheets, warnings


def load_data_files(files: list[tuple[str, bytes]]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Combine CSV entities and worksheets from any number of uploaded data files.

    A CSV filename supplies its logical sheet name: ``Customers.csv`` becomes
    ``Customers``. When several sources contain the same logical sheet, their rows
    are appended and their columns are aligned by Pandas.
    """
    collected: dict[str, list[pd.DataFrame]] = {}
    warnings: list[str] = []
    for filename, content in files:
        extension = Path(filename).suffix.lower()
        try:
            if extension == ".csv":
                logical_name = _canonical_sheet_name(Path(filename).stem)
                try:
                    frame = pd.read_csv(BytesIO(content), dtype=object)
                except UnicodeDecodeError:
                    frame = pd.read_csv(BytesIO(content), dtype=object, encoding="latin-1")
                frame, duplicates = normalise_frame_columns(frame, logical_name)
                if duplicates:
                    warnings.append(
                        f"'{filename}' coalesced duplicate normalized columns: {', '.join(duplicates)}."
                    )
                collected.setdefault(logical_name, []).append(frame)
            else:
                workbook_sheets, workbook_warnings = load_workbook(BytesIO(content), extension)
                warnings.extend(note for note in workbook_warnings if "coalesced duplicate" in note)
                for sheet_name, frame in workbook_sheets.items():
                    collected.setdefault(sheet_name, []).append(frame)
        except Exception as exc:
            warnings.append(f"Could not load '{filename}': {exc}")

    sheets: dict[str, pd.DataFrame] = {}
    for sheet_name, frames in collected.items():
        sheets[sheet_name] = pd.concat(frames, ignore_index=True, sort=False) if len(frames) > 1 else frames[0]
        if len(frames) > 1:
            warnings.append(f"Combined {len(frames)} uploaded sources into '{sheet_name}'.")
    for expected in EXPECTED_SHEETS:
        if expected not in sheets:
            warnings.append(f"Missing worksheet or CSV entity: {expected}")
    return sheets, warnings


def load_parameters(sheets: dict[str, pd.DataFrame]) -> tuple[dict[str, Any], list[str]]:
    """Read Parameters as a case-insensitive key/value mapping."""
    frame = sheets.get("Parameters")
    parameters: dict[str, Any] = {}
    warnings: list[str] = []
    if frame is None or frame.empty:
        warnings.append("Parameters worksheet or CSV entity is missing or blank.")
    elif not {"parameter", "value"}.issubset(frame.columns):
        warnings.append("Parameters requires parameter/name and value columns.")
    else:
        for _, row in frame.iterrows():
            if pd.notna(row["parameter"]):
                parameters[normalise_name(row["parameter"])] = row["value"]

    rule_config = sheets.get("ComplianceRules")
    if rule_config is not None and {"rule_id", "severity"}.issubset(rule_config.columns):
        rule_id_aliases = {
            "minor001": "r001", "email001": "r002", "leave001": "r003",
            "holiday001": "r004", "fd001": "r005",
        }
        for _, row in rule_config.iterrows():
            if pd.notna(row["rule_id"]) and pd.notna(row["severity"]):
                rule_id = normalise_name(row["rule_id"]).replace("_", "")
                internal_rule_id = rule_id_aliases.get(rule_id, rule_id)
                parameters.setdefault(f"{internal_rule_id}_severity", row["severity"])
    return parameters, warnings


def schema_issues(sheets: dict[str, pd.DataFrame]) -> dict[str, list[str]]:
    """Return missing prototype fields for available expected sheets."""
    issues: dict[str, list[str]] = {}
    for sheet, fields in SHEET_REQUIRED_FIELDS.items():
        if sheet in sheets:
            missing = [field for field in fields if field not in sheets[sheet].columns]
            if missing:
                issues[sheet] = missing
    return issues


def parse_date_series(values: pd.Series) -> pd.Series:
    """Parse dates consistently, coercing invalid values instead of raising."""
    return pd.to_datetime(values, errors="coerce").dt.normalize()


def truthy(values: pd.Series) -> pd.Series:
    """Interpret common spreadsheet flag values."""
    return values.fillna("").astype(str).str.strip().str.lower().isin(
        {"true", "yes", "y", "1", "minor"}
    )
