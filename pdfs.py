import io
import pandas as pd
from typing import Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet

def _money(x) -> str:
    try:
        if pd.isna(x):
            return ""
        return f"£{float(x):,.2f}"
    except Exception:
        return ""

def _dt(x) -> str:
    try:
        if pd.isna(x):
            return ""
        ts = pd.to_datetime(x)
        return ts.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(x)

def build_stylist_statement_pdf(
    brand: str,
    stylist: str,
    period_start: str,
    period_end: str,
    services_df: Optional[pd.DataFrame],
    clients_df: Optional[pd.DataFrame],
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18*mm,
        rightMargin=18*mm,
        topMargin=16*mm,
        bottomMargin=16*mm,
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"<b>{brand} — {stylist}</b>", styles["Title"]))
    story.append(Spacer(1, 6))
    if period_start and period_end:
        story.append(Paragraph(f"Statement period: {period_start} to {period_end}", styles["Normal"]))
    story.append(Spacer(1, 12))

    include_services = services_df is not None and not services_df.empty
    include_clients = clients_df is not None and not clients_df.empty

    # SERVICES SECTION (only if provided)
    if include_services:
        story.append(Paragraph(f"<b>{stylist} Services</b>", styles["Heading2"]))
        story.append(Spacer(1, 6))

        sdf = services_df[["Description", "Qty", "Per Service", "Total"]].copy()
        sdf["Qty"] = sdf["Qty"].astype(int)
        sdf["Per Service"] = sdf["Per Service"].apply(_money)
        sdf["Total"] = sdf["Total"].apply(_money)

        data = [["Description", "Qty", "Per Service", "Total"]] + sdf.values.tolist()
        t = Table(data, colWidths=[92*mm, 16*mm, 28*mm, 28*mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("ALIGN", (1,1), (1,-1), "RIGHT"),
            ("ALIGN", (2,1), (3,-1), "RIGHT"),
        ]))
        story.append(t)

        tot_qty = int(services_df["Qty"].fillna(0).sum())
        tot_val = services_df["Total"].fillna(0).sum()
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>Services total:</b> Qty {tot_qty}, Value {_money(tot_val)}", styles["Normal"]))
        story.append(Spacer(1, 12))

        if include_clients:
            story.append(PageBreak())

    # CLIENT SECTION (only if provided)
    if include_clients:
        story.append(Paragraph(f"<b>{stylist} Client Statement</b>", styles["Heading2"]))
        story.append(Spacer(1, 6))

        cdf = clients_df.copy()
        deposit_col = "Deposit" if "Deposit" in cdf.columns else ("Prepaid" if "Prepaid" in cdf.columns else None)
        if deposit_col is None:
            cdf["Deposit"] = 0.0
            deposit_col = "Deposit"

        cdf = cdf[["Date", "Client", "Cash1", deposit_col]].copy()
        cdf.rename(columns={deposit_col: "Deposit"}, inplace=True)

        cdf["Date"] = cdf["Date"].apply(_dt)
        cdf["Cash1"] = cdf["Cash1"].apply(_money)
        cdf["Deposit"] = cdf["Deposit"].apply(_money)

        data = [["Date/Time", "Client", "Cash1", "Deposit"]] + cdf.values.tolist()
        t = Table(data, colWidths=[34*mm, 76*mm, 30*mm, 30*mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("ALIGN", (2,1), (3,-1), "RIGHT"),
        ]))
        story.append(t)

        cash1_sum = clients_df["Cash1"].fillna(0).sum()
        dep_sum = clients_df[deposit_col].fillna(0).sum() if deposit_col in clients_df.columns else 0.0
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"<b>Client totals:</b> Cash1 {_money(cash1_sum)} | Deposit {_money(dep_sum)} | Combined {_money(cash1_sum + dep_sum)}",
            styles["Normal"]
        ))

    # If neither section provided, show a polite message (shouldn't happen, but safe)
    if not include_services and not include_clients:
        story.append(Paragraph("No statement data provided for this stylist.", styles["Italic"]))

    doc.build(story)
    return buf.getvalue()
