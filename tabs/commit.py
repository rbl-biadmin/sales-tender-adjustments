"""Review & Commit tab — step 7.

Summarises what the Sales and Tender tabs have staged, takes the mandatory
audit reason, and commits: Data Vault writes in one transaction, then the mart
stored procedures. Every outcome ends in a visible message and an audit row.

State prefix: 'cm' (widget keys, which embed the entry nonce so a successful
commit clears the form).
"""
import streamlit as st

from tabs.store_date import selection_caption
from utils.adjustments import commit_adjustments, proc_brand
from utils.audit import log_commit
from utils.entries import SOURCE, ZEROED, number_config
from utils.queries import store_hub_exists, clear_store_day_caches
from config import SALES_MEASURES, TENDER_MEASURES
from utils.state import get_selection, nonce, reset_entries, stash_flash

_SECTIONS = (("sales", "Sales", "_sa_plan", SALES_MEASURES),
             ("tender", "Tender", "_ta_plan", TENDER_MEASURES))


def _summary(label, lines, measures):
    st.markdown(f"**{label} adjustments**")
    if lines is None or lines.empty:
        st.info(f"No {label.lower()} adjustments entered — {label.lower()} will not be changed.")
        return
    zeroed = int((lines[SOURCE] == ZEROED).sum())
    st.caption(f"{len(lines)} line(s) will be written: {len(lines) - zeroed} entered"
               + (f", {zeroed} existing line(s) set to zero" if zeroed else ""))
    st.dataframe(lines, use_container_width=True, hide_index=True,
                 column_config=number_config(measures))


def _blockers(session, sel, plans):
    blockers = []
    if not any(p and not p["staged"].empty for p in plans.values()):
        blockers.append("Nothing to commit yet — enter lines on the Sales and/or Tender tab.")
    for label, p in plans.items():
        for e in (p or {}).get("errors", []):
            blockers.append(f"{label} tab: {e}")

    if sel["brand_id"] is None or sel["division_id"] is None:
        blockers.append(f"Brand '{sel['brand_name']}' / division '{sel['division_name']}' "
                        f"has no matching Data Vault reference id — raise a Jira ticket.")
    else:
        try:
            if not store_hub_exists(session, sel["store_number"], sel["brand_id"], sel["division_id"]):
                blockers.append(f"Store {sel['store_number']} was not found in the Data Vault "
                                f"store hub, so the adjustment could not be linked to it — "
                                f"raise a Jira ticket.")
        except Exception as e:
            st.warning(f"Could not verify the store in the Data Vault ({e}). "
                       f"You can still commit.")
    return blockers


def _report(session, sel, current_user, current_role, result, note):
    """Turn the commit result into one visible outcome plus one audit row."""
    n_sales = result["written"].get("sales", 0)
    n_tender = result["written"].get("tender", 0)

    if result["db_error"]:
        audit_err = log_commit(session, current_user, current_role, sel, 0, 0, note,
                               "FAILED", result["db_error"])
        st.error(f"❌ Nothing was saved — the commit was rolled back.\n\n{result['db_error']}")
        if audit_err:
            st.error(audit_err)
        return

    clear_store_day_caches()
    saved = " and ".join(f"{n} {lbl} line(s)" for n, lbl in
                         ((n_sales, "sales"), (n_tender, "tender")) if n)
    where = f"store {sel['store_number']} on {sel['date']:%d/%m/%Y}"

    if result["proc_errors"]:
        msg = " | ".join(result["proc_errors"])
        audit_err = log_commit(session, current_user, current_role, sel, n_sales, n_tender,
                               note, "PARTIAL", msg)
        # No rerun: the entries stay on screen so Commit can simply be retried —
        # re-committing rewrites the same lines and re-runs the refresh.
        st.warning(f"⚠️ Saved {saved} for {where} to the Data Vault, but the reporting "
                   f"refresh failed, so the reports do not show it yet.\n\n{msg}\n\n"
                   f"Click **Commit Changes** again to retry, or raise a Jira ticket.")
        if audit_err:
            st.error(audit_err)
        return

    audit_err = log_commit(session, current_user, current_role, sel, n_sales, n_tender,
                           note, "SUCCESS", " | ".join(result["proc_results"]))
    text = f"✅ Saved {saved} for {where}. Reports refreshed — the Store & Date tab shows the new figures."
    if audit_err:
        text += f"\n\n⚠️ {audit_err}"
    # Stashed, not written: the rerun below would discard it
    stash_flash("success", text)
    reset_entries()
    st.rerun()


def render_commit_tab(session, current_user, current_role, is_editor):
    """Render the Review & Commit tab."""
    sel = get_selection()
    if not sel:
        st.info("👈 Choose a store and date on the **Store & Date** tab first.")
        return
    st.markdown(selection_caption(sel))
    if not is_editor:
        st.warning("👁️ You have view-only access. Committing adjustments needs editor access "
                   "— see the Help tab.")
        return

    st.subheader("Step 7 — Review and commit")
    plans = {label: st.session_state.get(key) for _n, label, key, _m in _SECTIONS}
    for _name, label, key, measures in _SECTIONS:
        _summary(label, (plans[label] or {}).get("staged"), measures)

    st.divider()
    n = nonce()
    note = st.text_area("Audit reason / description (required)", key=f"cm_note_{n}",
                        max_chars=1000, height=80,
                        placeholder="Why is this adjustment needed? e.g. POS outage 7 Sep, "
                                    "sales keyed from the store's manual docket summary.")
    confirmed = st.checkbox("I have checked the before/after previews on the Sales and "
                            "Tender tabs", key=f"cm_confirm_{n}")

    blockers = _blockers(session, sel, plans)
    if blockers:
        st.warning("**Commit is not available yet:**\n\n" +
                   "\n".join(f"- {b}" for b in blockers))

    st.caption(f"On commit, the reporting refresh runs for brand `{proc_brand(sel)}`, "
               f"date `{sel['date_key']}`.")
    clicked = st.button("✅ Commit Changes", type="primary", disabled=bool(blockers),
                        use_container_width=True, key=f"cm_commit_{n}")
    if not clicked:
        return

    # Checked on click rather than by disabling the button: a text area only
    # reports its value when it loses focus, so a button disabled on "note is
    # empty" would ignore the first click after typing — silently.
    if not note.strip():
        st.error("Enter an audit reason before committing.")
        return
    if not confirmed:
        st.error("Tick the box to confirm you have checked the previews.")
        return

    staged = {name: (plans[label] or {}).get("staged") for name, label, _k, _m in _SECTIONS}
    with st.spinner("Saving adjustments and refreshing reports…"):
        result = commit_adjustments(session, sel, staged, note.strip(), current_user)
    _report(session, sel, current_user, current_role, result, note.strip())
