"""Tender Adjustments tab — steps 5 and 6.

Step 5: enter one or more tender adjustment lines for the active store/day.
Step 6: preview the day's tenders as they will be after the commit.

State prefix: 'ta'.
"""
import streamlit as st

from config import TENDER_MEASURES
from tabs.store_date import selection_caption
from utils.entries import (
    CHANNEL, channel_options, payment_options, render_entry_grid, build_preview,
    changed_mask, highlight_rows, preview_formats, with_total, number_config,
)
from utils.queries import load_store_day, load_channel_pairs, load_payment_types
from utils.state import get_selection, nonce

UI_KEYS = ["PAYMENT_TYPE", CHANNEL]
KEY_LABELS = {"PAYMENT_TYPE": "payment type", CHANNEL: "channel"}
DATA_KEYS = ["PAYMENT_TYPE", "ORDER_CHANNEL", "DELIVERY_CHANNEL"]
MEASURES = list(TENDER_MEASURES)


def _preview(base, existing, staged):
    st.subheader("Step 6 — Check the result")
    if staged.empty:
        st.caption("Enter at least one line above to see the before/after preview.")
        return

    cur, new = build_preview(base, existing, staged, DATA_KEYS, MEASURES)

    m1, m2 = st.columns(2)
    for col, field in ((m1, "TENDER_AMOUNT"), (m2, "TIP_AMOUNT")):
        col.metric(TENDER_MEASURES[field][0], f"{new[field].sum():,.2f}",
                   f"{new[field].sum() - cur[field].sum():+,.2f}")

    out = new[MEASURES].copy()
    out["CURRENT_TENDER"] = cur["TENDER_AMOUNT"]
    out["CHANGE"] = new["TENDER_AMOUNT"] - cur["TENDER_AMOUNT"]
    out = out.reset_index()
    mask = changed_mask(cur, new, MEASURES).reset_index(drop=True)
    out = with_total(out, "PAYMENT_TYPE", MEASURES + ["CURRENT_TENDER", "CHANGE"])

    cfg = number_config(TENDER_MEASURES, {f: f"New {lbl}" for f, (lbl, _c, _d) in TENDER_MEASURES.items()})
    cfg["CURRENT_TENDER"] = st.column_config.NumberColumn("Current Tender Amount")
    cfg["CHANGE"] = st.column_config.NumberColumn("Tender Change")
    fmts = preview_formats(TENDER_MEASURES, {"CURRENT_TENDER": "{:,.2f}", "CHANGE": "{:+,.2f}"})
    st.dataframe(highlight_rows(out, mask, fmts), use_container_width=True, hide_index=True,
                 column_config=cfg)
    st.caption("Highlighted rows change. New = current figures − existing adjustments "
               "+ the lines above (existing adjustments are replaced, not added to).")


def render_tender_tab(session, is_editor):
    """Render the Tender Adjustments tab."""
    sel = get_selection()
    if not sel:
        st.info("👈 Choose a store and date on the **Store & Date** tab first.")
        return
    st.markdown(selection_caption(sel))
    if not is_editor:
        st.warning("👁️ You have view-only access. Entering adjustments needs editor access "
                   "— see the Help tab.")
        return

    st.subheader("Step 5 — Enter tender adjustments")
    st.info("- Enter the **change** to apply — values can be positive or negative.\n"
            "- **All amounts incl. tax / GST.**\n"
            "- Pick the payment type and order/delivery channel pair, or **Adjustment** "
            "where the payment type or channel is not known.\n"
            "- Blank cells count as 0. Add as many lines as you need.\n"
            "- ⚠️ Any existing tender adjustments for this store/day will be **overwritten**.")

    data = load_store_day(session, sel)
    base, existing = data["tenders"], data["tender_adj"]
    pairs = load_channel_pairs(session, sel["store_key"])
    types = load_payment_types(session, sel["store_key"])

    key_config = {
        "PAYMENT_TYPE": st.column_config.SelectboxColumn(
            "Payment Type", options=payment_options(types, base, existing)),
        CHANNEL: st.column_config.SelectboxColumn(
            "Order | Delivery Channel", options=channel_options(pairs, base, existing),
            width="large"),
    }
    plan = render_entry_grid("ta", nonce(), "tender", UI_KEYS, KEY_LABELS, key_config,
                             DATA_KEYS, TENDER_MEASURES, existing)

    st.divider()
    _preview(base, existing, plan["staged"])
