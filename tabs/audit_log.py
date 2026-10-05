"""Audit Log tab — one row per commit attempt, newest first."""
from datetime import datetime

import streamlit as st

from config import DB_AUDIT_LOG


def render_audit_log_tab(session, is_editor):
    """Render the Audit Log tab (editors only — it holds store names and notes
    across every store, regardless of the viewer's store access)."""
    st.header("Audit Log")
    if not is_editor:
        st.warning("👀 Only editors and admins can view the audit log")
        return

    try:
        audit_df = session.sql(f"""
            SELECT TIMESTAMP, USER_NAME, USER_ROLE, DIVISION, BRAND, STORE_NUMBER,
                   STORE_NAME, ADJUSTMENT_DATE, SALES_LINES, TENDER_LINES, AUDIT_NOTE,
                   OUTCOME, MESSAGE
            FROM {DB_AUDIT_LOG}
            ORDER BY TIMESTAMP DESC
            LIMIT 1000
        """).to_pandas()
    except Exception as e:
        st.error(f"Error loading audit log: {str(e)}")
        st.info("The audit log table may not exist yet — see setup/snowflake_setup.sql.")
        return

    if audit_df.empty:
        st.info("No audit records yet.")
        return

    st.dataframe(
        audit_df, use_container_width=True, height=500, hide_index=True,
        column_config={
            "TIMESTAMP": st.column_config.DatetimeColumn("When", format="DD/MM/YYYY HH:mm:ss"),
            "USER_NAME": "User",
            "USER_ROLE": "Role",
            "DIVISION": "Division",
            "BRAND": "Brand",
            "STORE_NUMBER": "Store",
            "STORE_NAME": "Store Name",
            "ADJUSTMENT_DATE": st.column_config.DateColumn("Adjustment Date", format="DD/MM/YYYY"),
            "SALES_LINES": "Sales Lines",
            "TENDER_LINES": "Tender Lines",
            "AUDIT_NOTE": "Audit Note",
            "OUTCOME": "Outcome",
            "MESSAGE": "Message",
        },
    )
    st.download_button(
        label="📥 Download Audit Log (CSV)",
        data=audit_df.to_csv(index=False),
        file_name=f"adjustments_audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )
