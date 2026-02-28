
import numpy as np
import pandas as pd
import xlrd
from datetime import datetime

EXCEL_EPOCH = datetime(1899, 12, 30)

def _clean_text(x):
    if x is None:
        return None
    s = str(x)
    s = s.replace("\u00a0", " ")
    s = "".join(ch for ch in s if ord(ch) >= 32)
    for ch in ["\u2010","\u2011","\u2012","\u2013","\u2014","\u2212"]:
        s = s.replace(ch, "-")
    return s.strip()

def _to_number(x):
    if x is None:
        return np.nan
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    s = _clean_text(x)
    if s in ("", "nan", "None"):
        return np.nan
    s = s.replace("£","").replace(",","")
    try:
        return float(s)
    except Exception:
        return np.nan

def _excel_serial_to_datetime(serial: float, datemode: int) -> datetime:
    return xlrd.xldate.xldate_as_datetime(serial, datemode)

def _datetime_to_excel_serial(dt: datetime) -> float:
    delta = dt - EXCEL_EPOCH
    return delta.days + (delta.seconds + delta.microseconds/1e6) / 86400.0

def _date_key(v, datemode: int):
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return round(float(v) * 86400) / 86400.0
    if isinstance(v, datetime):
        return round(_datetime_to_excel_serial(v) * 86400) / 86400.0
    s = _clean_text(v)
    if not s:
        return None
    dt = pd.to_datetime(s, errors="coerce", yearfirst=True, dayfirst=False)
    if pd.isna(dt):
        dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if pd.isna(dt):
        return None
    return round(_datetime_to_excel_serial(dt.to_pydatetime()) * 86400) / 86400.0

def _date_display(v, datemode: int):
    if v is None:
        return pd.NaT
    if isinstance(v, datetime):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        try:
            return _excel_serial_to_datetime(float(v), datemode)
        except Exception:
            return pd.NaT
    s = _clean_text(v)
    if not s:
        return pd.NaT
    dt = pd.to_datetime(s, errors="coerce", yearfirst=True, dayfirst=False)
    if pd.isna(dt):
        dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if pd.isna(dt):
        return pd.NaT
    return dt.to_pydatetime()

def _read_xls_sheet(file_or_path, sheet_name: str):
    if hasattr(file_or_path, "read"):
        data = file_or_path.read()
        book = xlrd.open_workbook(file_contents=data)
    else:
        book = xlrd.open_workbook(file_or_path)
    sh = book.sheet_by_name(sheet_name)
    datemode = book.datemode
    rows = [sh.row_values(r) for r in range(sh.nrows)]
    return datemode, rows

def _promote_headers(rows):
    headers = [str(h).strip() for h in rows[0]]
    data = rows[1:]
    return headers, data

# ---------- Service Sales ----------
def _load_cost_table(cost_path_or_file) -> pd.DataFrame:
    cost = pd.read_excel(cost_path_or_file)
    required = {'Service Description', 'Per Service'}
    missing = required - set(cost.columns)
    if missing:
        raise ValueError(f"Services cost file missing columns: {', '.join(sorted(missing))}")
    cost = cost[['Service Description', 'Per Service']].copy()
    cost['Service Description'] = cost['Service Description'].astype(str).str.strip()
    cost['Per Service'] = pd.to_numeric(cost['Per Service'], errors='coerce')
    return cost

def convert_service_sales(input_path_or_file, cost_path_or_file=None) -> pd.DataFrame:
    df_raw = pd.read_excel(input_path_or_file, sheet_name='Service Sales by Team Mem', header=None)
    sel = df_raw[[1, 7, 11, 13]].copy()
    sel.columns = ['Description', 'Qty', 'Exc Vat', 'Inc Vat']
    sel = sel[sel['Description'].notna()]
    sel = sel[~sel['Description'].isin(['Hair', 'Treatment'])]

    headers = sel.iloc[0].tolist()
    df = sel.iloc[1:].copy()
    df.columns = headers

    df['Description'] = df['Description'].astype(str).str.strip()
    df['Qty'] = pd.to_numeric(df['Qty'], errors='coerce')
    df['Exc Vat'] = pd.to_numeric(df['Exc Vat'], errors='coerce')
    df['Inc Vat'] = pd.to_numeric(df['Inc Vat'], errors='coerce')

    df['Stylist'] = np.where(df['Qty'].isna(), df['Description'], np.nan)
    df['Stylist'] = df['Stylist'][::-1].ffill()[::-1]
    df = df[df['Qty'].notna()].copy()
    df['Qty'] = df['Qty'].astype(int)
    df['Stylist'] = df['Stylist'].astype(str).str.strip()

    if cost_path_or_file is not None:
        cost = _load_cost_table(cost_path_or_file)
        df = df.merge(cost, how='left', left_on='Description', right_on='Service Description')
        df.drop(columns=['Service Description'], inplace=True)
        df['Total'] = df['Qty'] * df['Per Service']
    else:
        df['Per Service'] = np.nan
        df['Total'] = np.nan

    return df[['Stylist', 'Description', 'Qty', 'Per Service', 'Total']].reset_index(drop=True)

# ---------- Till + SE ----------
def format_till_report(input_path_or_file) -> pd.DataFrame:
    datemode, rows = _read_xls_sheet(input_path_or_file, "Till Audit Report")
    keep_idx = [1, 3, 6, 8, 9, 10, 11, 14]
    kept = [[r[i] if i < len(r) else None for i in keep_idx] for r in rows]

    def _not_blank(x):
        if x is None: return False
        if isinstance(x, float) and np.isnan(x): return False
        return _clean_text(x) != ""
    kept = [r for r in kept if _not_blank(r[0])]

    headers, data = _promote_headers(kept)
    df = pd.DataFrame(data, columns=headers)

    df["DateKey"] = df["Date"].apply(lambda v: _date_key(v, datemode))
    df["Date"] = df["Date"].apply(lambda v: _date_display(v, datemode))
    df["Client"] = df["Client"].apply(_clean_text)

    for c in ["Cash", "Cash1", "Deposits", "Gift Cards", "Other Card", "Total"]:
        if c in df.columns:
            df[c] = df[c].apply(_to_number)

    return df.reset_index(drop=True)

def format_se_report(input_path_or_file) -> pd.DataFrame:
    datemode, rows = _read_xls_sheet(input_path_or_file, "TillAudit")
    keep_idx = [1, 4, 10, 12, 15, 18, 21, 24]
    kept = [[r[i] if i < len(r) else None for i in keep_idx] for r in rows]

    def _not_blank(x):
        if x is None: return False
        if isinstance(x, float) and np.isnan(x): return False
        return _clean_text(x) != ""
    kept = [r for r in kept if _not_blank(r[0])]

    headers, data = _promote_headers(kept)
    df = pd.DataFrame(data, columns=headers)

    df["Date_raw"] = df["Date"].apply(_clean_text)

    disclaimers = {
        "If a client name is highlighted in RED then more than one team member has worked on this client/Bill",
        "Services and Retail figures inc Vat",
        "This report is for a analysis only. Please check with HMRC or National Hairdressers Federation regarding Self Employed Regulations. PDQ charges are calculated on whole bill regardless on how many team members worked on the bill.",
        "This report is for a analysis only. Please check with HMRC or National Hairdressers Federation regarding Self Employed Regulations. PDQ charges are calculated on whole bill regardless on how many team members worked on the bill. ",
    }
    df = df[~df["Date_raw"].isin(disclaimers)].copy()

    df["Client"] = df["Client"].apply(_clean_text)

    for c in ["Cash", "Cards", "Other", "Total", "Services", "Retail"]:
        if c in df.columns:
            df[c] = df[c].apply(_to_number)

    is_txn = df["Client"].notna() & (df["Client"] != "")
    df["Stylist"] = np.where(~is_txn, df["Date_raw"], np.nan)
    df["Stylist"] = pd.Series(df["Stylist"]).ffill().apply(_clean_text)

    df.loc[is_txn, "DateKey"] = df.loc[is_txn, "Date"].apply(lambda v: _date_key(v, datemode))
    df.loc[is_txn, "Date"] = df.loc[is_txn, "Date"].apply(lambda v: _date_display(v, datemode))

    df = df[is_txn].copy()
    return df[["Stylist","Date_raw","Date","DateKey","Client","Cash","Cards","Other","Total","Services","Retail"]].reset_index(drop=True)

def merge_se_with_till(se_df: pd.DataFrame, till_df: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join SE rows to Till rows using raw Excel DateKey + Client.
    Handles optional Till columns (e.g., Gift Cards / Other Card may be absent for some periods).
    Produces:
      - Cash1 (calculated)
      - Deposit (Deposits + Gift Cards; missing treated as 0)
      - Check_Total = Cash1 + Deposit
    """
    for col in ["Cash1", "Deposits", "Gift Cards", "Other Card"]:
        if col not in till_df.columns:
            till_df[col] = 0.0

    till_sub = till_df[["DateKey", "Client", "Cash1", "Deposits", "Gift Cards", "Other Card"]].copy()

    merged = se_df.merge(
        till_sub,
        how="left",
        on=["DateKey", "Client"],
    )

    for c in ["Cash1", "Deposits", "Gift Cards", "Other Card"]:
        merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0.0)
    for c in ["Cash", "Cards", "Retail"]:
        if c in merged.columns:
            merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0.0)

    merged["Cash1_calc"] = (merged["Cash1"] + merged["Cash"]) - (merged["Retail"] - merged["Cards"])
    merged["Deposit"] = merged["Deposits"] + merged["Gift Cards"]
    merged["Check_Total"] = merged["Cash1_calc"] + merged["Deposit"]

    out = merged[["Stylist", "Date", "Client", "Cash1_calc", "Deposit", "Check_Total"]].copy()
    out.rename(columns={"Cash1_calc": "Cash1"}, inplace=True)

    out = out.sort_values(["Stylist", "Date"], ascending=[True, True]).reset_index(drop=True)
    return out

def reconciliation_summary(merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-stylist reconciliation totals. Uses Deposit (not Prepaid) and includes a TOTAL row.
    """
    g = merged_df.groupby("Stylist", dropna=False).agg(
        Cash1=("Cash1", "sum"),
        Deposit=("Deposit", "sum"),
        Check_Total=("Check_Total", "sum"),
        Rows=("Stylist", "size"),
        First_Date=("Date", "min"),
        Last_Date=("Date", "max"),
    ).reset_index()

    total = pd.DataFrame([{
        "Stylist": "TOTAL",
        "Cash1": g["Cash1"].sum(),
        "Deposit": g["Deposit"].sum(),
        "Check_Total": g["Check_Total"].sum(),
        "Rows": g["Rows"].sum(),
        "First_Date": merged_df["Date"].min(),
        "Last_Date": merged_df["Date"].max(),
    }])
    return pd.concat([g, total], ignore_index=True)

def statement_period(df: pd.DataFrame):
    if df is None or df.empty:
        return ("","")
    d = pd.to_datetime(df["Date"], errors="coerce")
    return (d.min().strftime("%d/%m/%Y"), d.max().strftime("%d/%m/%Y"))
