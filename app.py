import io
import zipfile
import hmac
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

st.set_page_config(page_title="Touche Hairdressing — Statements", page_icon="🧾", layout="centered")

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

brand = "Touche Hairdressing"

st.title("🧾 Touche Hairdressing — Stylist Statements")
st.write(
    "Upload any of the following pairs:\n"
    "- **Till + SE** → generates *Client Statements*\n"
    "- **Service Sales + Service Cost** → generates *Services Statements*\n"
    "- Upload **all 4** to generate both sections in the PDFs and in the Excel output."
)

with st.sidebar:
    st.header("Inputs — Till + SE (optional)")
    till_file = st.file_uploader("Till Report (.xls)", type=["xls"])
    se_file = st.file_uploader("SE Report (.xls)", type=["xls"])

    st.divider()
    st.header("Inputs — Service Sales (optional)")
    services_file = st.file_uploader("Service Sales report (.xls)", type=["xls"])
    services_cost_file = st.file_uploader("Services cost (.xlsx)", type=["xlsx"])

    st.divider()
    include_cleaned = st.checkbox("Include cleaned tabs in Excel output", value=True)

has_clients = till_file is not None and se_file is not None
has_services = services_file is not None and services_cost_file is not None

# Helpful guidance if a pair is incomplete
if (till_file is not None) ^ (se_file is not None):
    st.warning("To produce Client Statements, upload **both** Till Report and SE Report.")
if (services_file is not None) ^ (services_cost_file is not None):
    st.warning("To produce Services Statements, upload **both** Service Sales and Services cost.")

if not (has_clients or has_services):
    st.info("Upload **Till + SE** and/or **Service Sales + Service Cost** to begin.")
    st.stop()

try:
    merged_clients = None
    recon = None
    p_start, p_end = "", ""

    if has_clients:
        till_df = format_till_report(till_file)
        se_df = format_se_report(se_file)
        merged_clients = merge_se_with_till(se_df, till_df)
        recon = reconciliation_summary(merged_clients)
        p_start, p_end = statement_period(merged_clients)

        st.subheader("Client Statements — Reconciliation summary")
        st.dataframe(recon, use_container_width=True)
        st.subheader("Client Statements — Preview")
        st.dataframe(merged_clients.head(50), use_container_width=True)

    services_df = None
    if has_services:
        services_df = convert_service_sales(services_file, services_cost_file)
        st.subheader("Services Statements — Preview")
        st.dataframe(services_df.head(50), use_container_width=True)

    # ---- OUTPUT EXCEL ----
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        if has_clients:
            merged_clients.to_excel(writer, index=False, sheet_name="Client Statements")
            if recon is not None:
                recon.to_excel(writer, index=False, sheet_name="Reconciliation Summary")
            if include_cleaned:
                till_df.to_excel(writer, index=False, sheet_name="Till Cleaned")
                se_df.to_excel(writer, index=False, sheet_name="SE Cleaned")

        if has_services:
            services_df.to_excel(writer, index=False, sheet_name="Service Statements")
            if include_cleaned:
                # convert_service_sales already outputs final; raw cleaned tabs handled inside its own process historically
                pass

    out.seek(0)
    st.download_button(
        "Download Excel output (.xlsx)",
        data=out,
        file_name="Touche Stylist Statements.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # ---- OUTPUT PDFs ----
    st.subheader("PDF statements")
    st.caption("One PDF per stylist, packaged into a single ZIP.")

    if st.button("Generate ZIP of PDFs"):
        # Determine stylists from whichever dataset(s) exist
        stylists = set()
        if has_clients:
            stylists |= set(merged_clients["Stylist"].dropna().astype(str).unique())
        if has_services:
            stylists |= set(services_df["Stylist"].dropna().astype(str).unique())
        stylists = sorted(stylists)

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
            for stylist in stylists:
                s_services = services_df[services_df["Stylist"] == stylist].copy() if has_services else None
                s_clients = merged_clients[merged_clients["Stylist"] == stylist].copy() if has_clients else None

                pdf_bytes = build_stylist_statement_pdf(
                    brand=brand,
                    stylist=stylist,
                    period_start=p_start,
                    period_end=p_end,
                    services_df=s_services,
                    clients_df=s_clients,
                )

                safe = "".join(ch for ch in stylist if ch.isalnum() or ch in (" ", "-", "_")).strip().replace(" ", "_")
                z.writestr(f"{safe}.pdf", pdf_bytes)

        zip_buf.seek(0)
        st.download_button(
            "Download ZIP of PDFs",
            data=zip_buf,
            file_name="Touche Stylist Statements (PDF).zip",
            mime="application/zip",
        )

except Exception as e:
    st.error("Processing failed.")
    st.exception(e)
