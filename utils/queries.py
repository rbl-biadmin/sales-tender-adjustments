"""Read queries — all cached, shared by every tab.

Loaded once per store/day (``load_store_day``) and reused by the entry grids,
previews and commit summary, so the step-2 queries are not re-run as the user
types.
``_session`` is underscore-prefixed so Streamlit does not try to hash it.

st.cache_data is shared across ALL viewers of the app. The store list is
row-access filtered per user, so its loader takes ``viewer`` purely as a cache
key: without it, one user's store list would be served to the next.
"""
import pandas as pd
import streamlit as st

from config import (
    SALES_MEASURES, TENDER_MEASURES, AUDIT_SAT_USER_COL, LOOKBACK_DAYS,
    DB_DIM_STORES, DB_DIM_BRANDS, DB_DIM_DIVISIONS, DB_DIM_ORDER_CHANNELS,
    DB_DIM_DELIVERY_CHANNELS, DB_DIM_PAYMENT_TYPES, DB_RPT_DAILY_STORE_SALES,
    DB_RPT_TENDER_MEDIA, DB_FACT_SALES, DB_FACT_SALES_ADJ, DB_FACT_TENDER_ADJ,
    DB_REF_BRANDS, DB_REF_DIVISIONS, DB_HUB_STORES,
    DB_HUB_ADJ_AUDIT, DB_SAT_ADJ_AUDIT, DB_HUB_SALES_ADJ, DB_LINK_SALES_ADJ,
    DB_HUB_TENDER_ADJ, DB_LINK_TENDER_ADJ,
)
from utils.sql import q

_TTL = 60


def _numeric(df, cols):
    """Snowpark can hand NUMBER sums back as Decimal/object; make them floats."""
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df


@st.cache_data(ttl=600, show_spinner="Loading stores…")
def load_stores(_session, viewer):
    """Step 1 — stores the viewer can see, with the vault BRAND_ID/DIVISION_ID.

    The mart dimensions are keyed by BRAND_KEY/DIVISION_KEY, but the Data Vault
    hash keys are built from the vault REF_* ids, so those are resolved here by
    name. LEFT JOIN so a store with no matching REF row still appears — the
    commit tab then blocks it with an explicit error instead of hiding it.
    """
    df = _session.sql(f"""
        SELECT d.DIVISION_KEY, d.DIVISION_NAME, b.BRAND_KEY, b.BRAND_NAME,
               s.STORE_KEY, s.STORE_NUMBER, s.STORE_NAME, s.AREA_NAME,
               rb.BRAND_ID, rd.DIVISION_ID
        FROM {DB_DIM_STORES} s
        JOIN {DB_DIM_BRANDS}    b ON s.BRAND_KEY    = b.BRAND_KEY
        JOIN {DB_DIM_DIVISIONS} d ON s.DIVISION_KEY = d.DIVISION_KEY
        LEFT JOIN {DB_REF_BRANDS}    rb ON rb.BRAND_NAME    = b.BRAND_NAME
        LEFT JOIN {DB_REF_DIVISIONS} rd ON rd.DIVISION_NAME = d.DIVISION_NAME
        ORDER BY d.DIVISION_NAME, b.BRAND_NAME, s.STORE_NUMBER
    """).to_pandas()
    return df.drop_duplicates("STORE_KEY").reset_index(drop=True)


@st.cache_data(ttl=_TTL, show_spinner="Loading sales…")
def load_sales(_session, store_key, date_key):
    """Step 2 — current daily sales by channel (already includes any adjustments)."""
    df = _session.sql(f"""
        SELECT o.ORDER_CHANNEL, d.DELIVERY_CHANNEL,
               SUM(f.NUMBER_SALES)     AS TRANSACTIONS,
               SUM(f.AMOUNT_NET)       AS AMOUNT,
               SUM(f.DELIVERY_CHARGE)  AS DELIVERY_FEES,
               SUM(f.BOTTLE_FEE)       AS BOTTLE_FEE,
               SUM(f.GIFT_CARD_AMOUNT) AS GIFT_CARD,
               SUM(f.TB_FUND)          AS TB_FUND,
               SUM(f.DISCOUNT_AMOUNT)  AS DISCOUNT,
               SUM(f.GUAM_GST)         AS GUAM_GST,
               SUM(f.AMOUNT_TAX)       AS TAX_AMOUNT,
               SUM(IFNULL(f.AMOUNT_NET, 0) - IFNULL(f.GIFT_CARD_AMOUNT, 0)
                   + IFNULL(f.DELIVERY_CHARGE, 0) - IFNULL(f.BOTTLE_FEE, 0)
                   - IFNULL(f.GUAM_GST, 0) - IFNULL(f.TB_FUND, 0)) AS REPORT_NET_SALES
        FROM {DB_RPT_DAILY_STORE_SALES} f
        JOIN {DB_DIM_DELIVERY_CHANNELS} d ON f.DELIVERY_CHANNEL_KEY = d.DELIVERY_CHANNEL_KEY
        JOIN {DB_DIM_ORDER_CHANNELS}    o ON f.ORDER_CHANNEL_KEY    = o.ORDER_CHANNEL_KEY
        WHERE f.STORE_KEY = {q(store_key)}
          AND f.DATE_KEY  = {int(date_key)}
        GROUP BY o.ORDER_CHANNEL, d.DELIVERY_CHANNEL
        HAVING SUM(f.NUMBER_SALES) <> 0 OR SUM(f.AMOUNT_NET) <> 0
            OR SUM(f.DELIVERY_CHARGE) <> 0 OR SUM(f.BOTTLE_FEE) <> 0
            OR SUM(f.GIFT_CARD_AMOUNT) <> 0 OR SUM(f.TB_FUND) <> 0
            OR SUM(f.DISCOUNT_AMOUNT) <> 0
        ORDER BY o.ORDER_CHANNEL, d.DELIVERY_CHANNEL
    """).to_pandas()
    return _numeric(df, list(SALES_MEASURES) + ["GUAM_GST", "TAX_AMOUNT", "REPORT_NET_SALES"])


@st.cache_data(ttl=_TTL, show_spinner="Loading tenders…")
def load_tenders(_session, store_key, date_key):
    """Step 2 — current daily tenders by channel and payment type."""
    df = _session.sql(f"""
        SELECT p.PAYMENT_TYPE, o.ORDER_CHANNEL, d.DELIVERY_CHANNEL,
               SUM(f.TENDER_AMOUNT) AS TENDER_AMOUNT,
               SUM(f.TIP_AMOUNT)    AS TIP_AMOUNT
        FROM {DB_RPT_TENDER_MEDIA} f
        JOIN {DB_DIM_DELIVERY_CHANNELS} d ON f.DELIVERY_CHANNEL_KEY = d.DELIVERY_CHANNEL_KEY
        JOIN {DB_DIM_ORDER_CHANNELS}    o ON f.ORDER_CHANNEL_KEY    = o.ORDER_CHANNEL_KEY
        JOIN {DB_DIM_PAYMENT_TYPES}     p ON f.PAYMENT_TYPE_KEY     = p.PAYMENT_TYPE_KEY
        WHERE f.STORE_KEY = {q(store_key)}
          AND f.DATE_KEY  = {int(date_key)}
        GROUP BY p.PAYMENT_TYPE, o.ORDER_CHANNEL, d.DELIVERY_CHANNEL
        HAVING SUM(f.TENDER_AMOUNT) <> 0
        ORDER BY o.ORDER_CHANNEL, d.DELIVERY_CHANNEL, p.PAYMENT_TYPE
    """).to_pandas()
    return _numeric(df, list(TENDER_MEASURES))


def _latest_audit_sql(id_col, link_table, link_hkey, hub_table):
    """Latest audit note/user per adjustment id (the spec's `aud` subquery)."""
    return f"""
        SELECT DISTINCT ha.{id_col}, s.{AUDIT_SAT_USER_COL} AS ADJUSTED_BY,
               s.AUDIT_NOTE, s.LDTS AS ADJUSTMENT_DATE, s.RS AS ADJUSTMENT_SOURCE
        FROM {DB_HUB_ADJ_AUDIT} h
        JOIN {DB_SAT_ADJ_AUDIT} s ON h.H_ADJUSTMENT_AUDIT_HKEY = s.H_ADJUSTMENT_AUDIT_HKEY
        JOIN {link_table}       l ON h.H_ADJUSTMENT_AUDIT_HKEY = l.H_ADJUSTMENT_AUDIT_HKEY
        JOIN {hub_table}       ha ON l.{link_hkey} = ha.{link_hkey}
        WHERE s.LDTS = (SELECT MAX(s1.LDTS) FROM {DB_SAT_ADJ_AUDIT} s1
                        WHERE s1.H_ADJUSTMENT_AUDIT_HKEY = s.H_ADJUSTMENT_AUDIT_HKEY)
    """


@st.cache_data(ttl=_TTL, show_spinner="Loading existing sales adjustments…")
def load_sales_adjustments(_session, store_key, date_key):
    """Step 2 — sales adjustments already applied to this store/day."""
    aud = _latest_audit_sql("SALE_ADJUSTMENT_ID", DB_LINK_SALES_ADJ,
                            "H_SALE_ADJUSTMENT_HKEY", DB_HUB_SALES_ADJ)
    df = _session.sql(f"""
        SELECT o.ORDER_CHANNEL, d.DELIVERY_CHANNEL,
               f.LINE_COUNT      AS TRANSACTIONS,
               f.AMOUNT_NET      AS AMOUNT,
               f.DELIVERY_CHARGE AS DELIVERY_FEES,
               f.BOTTLE_FEE      AS BOTTLE_FEE,
               f.GIFT_CARD       AS GIFT_CARD,
               f.TB_FUND         AS TB_FUND,
               f.TOTAL_DISCOUNT  AS DISCOUNT,
               aud.ADJUSTED_BY, aud.AUDIT_NOTE, aud.ADJUSTMENT_DATE, aud.ADJUSTMENT_SOURCE
        FROM {DB_FACT_SALES_ADJ} f
        JOIN {DB_DIM_DELIVERY_CHANNELS} d ON f.DELIVERY_CHANNEL_KEY = d.DELIVERY_CHANNEL_KEY
        JOIN {DB_DIM_ORDER_CHANNELS}    o ON f.ORDER_CHANNEL_KEY    = o.ORDER_CHANNEL_KEY
        LEFT JOIN ({aud}) aud ON aud.SALE_ADJUSTMENT_ID = f.SALE_ADJUSTMENT_ID
        WHERE f.STORE_KEY = {q(store_key)}
          AND f.SALE_REPORT_DATE_KEY = {int(date_key)}
        ORDER BY o.ORDER_CHANNEL, d.DELIVERY_CHANNEL
    """).to_pandas()
    return _numeric(df, list(SALES_MEASURES))


@st.cache_data(ttl=_TTL, show_spinner="Loading existing tender adjustments…")
def load_tender_adjustments(_session, store_key, date_key):
    """Step 2 — tender adjustments already applied to this store/day."""
    aud = _latest_audit_sql("TENDER_ADJUSTMENT_ID", DB_LINK_TENDER_ADJ,
                            "H_TENDER_ADJUSTMENT_HKEY", DB_HUB_TENDER_ADJ)
    df = _session.sql(f"""
        SELECT p.PAYMENT_TYPE, o.ORDER_CHANNEL, d.DELIVERY_CHANNEL,
               f.TENDER_AMOUNT, f.TIP_AMOUNT,
               aud.ADJUSTED_BY, aud.AUDIT_NOTE, aud.ADJUSTMENT_DATE, aud.ADJUSTMENT_SOURCE
        FROM {DB_FACT_TENDER_ADJ} f
        JOIN {DB_DIM_DELIVERY_CHANNELS} d ON f.DELIVERY_CHANNEL_KEY = d.DELIVERY_CHANNEL_KEY
        JOIN {DB_DIM_ORDER_CHANNELS}    o ON f.ORDER_CHANNEL_KEY    = o.ORDER_CHANNEL_KEY
        JOIN {DB_DIM_PAYMENT_TYPES}     p ON f.PAYMENT_TYPE_KEY     = p.PAYMENT_TYPE_KEY
        LEFT JOIN ({aud}) aud ON aud.TENDER_ADJUSTMENT_ID = f.TENDER_ADJUSTMENT_ID
        WHERE f.STORE_KEY = {q(store_key)}
          AND f.TENDER_DATE_KEY = {int(date_key)}
        ORDER BY o.ORDER_CHANNEL, d.DELIVERY_CHANNEL, p.PAYMENT_TYPE
    """).to_pandas()
    return _numeric(df, list(TENDER_MEASURES))


@st.cache_data(ttl=3600, show_spinner="Loading channels…")
def load_channel_pairs(_session, store_key):
    """Order/delivery channel pairs this store has traded in the last 14 days.

    Filters on the raw date key, never a function of it: wrapping the column
    (UDF_KEY_TO_DATE) stops Snowflake pruning, so every FACT_SALES row the store
    ever had was converted and scanned — the slow first render of Step 3.
    """
    return _session.sql(f"""
        SELECT DISTINCT o.ORDER_CHANNEL, d.DELIVERY_CHANNEL
        FROM {DB_FACT_SALES} f
        JOIN {DB_DIM_ORDER_CHANNELS}    o ON f.ORDER_CHANNEL_KEY    = o.ORDER_CHANNEL_KEY
        JOIN {DB_DIM_DELIVERY_CHANNELS} d ON f.DELIVERY_CHANNEL_KEY = d.DELIVERY_CHANNEL_KEY
        WHERE f.STORE_KEY = {q(store_key)}
          AND f.SALE_REPORT_DATE_KEY >= TO_NUMBER(TO_CHAR(DATEADD(day, -{LOOKBACK_DAYS}, CURRENT_DATE()), 'YYYYMMDD'))
    """).to_pandas()


@st.cache_data(ttl=3600, show_spinner="Loading payment types…")
def load_payment_types(_session, store_key):
    """Payment types this store has taken in the last 14 days."""
    return _session.sql(f"""
        SELECT DISTINCT p.PAYMENT_TYPE
        FROM {DB_RPT_TENDER_MEDIA} f
        JOIN {DB_DIM_PAYMENT_TYPES} p ON f.PAYMENT_TYPE_KEY = p.PAYMENT_TYPE_KEY
        WHERE f.STORE_KEY = {q(store_key)}
          AND f.DATE_KEY >= TO_NUMBER(TO_CHAR(DATEADD(day, -{LOOKBACK_DAYS}, CURRENT_DATE()), 'YYYYMMDD'))
    """).to_pandas()


def store_hkey_sql(store_number, brand_id, division_id):
    """H_STORE_HKEY, computed with exactly the recipe the commit uses."""
    return (f"MD5_BINARY(IFNULL({q(store_number)}::VARCHAR, '') || '_' || "
            f"IFNULL({int(brand_id)}::NUMBER, 0) || '_' || IFNULL({int(division_id)}::NUMBER, 0))")


@st.cache_data(ttl=600, show_spinner=False)
def store_hub_exists(_session, store_number, brand_id, division_id):
    """Does the store hash key the commit will write actually exist in H_STORES?

    A wrong BRAND_ID/DIVISION_ID or recipe would write link rows that never join
    to a store — silently. Checking the hub first turns that into a visible
    error before anything is written.
    """
    rows = _session.sql(f"""
        SELECT COUNT(*) FROM {DB_HUB_STORES}
        WHERE H_STORE_HKEY = {store_hkey_sql(store_number, brand_id, division_id)}
    """).collect()
    return bool(rows and rows[0][0] > 0)


_DAY_DATA_KEY = "_adj_day_data"


def load_store_day(_session, sel):
    """The four step-2 frames for the selected store/day, loaded once.

    Held in session state until the store/day changes, a commit lands or the
    user refreshes — the cache_data TTL alone re-ran all four queries on the
    first interaction after it expired, mid-entry. Callers must not modify the
    frames in place: every tab shares the same objects.
    """
    sig = (sel["store_key"], sel["date_key"])
    held = st.session_state.get(_DAY_DATA_KEY)
    if held is None or held[0] != sig:
        held = (sig, {
            "sales": load_sales(_session, *sig),
            "tenders": load_tenders(_session, *sig),
            "sales_adj": load_sales_adjustments(_session, *sig),
            "tender_adj": load_tender_adjustments(_session, *sig),
        })
        st.session_state[_DAY_DATA_KEY] = held
    return held[1]


def clear_store_day_caches():
    """Invalidate the per-store/day data after a commit or a manual refresh."""
    st.session_state.pop(_DAY_DATA_KEY, None)
    for fn in (load_sales, load_tenders, load_sales_adjustments, load_tender_adjustments):
        fn.clear()
