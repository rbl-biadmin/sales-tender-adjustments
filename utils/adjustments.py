"""Commit staged sales / tender adjustments to the Data Vault, then refresh the mart.

Per section (sales, tender) that has staged lines, in one transaction:

    1. MERGE  H_ADJUSTMENTS_AUDIT        one row per store/day/section (_S / _T)
    2. INSERT S_ADJUSTMENTS_AUDIT        the viewer and the audit note
    3. MERGE  H_<SALES|TENDER>_ADJUSTMENTS   one row per adjustment line
    4. MERGE  L_<SALES|TENDER>_ADJUSTMENTS   line ↔ store ↔ audit
    5. INSERT S_<SALES|TENDER>_ADJUSTMENTS   the values, every staged line

then COMMIT, and only after that CALL the mart stored procedures: each
section's fact procedure (SALES_ADJUSTMENTS / TENDER_ADJUSTMENTS), then
LK_TRADING_DAYS once, then the aggregates (sales: AGG_DAILY_STORE_SALES,
AGG_DAILY_MENU_SALES, AGG_DAILY_DISCOUNTS; tender: AGG_TENDER_MEDIA_SALES). A
failure anywhere before COMMIT rolls the whole thing back, so the procedures
never run against a half-written day.

Hub and link MERGEs insert only — WHEN MATCHED is deliberately absent, so a
re-adjusted store/day reuses its existing keys rather than duplicating them.
Satellites are always inserted (no change detection): every commit is a
deliberate, audited overwrite, and the audit satellite gets a new row with the
new note each time.

All hash keys are computed in SQL with the pipeline's own recipe:

    MD5_BINARY(IFNULL(<id>::VARCHAR, '') || '_' ||
               IFNULL(BRAND_ID::NUMBER, 0) || '_' || IFNULL(DIVISION_ID::NUMBER, 0))

with ids  STORE_NUMBER_DATE_S|T                         (audit)
          STORE_NUMBER_DATE_ORDER_DELIVERY              (sales line)
          STORE_NUMBER_DATE_PAYMENT_ORDER_DELIVERY      (tender line)
          STORE_NUMBER                                  (store)
and DATE as 'YYYY-MM-DD'.
"""
from config import (
    RECORD_SOURCE, SALES_MEASURES, TENDER_MEASURES, SALES_SAT_DATE_COL,
    TENDER_SAT_DATE_COL, AUDIT_SAT_USER_COL, PROC_DIVISION_PREFIX, PROC_BRAND_CODE,
    DB_HUB_ADJ_AUDIT, DB_SAT_ADJ_AUDIT, DB_HUB_SALES_ADJ, DB_LINK_SALES_ADJ,
    DB_SAT_SALES_ADJ, DB_HUB_TENDER_ADJ, DB_LINK_TENDER_ADJ, DB_SAT_TENDER_ADJ,
    DB_PROC_SALES_ADJ, DB_PROC_TENDER_ADJ, DB_PROC_TRADING_DAYS,
    DB_PROC_AGG_STORE_SALES, DB_PROC_AGG_MENU_SALES, DB_PROC_AGG_DISCOUNTS,
    DB_PROC_AGG_TENDER_MEDIA,
)
from utils.sql import q, num

SECTIONS = {
    "sales": {
        "label": "Sales",
        "keys": ["ORDER_CHANNEL", "DELIVERY_CHANNEL"],     # also the id order
        "measures": SALES_MEASURES,
        "id_col": "SALE_ADJUSTMENT_ID",
        "hkey_col": "H_SALE_ADJUSTMENT_HKEY",
        "audit_suffix": "S",
        "hub": DB_HUB_SALES_ADJ,
        "link": DB_LINK_SALES_ADJ,
        "sat": DB_SAT_SALES_ADJ,
        "sat_date_col": SALES_SAT_DATE_COL,
        "procs": [("Sales", DB_PROC_SALES_ADJ)],
        # Run after LK_TRADING_DAYS — the aggregates read the trading days
        "agg_procs": [("Daily store sales", DB_PROC_AGG_STORE_SALES),
                      ("Daily menu sales", DB_PROC_AGG_MENU_SALES),
                      ("Daily discounts", DB_PROC_AGG_DISCOUNTS)],
    },
    "tender": {
        "label": "Tender",
        "keys": ["PAYMENT_TYPE", "ORDER_CHANNEL", "DELIVERY_CHANNEL"],
        "measures": TENDER_MEASURES,
        "id_col": "TENDER_ADJUSTMENT_ID",
        "hkey_col": "H_TENDER_ADJUSTMENT_HKEY",
        "audit_suffix": "T",
        "hub": DB_HUB_TENDER_ADJ,
        "link": DB_LINK_TENDER_ADJ,
        "sat": DB_SAT_TENDER_ADJ,
        "sat_date_col": TENDER_SAT_DATE_COL,
        "procs": [("Tender", DB_PROC_TENDER_ADJ)],
        "agg_procs": [("Tender media sales", DB_PROC_AGG_TENDER_MEDIA)],
    },
}


def proc_brand(sel):
    """Brand parameter for the mart procedures, e.g. 'HI_PH', 'AU_TB', 'KFC'."""
    return (PROC_DIVISION_PREFIX.get(sel["division_name"], "")
            + PROC_BRAND_CODE.get(sel["brand_name"], sel["brand_name"]))


def _hkey(id_expr):
    return (f"MD5_BINARY(IFNULL({id_expr}::VARCHAR, '') || '_' || "
            f"IFNULL(x.BRAND_ID::NUMBER, 0) || '_' || IFNULL(x.DIVISION_ID::NUMBER, 0))")


def _source_sql(spec, sel, lines):
    """One row per staged line, with every id and hash key the writes need."""
    keys, measures = spec["keys"], spec["measures"]
    casts = [f"${i + 1}::VARCHAR AS {k}" for i, k in enumerate(keys)]
    casts += [f"${len(keys) + j + 1}::NUMBER(38,{dec}) AS {f}"
              for j, (f, (_lbl, _col, dec)) in enumerate(measures.items())]
    rows = ", ".join(
        "(" + ", ".join([q(r[k]) for k in keys]
                        + [num(r[f], dec) for f, (_l, _c, dec) in measures.items()]) + ")"
        for r in lines.to_dict("records"))

    store, date = q(sel["store_number"]), q(sel["date_str"])
    line_id = f"{store} || '_' || {date} || '_' || " + " || '_' || ".join(f"v.{k}" for k in keys)
    audit_id = f"{store} || '_' || {date} || {q('_' + spec['audit_suffix'])}"

    return f"""
        SELECT x.*,
               {_hkey('x.' + spec['id_col'])} AS {spec['hkey_col']},
               {_hkey('x.STORE_NUMBER')}         AS H_STORE_HKEY,
               {_hkey('x.ADJUSTMENT_AUDIT_ID')}  AS H_ADJUSTMENT_AUDIT_HKEY
        FROM (
            SELECT v.*,
                   {store}                        AS STORE_NUMBER,
                   {int(sel['brand_id'])}::NUMBER    AS BRAND_ID,
                   {int(sel['division_id'])}::NUMBER AS DIVISION_ID,
                   {line_id}                      AS {spec['id_col']},
                   {audit_id}                     AS ADJUSTMENT_AUDIT_ID
            FROM (SELECT {', '.join(casts)} FROM VALUES {rows}) v
        ) x
    """


def _section_statements(spec, sel, lines, audit_note, current_user, ldts):
    src = _source_sql(spec, sel, lines)
    rs = q(RECORD_SOURCE)
    hk, idc = spec["hkey_col"], spec["id_col"]
    sat_cols = [spec["sat_date_col"]] + spec["keys"] + [c for _l, c, _d in spec["measures"].values()]
    sat_vals = [f"{q(sel['date_str'])}::DATE"] + spec["keys"] + list(spec["measures"])

    return [
        f"""
        MERGE INTO {DB_HUB_ADJ_AUDIT} tgt
        USING (SELECT DISTINCT H_ADJUSTMENT_AUDIT_HKEY, ADJUSTMENT_AUDIT_ID, DIVISION_ID, BRAND_ID
               FROM ({src})) src
        ON tgt.H_ADJUSTMENT_AUDIT_HKEY = src.H_ADJUSTMENT_AUDIT_HKEY
        WHEN NOT MATCHED THEN
            INSERT (H_ADJUSTMENT_AUDIT_HKEY, AUDIT_ID, DIVISION_ID, BRAND_ID, LDTS, RS)
            VALUES (src.H_ADJUSTMENT_AUDIT_HKEY, src.ADJUSTMENT_AUDIT_ID, src.DIVISION_ID,
                    src.BRAND_ID, {ldts}, {rs})
        """,
        f"""
        INSERT INTO {DB_SAT_ADJ_AUDIT}
            (H_ADJUSTMENT_AUDIT_HKEY, {AUDIT_SAT_USER_COL}, AUDIT_NOTE, LDTS, RS)
        SELECT DISTINCT H_ADJUSTMENT_AUDIT_HKEY, {q(current_user)}, {q(audit_note)}, {ldts}, {rs}
        FROM ({src})
        """,
        f"""
        MERGE INTO {spec['hub']} tgt
        USING ({src}) src
        ON tgt.{hk} = src.{hk}
        WHEN NOT MATCHED THEN
            INSERT ({hk}, {idc}, DIVISION_ID, BRAND_ID, LDTS, RS)
            VALUES (src.{hk}, src.{idc}, src.DIVISION_ID, src.BRAND_ID, {ldts}, {rs})
        """,
        f"""
        MERGE INTO {spec['link']} tgt
        USING ({src}) src
        ON  tgt.{hk} = src.{hk}
        AND tgt.H_STORE_HKEY = src.H_STORE_HKEY
        AND tgt.H_ADJUSTMENT_AUDIT_HKEY = src.H_ADJUSTMENT_AUDIT_HKEY
        WHEN NOT MATCHED THEN
            INSERT ({hk}, H_STORE_HKEY, H_ADJUSTMENT_AUDIT_HKEY, LDTS, RS)
            VALUES (src.{hk}, src.H_STORE_HKEY, src.H_ADJUSTMENT_AUDIT_HKEY, {ldts}, {rs})
        """,
        f"""
        INSERT INTO {spec['sat']} ({hk}, {', '.join(sat_cols)}, LDTS, RS)
        SELECT {hk}, {', '.join(sat_vals)}, {ldts}, {rs}
        FROM ({src})
        """,
    ]


def _pinned_ldts(session):
    """One LDTS for every row of the commit, evaluated by Snowflake.

    Read from Snowflake (never formatted from a Python clock) and passed back
    with its offset, so hub, link, satellites and audit all carry the same
    instant regardless of session time zone. The vault LDTS columns are
    TIMESTAMP_LTZ, and MERGE ... INSERT VALUES will not cast TZ to LTZ, so the
    literal must be built as LTZ — the offset still pins the instant.
    """
    now = session.sql("SELECT CURRENT_TIMESTAMP()").collect()[0][0]
    if getattr(now, "tzinfo", None) is None:
        return "CURRENT_TIMESTAMP()"
    return f"TO_TIMESTAMP_LTZ({q(now.isoformat())})"


def commit_adjustments(session, sel, staged, audit_note, current_user):
    """Write the staged sections and run their mart procedures.

    ``staged`` maps section name ('sales' / 'tender') to its staged lines;
    empty or missing sections are not touched. ``current_user`` is the viewer.

    Never raises. Returns a dict:
        written      {section: line count} — empty if the transaction failed
        db_error     str or None — the vault write failed and was rolled back
        proc_errors  [str] — vault written, but a mart procedure failed
        proc_results [str] — the procedures' return values
    """
    result = {"written": {}, "db_error": None, "proc_errors": [], "proc_results": []}
    sections = {name: lines for name, lines in staged.items()
                if lines is not None and not lines.empty}
    if not sections:
        return result

    try:
        ldts = _pinned_ldts(session)
        session.sql("BEGIN").collect()
        for name, lines in sections.items():
            for stmt in _section_statements(SECTIONS[name], sel, lines,
                                            audit_note, current_user, ldts):
                session.sql(stmt).collect()
        session.sql("COMMIT").collect()
        result["written"] = {name: len(lines) for name, lines in sections.items()}
    except Exception as e:
        try:
            session.sql("ROLLBACK").collect()
        except Exception:
            pass
        result["db_error"] = str(e)
        return result

    # Order: the sections' fact procedures, then the trading-days lookup once
    # (it reads those facts), then the aggregates (they read the trading days).
    # Every call runs even if an earlier one failed: the vault is committed
    # either way, and a retry re-runs them all.
    brand = proc_brand(sel)
    calls = [call for name in sections for call in SECTIONS[name]["procs"]]
    calls.append(("Trading days", DB_PROC_TRADING_DAYS))
    calls += [call for name in sections for call in SECTIONS[name]["agg_procs"]]
    for label, proc in calls:
        try:
            rows = session.sql(
                f"CALL {proc}({q(brand)}, {int(sel['date_key'])}, {q(sel['store_key'])})"
            ).collect()
            ret = rows[0][0] if rows else None
            result["proc_results"].append(f"{label}: {ret if ret is not None else 'done'}")
        except Exception as e:
            result["proc_errors"].append(f"{label} refresh failed: {e}")
    return result
