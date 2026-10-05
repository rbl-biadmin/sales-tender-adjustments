"""
Sales & Tender Adjustments - Main Application
Streamlit app for loading one-store / one-day sales and tender adjustments into
the Snowflake Data Vault, across all divisions and brands.
"""
from config import DB_EDW, APP_VERSION
import streamlit as st
from snowflake.snowpark.context import get_active_session
from datetime import datetime, timedelta

# Import utilities
from utils.auth import has_edit_permission, get_display_role
from utils.state import show_flash

# Import tab modules
from tabs.store_date import render_store_date_tab
from tabs.sales_adjustments import render_sales_tab
from tabs.tender_adjustments import render_tender_tab
from tabs.commit import render_commit_tab
from tabs.audit_log import render_audit_log_tab
from tabs.help import render_help_tab

# Page configuration — must be the first Streamlit call
st.set_page_config(page_title="Sales & Tender Adjustments", layout="wide")

# ============================================================================
# CUSTOM CSS TO MAXIMISE SCREEN SPACE
# The grids are the whole app; Streamlit's defaults waste about a third of the
# vertical space. Tuned as a set — changing one value in isolation looks worse.
# ============================================================================
st.markdown("""
    <style>
        /* Shrink main container padding */
        .block-container {
            padding-top: 0.4rem !important;
            padding-bottom: 0 !important;
            max-width: 100% !important;
        }

        /* Smaller, tighter title */
        h1 { font-size: 1.3rem !important; margin: 0 0 0.1rem 0 !important; padding: 0 !important; }
        h2 { font-size: 1.0rem !important; margin: 0.15rem 0 !important; }
        h3 { font-size: 0.9rem  !important; margin: 0.1rem  0 !important; }

        /* Caption tight under title */
        .stCaption p { font-size: 0.72rem !important; margin: 0 !important; line-height: 1.2; }

        /* Tabs — smaller text, less padding */
        .stTabs [data-baseweb="tab-list"] { gap: 1px; }
        .stTabs [data-baseweb="tab"] { padding: 3px 10px !important; font-size: 0.82rem !important; }
        .stTabs [data-baseweb="tab-panel"] { padding-top: 0.35rem !important; }

        /* Reduce gap between stacked elements */
        div[data-testid="stVerticalBlock"] > div { gap: 0.2rem !important; }

        /* Compact expander */
        .streamlit-expanderHeader  { padding: 0.15rem 0.5rem !important; font-size: 0.82rem !important; }
        .streamlit-expanderContent { padding: 0.35rem 0.5rem !important; }
        details > summary { padding: 0.15rem 0.5rem !important; font-size: 0.82rem !important; }

        /* Compact text inputs and labels */
        .stTextInput  > label { font-size: 0.78rem !important; margin-bottom: 1px !important; }
        .stTextInput  input   { padding: 0.2rem 0.4rem !important; font-size: 0.82rem !important; }
        .stMultiSelect > label { font-size: 0.78rem !important; margin-bottom: 1px !important; }
        .stMultiSelect [data-baseweb="select"] > div { font-size: 0.82rem !important; padding: 1px 4px !important; }

        /* Compact buttons */
        .stButton > button { padding: 0.2rem 0.75rem !important; font-size: 0.82rem !important; }

        /* Compact alerts */
        div[data-testid="stAlert"] { padding: 0.4rem 0.6rem !important; font-size: 0.82rem !important; }

        /* Column padding */
        div[data-testid="column"] { padding: 0 0.3rem !important; }

        /* Remove divider vertical margin */
        hr { margin: 0.15rem 0 !important; }
    </style>
""", unsafe_allow_html=True)

# ============================================================================
# SESSION TIMEOUT (housekeeping)
# ============================================================================
TIMEOUT_MINUTES = 15  # Auto-logout after 15 minutes of inactivity

_now = datetime.now()
if 'last_activity' not in st.session_state:
    st.session_state.last_activity = _now

# Time since the previous script run. This MUST be measured before
# last_activity is updated — updating it first makes the delta always zero and
# both checks below unreachable.
time_inactive = _now - st.session_state.last_activity

# Note: Streamlit only re-runs the script on interaction, so an idle browser
# never triggers this on its own — it fires on the user's next interaction.
# Housekeeping, not a security control.
if time_inactive > timedelta(minutes=TIMEOUT_MINUTES):
    st.error("⏱️ Your session has timed out due to inactivity. Please refresh the page to continue.")
    st.info("This is for security purposes. Any adjustments you had not committed will need to be re-entered.")
    st.stop()  # deliberately before the update below, so the page stays stopped

# Warn 5 minutes before timeout
if time_inactive > timedelta(minutes=TIMEOUT_MINUTES - 5):
    minutes_left = TIMEOUT_MINUTES - int(time_inactive.total_seconds() / 60)
    st.warning(f"⚠️ Your session will timeout in approximately {minutes_left} minutes. Click anywhere to stay active.")

# Record this interaction for the next run
st.session_state.last_activity = _now

# ============================================================================
# MAIN APPLICATION
# ============================================================================

# Get the current session (only resolves inside Snowflake — there is no local run)
session = get_active_session()

# Get current user from Streamlit context. Reaches into Streamlit internals and
# the shape of user_info varies by runtime version, so this must never break the
# page. CURRENT_USER() is not a substitute: inside SiS it returns the app owner.
current_user = None
try:
    import streamlit.runtime.scriptrunner as scriptrunner
    ctx = scriptrunner.get_script_run_ctx()
    if ctx and hasattr(ctx, 'user_info'):
        current_user = ctx.user_info.get('email') or ctx.user_info.get('user')
except Exception:
    pass

if not current_user:
    current_user = "UNKNOWN_USER"

# Get current role (user's actual app role, not the session owner's role)
current_role = get_display_role(session)

# Check permissions once and pass down — each call is two queries
is_editor = has_edit_permission(session)

# Application header. Showing DB_EDW is how a user tells dev from production.
st.title("🧾 Sales & Tender Adjustments")
st.caption(f"Logged in as: **{current_user}** | Role: **{current_role}** | "
           f"Database: **{DB_EDW}** | Version: `{APP_VERSION}`")

# The outcome of a commit, stashed across the st.rerun() that followed it
show_flash()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📍 1. Store & Date",
    "💰 2. Sales Adjustments",
    "💳 3. Tender Adjustments",
    "✅ 4. Review & Commit",
    "📊 Audit Log",
    "❓ Help",
])


def _guard(label, fn, *args, plan_key=None):
    """One broken tab must not take the app down.

    For an entry tab, its staged plan is dropped on error: otherwise the commit
    tab would read the plan left over from the previous run and commit it.
    """
    try:
        fn(*args)
    except Exception as e:
        if plan_key:
            st.session_state.pop(plan_key, None)
        st.error(f"The {label} tab hit an error. Your entries on other tabs are kept.")
        st.exception(e)


# Rendered in tab order on every run: tab 1 settles the store/day, tabs 2-3
# publish their staged plans, tab 4 reads them.
with tab1:
    _guard("Store & Date", render_store_date_tab, session, current_user)
with tab2:
    _guard("Sales Adjustments", render_sales_tab, session, is_editor, plan_key="_sa_plan")
with tab3:
    _guard("Tender Adjustments", render_tender_tab, session, is_editor, plan_key="_ta_plan")
with tab4:
    _guard("Review & Commit", render_commit_tab, session, current_user, current_role, is_editor)
with tab5:
    _guard("Audit Log", render_audit_log_tab, session, is_editor)
with tab6:
    _guard("Help", render_help_tab, current_user, current_role, is_editor)
