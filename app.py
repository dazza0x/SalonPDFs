
import io, zipfile, hmac
import pandas as pd
import streamlit as st

from transform import (
    convert_service_sales,
    format_till_report,
    format_se_report,
    merge_se_with_till,
    reconciliation_summary,
    statement_period,
)
from pdfs import build_stylist_statement_pdf

st.set_page_config(page_title="Touche Stylist Statements", page_icon="🧾", layout="centered")

def _maybe_require_password():
    # Password protection is mandatory for this app.
    if "auth" not in st.secrets or "password" not in st.secrets["auth"]:
        st.error(
            "Password protection is not configured. Add an app secret named "
            "`auth.password` in Streamlit Community Cloud (App settings → Secrets)."
        )
        st.stop()

    if st.session_state.get("authenticated"):
        return

    st.sidebar.subheader("🔒 Access")
    pw = st.sidebar.text_input("Password", type="password")
    correct = st.secrets["auth"]["password"]

    if pw and hmac.compare_digest(pw, correct):
        st.session_state["authenticated"] = True
        st.sidebar.success("Access granted")
        return
    if pw:
        st.sidebar.error("Incorrect password")
    st.stop()

_maybe_require_password()


brand = "Touche Hair Caterham"

st.title("🧾 Touche Hair Caterham — Stylist Statements")
st.write("Upload all three source reports (Till, SE, and Service Sales) plus the Services Cost file. Download Excel + a ZIP of per-stylist PDF statements.")

with st.sidebar:
    st.header("Inputs — Till + SE")
    till_file = st.file_uploader("Till Report (.xls)", type=["xls"])
    se_file = st.file_uploader("SE Report (.xls)", type=["xls"])

    st.divider()
    st.header("Inputs — Service Sales (required)")
    services_file = st.file_uploader("Service Sales report (.xls)", type=["xls"])
    services_cost_file = st.file_uploader("Services cost (.xlsx) — required", type=["xlsx"])

    st.divider()
    include_cleaned = st.checkbox("Include cleaned tabs in Excel output", value=True)

if till_file is None or se_file is None or services_file is None or services_cost_file is None:
    st.info("Upload Till Report (.xls), SE Report (.xls), Service Sales (.xls), and Services cost (.xlsx) to begin.")
    st.stop()

try:
    till_df = format_till_report(till_file)
    se_df = format_se_report(se_file)
    merged_clients = merge_se_with_till(se_df, till_df)
    recon = reconciliation_summary(merged_clients)
    p_start, p_end = statement_period(merged_clients)

    services_df = convert_service_sales(services_file, services_cost_file)

    st.subheader("Reconciliation summary")
    st.caption("Eyeball check: Cash1 + Deposit should match your other system.")
    st.dataframe(recon, use_container_width=True)

    st.subheader("Merged client output (preview)")
    st.dataframe(merged_clients.head(50), use_container_width=True)
    st.subheader("Service sales output (preview)")
    st.dataframe(services_df.head(50), use_container_width=True)

    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        merged_clients.to_excel(writer, index=False, sheet_name="Client Merged Output")
        recon.to_excel(writer, index=False, sheet_name="Reconciliation Summary")
        services_df.to_excel(writer, index=False, sheet_name="Service Sales Output")
        if include_cleaned:
            se_df.to_excel(writer, index=False, sheet_name="SE Cleaned")
            till_df.to_excel(writer, index=False, sheet_name="Till Cleaned")
    excel_buf.seek(0)

    st.download_button(
        "Download Excel output (.xlsx)",
        data=excel_buf,
        file_name="Touche Statements Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.subheader("PDF statements")
    if st.button("Generate ZIP of stylist PDFs"):
        stylists = set(merged_clients["Stylist"].dropna().astype(str))
        stylists |= set(services_df["Stylist"].dropna().astype(str))

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
            for stylist in sorted(stylists):
                s_clients = merged_clients[merged_clients["Stylist"] == stylist].copy()
                s_services = services_df[services_df["Stylist"] == stylist].copy()

                pdf_bytes = build_stylist_statement_pdf(
                    brand=brand,
                    stylist=stylist,
                    period_start=p_start,
                    period_end=p_end,
                    services_df=s_services,
                    clients_df=s_clients,
                )
                safe = "".join(ch for ch in stylist if ch.isalnum() or ch in (" ","-","_")).strip().replace(" ","_")
                z.writestr(f"{safe}.pdf", pdf_bytes)

        zip_buf.seek(0)
        st.download_button(
            "Download ZIP of PDFs",
            data=zip_buf,
            file_name="Stylist Statements.zip",
            mime="application/zip",
        )

except Exception as e:
    st.error("Processing failed.")
    st.exception(e)
