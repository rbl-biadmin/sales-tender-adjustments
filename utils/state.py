"""Cross-tab session state.

The app is a wizard: the Store & Date tab picks the store/day, the two entry
tabs stage adjustments for it, and the Review & Commit tab writes them. Every
tab renders on every run, in tab order, so the entry tabs always see this run's
selection and the commit tab always sees this run's staged plans.

Keys owned here:

    _adj_sel      the active store/day (dict) — what every tab works on
    _adj_nonce    bumped to reset every entry widget at once (new store/day,
                  successful commit); widget keys embed it
    _sa_*/_ta_*   the sales / tender entry tabs' own state, prefix 'sa' / 'ta'
    _adj_flash    a message stashed across an st.rerun()
"""
import streamlit as st

SEL_KEY = "_adj_sel"
NONCE_KEY = "_adj_nonce"
FLASH_KEY = "_adj_flash"
ENTRY_PREFIXES = ("sa", "ta")


def get_selection():
    return st.session_state.get(SEL_KEY)


def nonce():
    return st.session_state.get(NONCE_KEY, 0)


def has_entries():
    """True if either entry tab holds anything the user typed (valid or not)."""
    return any((st.session_state.get(f"_{p}_plan") or {}).get("dirty")
               for p in ENTRY_PREFIXES)


def reset_entries():
    """Discard everything staged in the entry tabs and the commit form."""
    for p in ENTRY_PREFIXES:
        for suffix in ("seed", "plan"):
            st.session_state.pop(f"_{p}_{suffix}", None)
    st.session_state[NONCE_KEY] = nonce() + 1


def set_selection(sel):
    st.session_state[SEL_KEY] = sel
    reset_entries()


def stash_flash(kind, text):
    """Stash a message to show after an st.rerun() — which discards anything
    written on the current run, so a message emitted just before it never
    reaches the browser."""
    st.session_state[FLASH_KEY] = (kind, text)


def show_flash():
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        getattr(st, flash[0])(flash[1])
