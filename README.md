# Sales & Tender Adjustments

Streamlit in Snowflake app for loading **one store / one day** of sales and
tender adjustments into the EDW Data Vault, across all divisions and brands.
Bulk adjustments go through support (Jira).

## Flow

| Tab | Step | What happens |
| --- | --- | --- |
| 1. Store & Date | 1–2 | Pick a store (row-access filtered) and a date; read-only view of current sales, tenders and existing adjustments |
| 2. Sales Adjustments | 3–4 | Enter adjustment lines; before/after preview |
| 3. Tender Adjustments | 5–6 | Enter adjustment lines; before/after preview |
| 4. Review & Commit | 7 | Mandatory audit reason → Data Vault writes in one transaction → `SALES_ADJUSTMENTS` / `TENDER_ADJUSTMENTS` procedures |

**Overwrite rule:** committing a section replaces that section's existing
adjustments for the store/day; existing lines not re-entered are written as
zero. Nothing is updated or deleted — every commit inserts new satellite rows.

## Layout

```
streamlit_app.py        shell, CSS, auth, tab wiring
config.py               every constant: DB_EDW, table names, measure → column maps
utils/queries.py        cached read queries (steps 1–2, dropdown lists)
utils/entries.py        entry grid, validation, overwrite staging, previews
utils/adjustments.py    Data Vault commit (hub/link/satellite MERGE + INSERT) and procedure calls
utils/state.py          cross-tab session state
utils/audit.py          app audit log (one row per commit attempt)
utils/auth.py           role lookup + edit permission
tabs/                   one module per tab
setup/snowflake_setup.sql  one-off Snowflake objects and grants
```

## Deployment

No local run — `get_active_session()` only resolves inside Snowflake. Push to
`develop` to update the dev app (`EDW_TEST`); merge `develop` → `main` to
release (CI rewrites `DB_EDW` to `EDW_PROD`). Bump `APP_VERSION` in `config.py`
and `_UPDATED` in `tabs/help.py` with every release.
