# Bank Compliance Analysis Application

A local, file-driven Streamlit prototype that validates uploaded banking data, runs independent compliance rules, and presents filterable findings and reports. It contains no embedded banking records and connects to no external services.

## Set up

Python 3.10 or newer is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.

## Run

```bash
streamlit run app.py
```

Open the local URL printed by Streamlit, then upload one or more data files from the sidebar. Supported formats are `.csv`, `.xlsx`, `.xlsm`, `.xls`, and `.xlsb`.

Multiple files can be selected in one upload. Matching worksheets are appended together. For CSV input, an entity name can be exact or part of a longer filename—for example, `Customers.csv`, `bank_customers.csv`, or `bank_compliance_parameters.csv`. CSV and Excel sources can be uploaded together.

A consolidated CSV such as `bank_compliance_test_data.csv` is also supported. When it is not named after a specific entity, each rule locates a suitable uploaded table from the columns it requires. Explicitly named entity files take precedence.

## Expected data entities

- `Customers`
- `Accounts`
- `Transactions`
- `Employees`
- `MandatoryLeave`
- `FixedDeposits`
- `Parameters`
- `BankHolidays`

Worksheets or CSV entities can be omitted; affected rules are marked **Not Executed** and other rules continue. Column labels are normalised to snake case and common aliases such as `Customer ID`, `CustomerID`, and `customer_id` are accepted.

The Data Overview page reports completeness, duplicate rows, missing fields, normalized columns, and import notices. The Reports page can export both CSV findings and a multi-sheet Excel compliance report.

The `Parameters` worksheet should use `Parameter` and `Value` columns. The initial parameter-dependent rules expect `minor_age_limit` and `senior_citizen_age`. Optional rule severities may be supplied as `r001_severity` through `r005_severity`, or through `Rule ID` and `Severity` columns in an optional `ComplianceRules` entity. Findings display `Unspecified` when severity is not configured; the application does not silently supply regulatory defaults.

## Prototype data safety

Use only synthetic or properly anonymised data during prototype development. Uploaded data is processed in the local Streamlit process and is not intentionally sent to an external service by this application.

AI functionality is not implemented. The AI Copilot screen is a placeholder for a later phase.

## Architecture

- `data_utils.py`: Excel loading, flexible column normalisation, parameter reading, schema diagnostics
- `compliance_engine.py`: UI-independent rules and standard findings
- `reporting.py`: reusable filters and report summaries
- `app.py`: Streamlit pages, visualisations, and downloads

This separation allows the rule engine to be reused behind a future API without depending on Streamlit.
