"""Regression tests for framework-independent prototype behaviour."""

from __future__ import annotations

import unittest
from io import BytesIO

import pandas as pd

from compliance_engine import RuleResult, empty_findings, run_rules
from data_utils import load_data_files, load_parameters
from reporting import apply_finding_filters, build_excel_report, compliance_review_summary


class DataImportTests(unittest.TestCase):
    def test_contextual_date_alias_and_duplicate_columns(self) -> None:
        sheets, _ = load_data_files([
            ("bank_holidays.csv", b"Date,Holiday Name\n2026-01-01,New Year\n"),
            ("transactions.csv", b"Transaction ID,Transaction Date,Posting Date\nT1,,2026-01-01\n"),
        ])
        self.assertIn("holiday_date", sheets["BankHolidays"])
        self.assertNotIn("posting_date", sheets["BankHolidays"])
        self.assertEqual(list(sheets["Transactions"].columns).count("posting_date"), 1)

    def test_missing_inputs_isolate_each_rule(self) -> None:
        findings, results = run_rules({}, {})
        self.assertTrue(findings.empty)
        self.assertEqual(len(results), 5)
        self.assertTrue(all(result.status == "Not Executed" and result.reason for result in results))

    def test_rule_severity_is_loaded_without_a_default(self) -> None:
        sheets, _ = load_data_files([
            ("compliance_rules.csv", b"Rule ID,Severity\nR001,High\n"),
            ("parameters.csv", b"Parameter,Value\nminor_age_limit,18\n"),
        ])
        parameters, _ = load_parameters(sheets)
        self.assertEqual(parameters["r001_severity"], "High")


class ReportingTests(unittest.TestCase):
    def test_filtering_and_excel_report(self) -> None:
        findings = empty_findings()
        findings.loc[0] = [
            "F1", "R1", "Rule One", "Account", "A1", "C1", "A1", "B1", "High", "Open",
            "Expected", "Actual", "Evidence", "Review", pd.NaT, pd.Timestamp("2026-01-01"),
        ]
        filtered = apply_finding_filters(findings, {"severity": ["High"], "search": "c1"})
        self.assertEqual(len(filtered), 1)
        dated_filter = apply_finding_filters(
            findings,
            {"date_range": (pd.Timestamp("2026-01-01").date(), pd.Timestamp("2026-01-31").date()),
             "include_undated": True},
        )
        self.assertEqual(len(dated_filter), 1)
        result = RuleResult("R1", "Rule One", "Executed", "", findings)
        report = build_excel_report({"Accounts": pd.DataFrame({"account_id": ["A1"]})}, filtered, findings, [result])
        workbook = pd.ExcelFile(BytesIO(report), engine="openpyxl")
        self.assertEqual(
            set(workbook.sheet_names),
            {"Summary", "Rule Execution", "Filtered Findings", "All Findings"},
        )
        narrative = compliance_review_summary(
            {"Accounts": pd.DataFrame({"account_id": ["A1"]})}, filtered, [result]
        )
        self.assertTrue(narrative["attention"])
        self.assertTrue(narrative["positive"])
        self.assertTrue(narrative["actions"])


if __name__ == "__main__":
    unittest.main()
