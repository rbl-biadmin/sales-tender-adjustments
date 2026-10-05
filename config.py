"""Configuration constants for the Sales & Tender Adjustments app.

Every environment- or schema-specific value lives here. No other module may
contain a literal table name.
"""

# Application version — update with each deployment. Read by the app header and
# the Help tab footer, so it only needs changing here.
APP_VERSION = "v1.0.0"

# Record source identifier — stamped as RS on every Data Vault row the app
# writes, and shown as "Adjustment Source" on the Store & Date tab.
RECORD_SOURCE = "STREAMLIT_ADJUSTMENTS_APP"

# Database name.
# KEEP THIS ON ONE LINE matching `DB_EDW = "..."` — CI rewrites it with sed when
# deploying to main. Reformatting it means the prod app silently reads the test
# database.
DB_EDW = "EDW_TEST"

# ---------------------------------------------------------------------------
# Business rules
# ---------------------------------------------------------------------------

# The catch-all value offered in every channel / payment type dropdown, for a
# general day adjustment where the real channel is not known.
ADJUSTMENT = "Adjustment"

# Order and delivery channel are linked, so the entry grids offer them as one
# "Order | Delivery" dropdown of valid pairs.
CHANNEL_SEP = " | "

# How far back the fact tables are scanned for the channel / payment type
# dropdown lists.
LOOKBACK_DAYS = 14

# Divisions whose sales Amount is entered incl. GST (GST is removed on load).
GST_INCLUSIVE_DIVISIONS = {"Guam"}

# Brand parameter for the mart stored procedures: division prefix + brand code.
# Divisions/brands not listed fall back to '' / the brand name.
PROC_DIVISION_PREFIX = {
    "Australia": "AU_",
    "Hawaii": "HI_",
    "Guam": "HI_",
    "Saipan": "HI_",
}
PROC_BRAND_CODE = {
    "Pizza Hut": "PH",
    "Taco Bell": "TB",
    "Carls Junior": "CJ",
}

# ---------------------------------------------------------------------------
# Measures — field name (as aliased in the read queries) →
#   (grid label, satellite column, decimals)
# The satellite column is where the value lands on commit; the field name is
# what the read queries, the entry grids and the previews share.
# ---------------------------------------------------------------------------
SALES_MEASURES = {
    "TRANSACTIONS":  ("Transactions",  "LINE_COUNT",      0),
    "AMOUNT":        ("Amount",        "AMOUNT_NET",      2),
    "DELIVERY_FEES": ("Delivery Fees", "DELIVERY_CHARGE", 2),
    "BOTTLE_FEE":    ("Bottle Fee",    "BOTTLE_FEE",      2),
    "GIFT_CARD":     ("Gift Card",     "GIFT_CARD",       2),
    "TB_FUND":       ("TB Fund",       "TB_FUND",         2),
    "DISCOUNT":      ("Discount",      "TOTAL_DISCOUNT",  2),
}
TENDER_MEASURES = {
    "TENDER_AMOUNT": ("Tender Amount", "TENDER_AMOUNT", 2),
    "TIP_AMOUNT":    ("Tip Amount",    "TIP_AMOUNT",    2),
}

# Satellite date columns
SALES_SAT_DATE_COL = "SALE_REPORT_DATE"
TENDER_SAT_DATE_COL = "TENDER_DATE"

# USER is a reserved word, so the audit satellite's column must be quoted.
AUDIT_SAT_USER_COL = '"USER"'

# ---------------------------------------------------------------------------
# Table names
# ---------------------------------------------------------------------------

# Mart — read side
DB_DIM_STORES            = f"{DB_EDW}.MART_SALES.DIM_STORES"
DB_DIM_BRANDS            = f"{DB_EDW}.MART_SALES.DIM_BRANDS"
DB_DIM_DIVISIONS         = f"{DB_EDW}.MART_SALES.DIM_DIVISIONS"
DB_DIM_ORDER_CHANNELS    = f"{DB_EDW}.MART_SALES.DIM_ORDER_CHANNELS"
DB_DIM_DELIVERY_CHANNELS = f"{DB_EDW}.MART_SALES.DIM_DELIVERY_CHANNELS"
DB_DIM_PAYMENT_TYPES     = f"{DB_EDW}.MART_SALES.DIM_PAYMENT_TYPES"
DB_RPT_DAILY_STORE_SALES = f"{DB_EDW}.MART_SALES.RPT_DAILY_STORE_SALES"
DB_RPT_TENDER_MEDIA      = f"{DB_EDW}.MART_SALES.RPT_TENDER_MEDIA_SALES"
DB_FACT_SALES            = f"{DB_EDW}.MART_SALES.FACT_SALES"
DB_FACT_SALES_ADJ        = f"{DB_EDW}.MART_SALES.FACT_SALES_ADJUSTMENTS"
DB_FACT_TENDER_ADJ       = f"{DB_EDW}.MART_SALES.FACT_TENDER_ADJUSTMENTS"

# Mart — stored procedures that rebuild the adjustment facts for a store/day
DB_PROC_SALES_ADJ  = f"{DB_EDW}.MART_SALES.SALES_ADJUSTMENTS"
DB_PROC_TENDER_ADJ = f"{DB_EDW}.MART_SALES.TENDER_ADJUSTMENTS"

# Data Vault
DB_UDF_KEY_TO_DATE  = f"{DB_EDW}.DATAVAULT.UDF_KEY_TO_DATE"
DB_REF_BRANDS       = f"{DB_EDW}.DATAVAULT.REF_BRANDS"
DB_REF_DIVISIONS    = f"{DB_EDW}.DATAVAULT.REF_DIVISIONS"
DB_HUB_STORES       = f"{DB_EDW}.DATAVAULT.H_STORES"
DB_HUB_ADJ_AUDIT    = f"{DB_EDW}.DATAVAULT.H_ADJUSTMENTS_AUDIT"
DB_SAT_ADJ_AUDIT    = f"{DB_EDW}.DATAVAULT.S_ADJUSTMENTS_AUDIT"
DB_HUB_SALES_ADJ    = f"{DB_EDW}.DATAVAULT.H_SALES_ADJUSTMENTS"
DB_LINK_SALES_ADJ   = f"{DB_EDW}.DATAVAULT.L_SALES_ADJUSTMENTS"
DB_SAT_SALES_ADJ    = f"{DB_EDW}.DATAVAULT.S_SALES_ADJUSTMENTS"
DB_HUB_TENDER_ADJ   = f"{DB_EDW}.DATAVAULT.H_TENDER_ADJUSTMENTS"
DB_LINK_TENDER_ADJ  = f"{DB_EDW}.DATAVAULT.L_TENDER_ADJUSTMENTS"
DB_SAT_TENDER_ADJ   = f"{DB_EDW}.DATAVAULT.S_TENDER_ADJUSTMENTS"

# App audit log (one row per commit attempt) — deliberately NOT parameterised
# by DB_EDW. It lives beside the app so dev and prod share one audit trail.
DB_AUDIT_LOG = "STREAMLIT_APPS.DATA_MANAGEMENT.AUDIT_LOG_ADJUSTMENTS"
