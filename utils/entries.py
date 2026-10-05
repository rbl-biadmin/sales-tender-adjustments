"""Shared helpers for the two adjustment entry tabs (sales and tender).

Both tabs follow the same shape: an `st.data_editor` with dynamic rows, a clean
and validate pass, a staging pass that applies the overwrite rule, and a
before/after preview computed in pandas from the cached step-2 frames.

Order and delivery channel are linked — only pairs the store actually trades
are valid — and `st.data_editor` cannot make one cell's options depend on
another's. So the grid offers a single "Order | Delivery" column whose options
are the valid pairs, and it is split back into two fields when cleaned.
"""
import pandas as pd
import streamlit as st

from config import ADJUSTMENT, CHANNEL_SEP

CHANNEL = "CHANNEL"
SOURCE = "SOURCE"
ENTERED = "Entered"
ZEROED = "Zeroed (replaces existing)"
_TOL = 0.005


def channel_label(order_channel, delivery_channel):
    return f"{order_channel}{CHANNEL_SEP}{delivery_channel}"


def channel_options(*frames):
    """'Adjustment | Adjustment' first, then every pair seen in ``frames``.

    Pairs from the day's own sales and existing adjustments are included as
    well as the 14-day list, so an older date's channels are always offered.
    """
    labels = set()
    for df in frames:
        if df is None or df.empty:
            continue
        for o, d in df[["ORDER_CHANNEL", "DELIVERY_CHANNEL"]].dropna().itertuples(index=False):
            labels.add(channel_label(o, d))
    general = channel_label(ADJUSTMENT, ADJUSTMENT)
    labels.discard(general)
    return [general] + sorted(labels)


def payment_options(*frames):
    """'Adjustment' first, then every payment type seen in ``frames``."""
    types = set()
    for df in frames:
        if df is not None and not df.empty:
            types.update(df["PAYMENT_TYPE"].dropna().astype(str))
    types.discard(ADJUSTMENT)
    return [ADJUSTMENT] + sorted(types)


def empty_entries(ui_keys, measures):
    cols = {k: pd.Series(dtype="object") for k in ui_keys}
    cols.update({m: pd.Series(dtype="float") for m in measures})
    return pd.DataFrame(cols)


def seed_from_existing(existing, ui_keys, measures):
    """Entry rows pre-filled from the adjustments already applied."""
    if existing is None or existing.empty:
        return empty_entries(ui_keys, measures)
    df = existing.copy()
    df[CHANNEL] = [channel_label(o, d) for o, d in
                   zip(df["ORDER_CHANNEL"], df["DELIVERY_CHANNEL"])]
    return df[ui_keys + measures].reset_index(drop=True)


def clean_entries(edited, ui_keys, key_labels, data_keys, measures):
    """Validate the grid and return ``(clean_df, errors, dirty)``.

    - Fully blank rows (the editor's empty trailing row) are dropped silently.
    - A row with values but a missing dropdown is an error, never guessed.
    - Blank measure cells are 0, matching the vault's DEFAULT 0.
    - The same key entered twice is an error: both lines would hash to the same
      hub key and write two satellite rows at one LDTS.

    ``dirty`` is True if the user has typed anything at all, valid or not —
    it is what protects the entries from a silent store/day change.
    """
    if edited is None or edited.empty:
        return pd.DataFrame(columns=data_keys + measures), [], False

    df = edited.reset_index(drop=True).copy()
    for k in ui_keys:
        df[k] = df[k].where(df[k].notna(), "").astype(str).str.strip()
    vals = df[measures].apply(pd.to_numeric, errors="coerce")

    key_set = df[ui_keys] != ""
    has_val = vals.notna() & (vals.abs() > 0)
    keep = key_set.any(axis=1) | has_val.any(axis=1)
    complete = key_set.all(axis=1)

    errors = []
    for i in df.index[keep & ~complete]:
        missing = [key_labels[k] for k in ui_keys if not key_set.at[i, k]]
        errors.append(f"Row {i + 1}: choose a {' and '.join(missing)}.")

    clean = df.loc[keep & complete, ui_keys].copy()
    clean[measures] = vals.loc[clean.index].fillna(0.0)
    if CHANNEL in ui_keys:
        # A label without the separator can only be a bare 'Adjustment'
        parts = [(s.split(CHANNEL_SEP, 1) + [s])[:2] for s in clean[CHANNEL]]
        clean["ORDER_CHANNEL"] = [p[0] for p in parts]
        clean["DELIVERY_CHANNEL"] = [p[1] for p in parts]
    clean = clean[data_keys + measures].reset_index(drop=True)

    dup = clean[clean.duplicated(data_keys, keep=False)]
    for key in dup[data_keys].drop_duplicates().itertuples(index=False):
        errors.append(f"{' / '.join(map(str, key))} is entered more than once — "
                      f"combine it into one line.")

    return clean, errors, bool(keep.any())


def stage_lines(clean, existing, data_keys, measures, clear_all=False):
    """Apply the overwrite rule: the lines that will actually be written.

    Entering any line replaces the day's adjustments for this section, so every
    existing adjustment line that was not re-entered is staged as a zero row.
    With nothing entered the section is left alone — unless ``clear_all``, which
    stages zero rows for every existing line.
    """
    entered = clean.assign(**{SOURCE: ENTERED})
    if entered.empty and not clear_all:
        return entered
    if existing is None or existing.empty:
        return entered

    existing_keys = existing[data_keys].drop_duplicates()
    merged = existing_keys.merge(entered[data_keys], on=data_keys, how="left", indicator=True)
    zeroed = merged.loc[merged["_merge"] == "left_only", data_keys].copy()
    for m in measures:
        zeroed[m] = 0.0
    zeroed[SOURCE] = ZEROED
    return pd.concat([entered, zeroed], ignore_index=True)


def _by_key(df, keys, cols):
    if df is None or df.empty:
        return pd.DataFrame(columns=keys + cols).set_index(keys)
    return df.groupby(keys, dropna=False)[cols].sum()


def build_preview(base, existing, staged, keys, measures, extra_base_cols=()):
    """Return ``(current, new)`` frames indexed by ``keys``.

    The RPT tables already include previously applied adjustments, and the new
    entry *replaces* them, so: new = current − existing adjustments + staged.
    Without backing the existing adjustments out, re-entering an adjustment
    would count it twice in the preview.

    ``extra_base_cols`` (e.g. GUAM_GST) are carried from ``base`` unchanged
    into both frames.
    """
    cur = _by_key(base, keys, list(measures) + list(extra_base_cols))
    old = _by_key(existing, keys, list(measures))
    stg = _by_key(staged, keys, list(measures))
    idx = cur.index.union(old.index).union(stg.index)
    cur = cur.reindex(idx, fill_value=0).astype(float)
    old = old.reindex(idx, fill_value=0).astype(float)
    stg = stg.reindex(idx, fill_value=0).astype(float)

    new = cur.copy()
    new[list(measures)] = cur[list(measures)] - old[list(measures)] + stg[list(measures)]
    return cur, new


def changed_mask(current, new, cols):
    return ((new[cols] - current[cols]).abs() > _TOL).any(axis=1)


def preview_formats(measures, extra=None):
    """Styler number formats: a Styler's display values take precedence over
    column_config formats, so they are set here explicitly."""
    fmts = {f: "{:,.0f}" if dec == 0 else "{:,.2f}" for f, (_l, _c, dec) in measures.items()}
    fmts.update(extra or {})
    return fmts


def highlight_rows(df, mask, formats):
    """Styler highlighting the rows the commit will change (``df`` must have a
    positional index; a trailing totals row is never highlighted)."""
    def _row(r):
        hit = bool(mask.iloc[r.name]) if r.name < len(mask) else False
        return ["background-color: #fff3cd" if hit else ""] * len(r)
    fmts = {c: f for c, f in formats.items() if c in df.columns}
    return df.style.apply(_row, axis=1).format(fmts, na_rep="")


def with_total(df, label_col, num_cols, label="Total"):
    """Append a totals row for display."""
    if df.empty:
        return df
    total = {c: df[c].sum() for c in num_cols if c in df.columns}
    total[label_col] = label
    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)


TEXT_LABELS = {
    "ORDER_CHANNEL": "Order Channel",
    "DELIVERY_CHANNEL": "Delivery Channel",
    "PAYMENT_TYPE": "Payment Type",
    "ADJUSTED_BY": "Adjusted By",
    "AUDIT_NOTE": "Audit Note",
    "ADJUSTMENT_SOURCE": "Source",
    SOURCE: "Line",
}


def number_config(measures, label_overrides=None):
    """`st.column_config` for measure columns (from the config tuples), plus
    readable headers for the key/text columns."""
    label_overrides = label_overrides or {}
    cfg = {c: st.column_config.TextColumn(lbl) for c, lbl in TEXT_LABELS.items()}
    for field, (label, _sat_col, decimals) in measures.items():
        cfg[field] = st.column_config.NumberColumn(
            label_overrides.get(field, label),
            format="%d" if decimals == 0 else "%.2f",
            step=1 if decimals == 0 else 0.01,
        )
    return cfg


def show_errors(errors):
    if errors:
        st.error("**Fix these before committing:**\n\n" +
                 "\n".join(f"- {e}" for e in errors))


def render_entry_grid(prefix, nonce, section, ui_keys, key_labels, key_config,
                      data_keys, measures, existing):
    """Render one entry grid and publish its plan to ``_<prefix>_plan``.

    The grid's input frame lives in ``_<prefix>_seed`` and its widget key only
    changes when the seed is deliberately replaced (pre-fill, clear, new
    store/day, commit). `st.data_editor` keeps the user's edits only while its
    input frame and key are unchanged, so nothing else may rebuild the seed.

    The plan — ``{'staged', 'errors', 'dirty'}`` — is what the Review & Commit
    tab reads. Returns it as well.
    """
    measure_cols = list(measures)
    seed_key, ver_key = f"_{prefix}_seed", f"_{prefix}_ver"
    seed = st.session_state.get(seed_key)
    if seed is None:
        seed = st.session_state[seed_key] = empty_entries(ui_keys, measure_cols)

    b1, b2, _ = st.columns([2, 1, 4])
    if b1.button(f"↺ Start from existing {section} adjustments", disabled=existing.empty,
                 key=f"{prefix}_prefill_{nonce}",
                 help="Replace the lines below with the adjustments already applied, "
                      "so you can edit them rather than re-type them."):
        seed = st.session_state[seed_key] = seed_from_existing(existing, ui_keys, measure_cols)
        st.session_state[ver_key] = st.session_state.get(ver_key, 0) + 1
    if b2.button("🗑 Clear lines", key=f"{prefix}_clear_lines_{nonce}"):
        seed = st.session_state[seed_key] = empty_entries(ui_keys, measure_cols)
        st.session_state[ver_key] = st.session_state.get(ver_key, 0) + 1

    cfg = number_config(measures)
    cfg.update(key_config)
    edited = st.data_editor(
        seed,
        key=f"{prefix}_editor_{nonce}_{st.session_state.get(ver_key, 0)}",
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_order=ui_keys + measure_cols,
        column_config=cfg,
    )

    clean, errors, dirty = clean_entries(edited, ui_keys, key_labels, data_keys, measure_cols)

    clear_all = False
    if clean.empty and not existing.empty:
        clear_all = st.checkbox(
            f"Remove all existing {section} adjustments for this day (set them to zero)",
            key=f"{prefix}_clear_all_{nonce}")

    staged = stage_lines(clean, existing, data_keys, measure_cols, clear_all)
    show_errors(errors)

    zeroed = staged[staged[SOURCE] == ZEROED] if not staged.empty else staged
    if not zeroed.empty:
        st.warning(f"⚠️ {len(zeroed)} existing {section} adjustment line(s) not re-entered "
                   f"will be **set to zero**: "
                   + ", ".join(" / ".join(map(str, k))
                               for k in zeroed[data_keys].itertuples(index=False)))

    plan = {"staged": staged, "errors": errors, "dirty": dirty or clear_all}
    st.session_state[f"_{prefix}_plan"] = plan
    return plan
