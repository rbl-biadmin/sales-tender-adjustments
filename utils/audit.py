"""App audit log — one summary row per commit attempt.

The Data Vault already holds the user and audit note for every successful
commit (S_ADJUSTMENTS_AUDIT). This log adds what the vault cannot: failed and
rolled-back attempts, and the outcome of the mart stored procedures. It is
written on every commit path, including the ones that error early.
"""
from config import RECORD_SOURCE, DB_AUDIT_LOG
from utils.sql import q


def log_commit(session, current_user, current_role, sel, sales_lines,
               tender_lines, audit_note, outcome, message):
    """Insert one audit row. ``current_user`` is the viewer — never CURRENT_USER().

    Returns None, or an error message for the caller to show. Never raises: a
    broken audit insert must not undo a successful data write. It returns the
    message rather than calling st.error because the success path ends in an
    st.rerun(), which would discard it — the caller folds it into the flash.
    """
    try:
        session.sql(f"""
            INSERT INTO {DB_AUDIT_LOG}
                (USER_NAME, USER_ROLE, DIVISION, BRAND, STORE_NUMBER, STORE_NAME,
                 ADJUSTMENT_DATE, SALES_LINES, TENDER_LINES, AUDIT_NOTE,
                 OUTCOME, MESSAGE, RECORD_SOURCE)
            SELECT {q(current_user)}, {q(current_role)},
                   {q(sel['division_name'])}, {q(sel['brand_name'])},
                   {q(sel['store_number'])}, {q(sel['store_name'])},
                   {q(sel['date_str'])}::DATE, {int(sales_lines)}, {int(tender_lines)},
                   {q(audit_note)}, {q(outcome)}, {q(message or '')},
                   {q(RECORD_SOURCE)}
        """).collect()
        return None
    except Exception as e:
        return f"Audit log failed: {str(e)}"
