"""Store & Date tab — steps 1 and 2.

Picks the store/day every other tab works on, and shows what is currently in
the warehouse for it, read only: sales, tenders, and any adjustments already
applied.

State prefix: 'sel' (widget keys). The chosen store/day itself lives in
``utils.state`` because every tab reads it.
"""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from config import SALES_MEASURES, TENDER_MEASURES, GST_INCLUSIVE_DIVISIONS
from utils.entries import with_total, number_config
from utils.queries import load_stores, load_store_day, clear_store_day_caches
from utils.state import get_selection, set_selection, has_entries

_ALL = "All"


def _store_label(r):
    return f"{r.STORE_NUMBER} – {r.STORE_NAME}  ({r.BRAND_NAME}, {r.DIVISION_NAME})"


def _to_selection(store, day):
    return {
        "store_key": str(store.STORE_KEY),
        "store_number": str(store.STORE_NUMBER),
        "store_name": str(store.STORE_NAME),
        "area_name": None if pd.isna(store.AREA_NAME) else str(store.AREA_NAME),
        "brand_name": str(store.BRAND_NAME),
        "division_name": str(store.DIVISION_NAME),
        "brand_id": None if pd.isna(store.BRAND_ID) else int(store.BRAND_ID),
        "division_id": None if pd.isna(store.DIVISION_ID) else int(store.DIVISION_ID),
        "date": day,
        "date_key": int(day.strftime("%Y%m%d")),
        "date_str": day.strftime("%Y-%m-%d"),
    }


def selection_caption(sel):
    """One-line description of the active store/day, shared by every tab."""
    return (f"🏪 **{sel['store_number']} – {sel['store_name']}**  |  "
            f"{sel['brand_name']} / {sel['division_name']}"
            + (f" / {sel['area_name']}" if sel.get("area_name") else "")
            + f"  |  📅 **{sel['date']:%a %d %b %Y}**")


def _sig(sel):
    return None if sel is None else (sel["store_key"], sel["date_key"])


def _select(session, current_user):
    """Render the pickers and return the store/day they currently request."""
    stores = load_stores(session, current_user)
    if stores.empty:
        st.warning("No stores are available to you. If you expected to see stores "
                   "here, check your access with the Help tab.")
        return None

    c1, c2, c3, c4 = st.columns([1, 1, 3, 1])
    with c1:
        divisions = [_ALL] + sorted(stores["DIVISION_NAME"].dropna().unique())
        division = st.selectbox("Division", divisions, key="sel_division")
    scoped = stores if division == _ALL else stores[stores["DIVISION_NAME"] == division]
    with c2:
        brands = [_ALL] + sorted(scoped["BRAND_NAME"].dropna().unique())
        brand = st.selectbox("Brand", brands, key="sel_brand")
    scoped = scoped if brand == _ALL else scoped[scoped["BRAND_NAME"] == brand]
    labels = {r.STORE_KEY: _store_label(r) for r in scoped.itertuples()}
    with c3:
        store_key = st.selectbox("Store", list(labels), index=None,
                                 format_func=labels.get, placeholder="Choose a store…",
                                 key="sel_store")
    with c4:
        day = st.date_input("Date", value=date.today() - timedelta(days=1),
                            max_value=date.today(), format="DD/MM/YYYY", key="sel_date")

    if store_key is None or day is None:
        return None
    store = scoped[scoped["STORE_KEY"] == store_key].iloc[0]
    return _to_selection(store, day)


def _apply(requested):
    """Adopt the requested store/day — unless that would silently discard entries.

    Changing store/day resets both entry grids, so with unsaved entries the
    change is held until the user confirms it.
    """
    active = get_selection()
    if _sig(requested) == _sig(active):
        return
    if not has_entries():
        set_selection(requested)
        return

    where = "a different store/day" if requested else "no store"
    st.warning(f"⚠️ You have adjustments entered for the store/day below. Switching to "
               f"{where} will discard them.")
    if st.button("Discard entered adjustments and switch", key="sel_discard"):
        set_selection(requested)
        st.rerun()


def _show(df, title, measures, label_col, hide=(), empty_msg="No data."):
    st.markdown(f"**{title}**")
    if df.empty:
        st.info(empty_msg)
        return
    shown = df.drop(columns=[c for c in hide if c in df.columns])
    shown = with_total(shown, label_col, [c for c in shown.columns if c in measures])
    cfg = number_config(measures)
    cfg["ADJUSTMENT_DATE"] = st.column_config.DatetimeColumn("Adjusted At", format="DD/MM/YYYY HH:mm")
    st.dataframe(shown, use_container_width=True, hide_index=True, column_config=cfg)


def render_store_date_tab(session, current_user):
    """Render the Store & Date tab."""
    st.caption("One store, one day at a time. For bulk adjustments, raise a Jira "
               "ticket with support.")
    _apply(_select(session, current_user))

    sel = get_selection()
    if not sel:
        st.info("Choose a store and a date to see the current figures.")
        return

    st.divider()
    head, refresh = st.columns([5, 1])
    head.markdown(selection_caption(sel))
    # The figures are loaded once per store/day; this is the only re-read
    # besides a commit. Entries are kept — they are changes, not totals.
    if refresh.button("🔄 Refresh figures", key="sel_refresh"):
        clear_store_day_caches()
    if sel["division_name"] in GST_INCLUSIVE_DIVISIONS:
        st.caption("ℹ️ Guam store: Amount shown excludes GST; GST is in the Guam GST column.")

    data = load_store_day(session, sel)
    sales, tenders = data["sales"], data["tenders"]
    sales_adj, tender_adj = data["sales_adj"], data["tender_adj"]

    sales_measures = dict(SALES_MEASURES)
    sales_measures.update({
        "GUAM_GST": ("Guam GST", None, 2),
        "TAX_AMOUNT": ("Tax", None, 2),
        "REPORT_NET_SALES": ("Report Net Sales", None, 2),
    })

    left, right = st.columns([3, 2])
    with left:
        _show(sales, "Sales (current, incl. any existing adjustments)", sales_measures,
              "ORDER_CHANNEL", empty_msg="No sales recorded for this store/day.")
    with right:
        _show(tenders, "Tenders (current, incl. any existing adjustments)", TENDER_MEASURES,
              "PAYMENT_TYPE", empty_msg="No tenders recorded for this store/day.")

    left, right = st.columns([3, 2])
    with left:
        _show(sales_adj, "Existing sales adjustments", SALES_MEASURES, "ORDER_CHANNEL",
              empty_msg="No sales adjustments applied to this store/day.")
    with right:
        _show(tender_adj, "Existing tender adjustments", TENDER_MEASURES, "PAYMENT_TYPE",
              empty_msg="No tender adjustments applied to this store/day.")

    if not sales_adj.empty or not tender_adj.empty:
        st.warning("⚠️ Adjustments already exist for this store/day. Committing new "
                   "sales (or tender) adjustments **replaces** the existing sales (or "
                   "tender) adjustments — any line you do not re-enter is set to zero.")
