# Touche Hair Caterham — Stylist Statements (Streamlit)

## What it does
- Builds Till + SE merged output using a raw Excel datetime join (DateKey + Client)
- Converts Service Sales (required input) report and enriches with services cost.xlsx
- Produces:
  - One Excel output workbook (merged output + reconciliation + required service output + required cleaned tabs)
  - A ZIP of per-stylist PDFs, each containing:
    1) "{Stylist} Services"
    2) "{Stylist} Client Statement"

## Inputs
Required:
- Till Report.xls (sheet: Till Audit Report)
- SE Report.xls (sheet: TillAudit)

Optional:
- Service Sales report .xls (sheet: Service Sales by Team Mem)
- services cost.xlsx (columns: Service Description, Per Service)

## Deploy
- Main file: app.py
- Python: 3.12 recommended
