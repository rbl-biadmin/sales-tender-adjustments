"""Sales Adjustments tab — steps 3 and 4.

Step 3: enter one or more sales adjustment lines for the active store/day.
Step 4: preview the day's sales as they will be after the commit.

State prefix: 'sa'.
"""
import streamlit as st

from config import SALES_MEASURES, GST_INCLUSIVE_DIVISIONS
from tabs.store_date import selection_caption
from utils.entries import (
    CHANNEL, channel_options, render_entry_grid, build_preview, changed_mask,
    highlight_rows, preview_formats, with_total, number_config,
)
from utils.queries import load_store_day, load_channel_pairs
from utils.state import get_selection, nonce

UI_KEYS = [CHANNEL]
KEY_LABELS = {CHANNEL: "channel"}
DATA_KEYS = ["ORDER_CHANNEL", "DELIVERY_CHANNEL"]
MEASURES = list(SALES_MEASURES)
# The reporting tables combine promos with discount, so the preview compares
# like with like: promos folded into DISCOUNT, no separate promo column.
PREVIEW_MEASURES = [m for m in MEASURES if m != "PROMOS"]


def _fold_promos(df):
    if df is None or df.empty or "PROMOS" not in df.columns:
        return df
    out = df.copy()
    out["DISCOUNT"] = out["DISCOUNT"] + out["PROMOS"]
    return out


def _net(df):
    """Report net sales — the same formula as RPT_DAILY_STORE_SALES."""
    return (df["AMOUNT"] - df["GIFT_CARD"] + df["DELIVERY_FEES"]
            - df["BOTTLE_FEE"] - df["GUAM_GST"] - df["TB_FUND"])


def _preview(sel, base, existing, staged):
    st.subheader("Step 4 — Check the result")
    if staged.empty:
        st.caption("Enter at least one line above to see the before/after preview.")
        return

    cur, new = build_preview(base, _fold_promos(existing), _fold_promos(staged), DATA_KEYS,
                             PREVIEW_MEASURES, extra_base_cols=["GUAM_GST"])
    cur_net, new_net = _net(cur), _net(new)

    m1, m2, m3 = st.columns(3)
    m1.metric("Report Net Sales", f"{new_net.sum():,.2f}",
              f"{new_net.sum() - cur_net.sum():+,.2f}")
    m2.metric("Transactions", f"{new['TRANSACTIONS'].sum():,.0f}",
              f"{new['TRANSACTIONS'].sum() - cur['TRANSACTIONS'].sum():+,.0f}")
    m3.metric("Amount", f"{new['AMOUNT'].sum():,.2f}",
              f"{new['AMOUNT'].sum() - cur['AMOUNT'].sum():+,.2f}")

    out = new[PREVIEW_MEASURES].copy()
    out["CURRENT_NET"] = cur_net
    out["NEW_NET"] = new_net
    out["CHANGE"] = new_net - cur_net
    out = out.reset_index()
    mask = changed_mask(cur, new, PREVIEW_MEASURES).reset_index(drop=True)
    num_cols = PREVIEW_MEASURES + ["CURRENT_NET", "NEW_NET", "CHANGE"]
    out = with_total(out, "ORDER_CHANNEL", num_cols)

    labels = {f: f"New {lbl}" for f, (lbl, _c, _d) in SALES_MEASURES.items()}
    labels["DISCOUNT"] = "New Discount (incl. Promos)"
    cfg = number_config(SALES_MEASURES, labels)
    cfg["CURRENT_NET"] = st.column_config.NumberColumn("Current Net Sales", format="%.2f")
    cfg["NEW_NET"] = st.column_config.NumberColumn("New Net Sales", format="%.2f")
    cfg["CHANGE"] = st.column_config.NumberColumn("Change", format="%+.2f")
    fmts = preview_formats(SALES_MEASURES, {"CURRENT_NET": "{:,.2f}", "NEW_NET": "{:,.2f}",
                                            "CHANGE": "{:+,.2f}"})
    st.dataframe(highlight_rows(out, mask, fmts), use_container_width=True, hide_index=True,
                 column_config=cfg)
    st.caption("Highlighted rows change. New = current figures − existing adjustments "
               "+ the lines above (existing adjustments are replaced, not added to).")
    if sel["division_name"] in GST_INCLUSIVE_DIVISIONS:
        st.caption("ℹ️ Guam: the preview uses the Amount as entered (incl. GST). GST is "
                   "calculated and removed from net sales when the adjustment is loaded, "
                   "so the final Report Net Sales will be lower than shown here.")


def render_sales_tab(session, is_editor):
    """Render the Sales Adjustments tab."""
    sel = get_selection()
    if not sel:
        st.info("👈 Choose a store and date on the **Store & Date** tab first.")
        return
    st.markdown(selection_caption(sel))
    if not is_editor:
        st.warning("👁️ You have view-only access. Entering adjustments needs editor access "
                   "— see the Help tab.")
        return

    st.subheader("Step 3 — Enter sales adjustments")
    notes = ("- Enter the **change** to apply — values can be positive or negative.\n"
             "- Pick the order/delivery channel pair, or **Adjustment | Adjustment** for a "
             "general day adjustment where the channel is not known.\n"
             "- Blank cells count as 0. Add as many lines as you need.\n"
             "- ⚠️ Any existing sales adjustments for this store/day will be **overwritten**.")
    if sel["division_name"] in GST_INCLUSIVE_DIVISIONS:
        notes += ("\n- 🇬🇺 **Guam: enter Amount incl. GST.** GST is calculated and removed "
                  "from net sales on loading.")
    st.info(notes)

    data = load_store_day(session, sel)
    base, existing = data["sales"], data["sales_adj"]
    pairs = load_channel_pairs(session, sel["store_key"])

    key_config = {CHANNEL: st.column_config.SelectboxColumn(
        "Order | Delivery Channel", options=channel_options(pairs, base, existing),
        width="large")}
    plan = render_entry_grid("sa", nonce(), "sales", UI_KEYS, KEY_LABELS, key_config,
                             DATA_KEYS, SALES_MEASURES, existing)

    st.divider()
    _preview(sel, base, existing, plan["staged"])
