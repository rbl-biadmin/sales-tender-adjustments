"""Help and Documentation Tab.

The app's only user documentation — written for non-technical users. Update it
with every functional change: new tab, changed fields, new rule.
"""
import streamlit as st
from config import APP_VERSION

_JIRA = "https://restaurantbrands.atlassian.net/servicedesk/customer/portal/17"
_APP_URL = ("https://app.snowflake.com/restaurantbrands/ualczxk/#/streamlit-apps/"
            "STREAMLIT_APPS.DATA_MANAGEMENT.SALES_TENDER_ADJUSTMENTS")
_UPDATED = "October 2026"


def render_help_tab(current_user, current_role, is_editor):
    """Render the Help/Documentation tab"""

    st.header("📖 Help & Documentation")

    # 1. Bookmark link
    st.subheader("🔗 Bookmark This App")
    st.info("**Direct Link:**")
    st.code(_APP_URL, language="text")
    st.caption("Copy and bookmark this link for quick access!")

    # 2. Access level
    st.divider()
    st.subheader("🔐 Your Access Level")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("User", current_user)
        st.metric("Role", current_role)
    with col2:
        if is_editor:
            st.success("✅ You have **EDIT** access — you can enter and commit adjustments")
        else:
            st.warning("👁️ You have **VIEW-ONLY** access — you can view a store's figures "
                       "and existing adjustments")
    st.caption("You only see the stores your Snowflake access allows. "
               f"Need different access? [Log a Jira ticket]({_JIRA})")

    # 3. Features by tab
    st.divider()
    st.subheader("📋 Features by Tab")

    with st.expander("📍 Store & Date", expanded=False):
        st.markdown("""
        - Narrow by **Division** and **Brand**, pick the **Store**, then the **Date**.
        - Shows, read only, what is in the warehouse for that store/day:
          **Sales** and **Tenders** by channel (these already include any adjustments
          applied earlier), and the **existing sales and tender adjustments** with who
          applied them, when, and why.
        - The app works on **one store, one day at a time**. For bulk adjustments,
          raise a Jira ticket.
        - If you have entered adjustments and change the store or date, you are asked
          to confirm before they are discarded.
        """)

    with st.expander("💰 Sales Adjustments", expanded=False):
        st.markdown("""
        **Fields per line:** Order | Delivery Channel, Transactions, Amount, Delivery Fees,
        Bottle Fee, Gift Card, TB Fund, Discount, Promos.

        - **Promos** are combined with Discount in reporting, so the preview and the
          Store & Date sales figures show Discount **incl. Promos**.

        - Enter the **change** to apply. Values can be positive or negative.
        - Order and delivery channel are picked together, from the pairs this store has
          traded in the last 14 days (plus any on the chosen day). Pick
          **Adjustment | Adjustment** for a general day adjustment where the channel is
          not known.
        - Blank cells count as **0**.
        - **Guam:** enter the Amount **incl. GST**. GST is calculated and removed from net
          sales when the adjustment is loaded.
        - **↺ Start from existing sales adjustments** copies the adjustments already
          applied into the grid, so you can change them rather than re-type them.
        - **Step 4 preview:** the day's sales after the commit, with changed rows
          highlighted, and the change in Report Net Sales.
        """)

    with st.expander("💳 Tender Adjustments", expanded=False):
        st.markdown("""
        **Fields per line:** Payment Type, Order | Delivery Channel, Tender Amount, Tip Amount.

        - All amounts **incl. tax / GST**. Values can be positive or negative.
        - Pick **Adjustment** as the payment type and/or channel where it is not known.
        - Blank cells count as **0**.
        - **Step 6 preview:** the day's tenders after the commit, changed rows highlighted.
        """)

    with st.expander("✅ Review & Commit", expanded=False):
        st.markdown("""
        - Lists exactly what will be written, including any existing lines being set
          to zero.
        - **Jira ticket number** is mandatory (e.g. DATA-1234). The ticket must already
          have the required approvals — tick the box to confirm it does.
        - **Audit reason** is mandatory. It is saved as *ticket: reason* with the
          adjustment and shown on the Store & Date tab next time anyone looks at this
          store/day.
        - Tick the box to confirm you checked the previews, then **Commit Changes**.
        - You can commit sales only, tenders only, or both. A section with nothing
          entered is left untouched.
        """)

    with st.expander("📊 Audit Log", expanded=False):
        st.markdown("""
        **Available to:** Editors and Admins only

        One row per commit attempt — who, when, which store/day, how many lines, the
        audit reason, and the outcome (**SUCCESS**, **PARTIAL** — saved but the mart
        update failed, or **FAILED** — nothing saved). Export to CSV.
        """)

    # 4. How to make changes
    st.divider()
    st.subheader("🎯 How to Make an Adjustment")
    st.markdown("""
    1. **Store & Date** — pick the store and the day; check the current figures.
    2. **Sales Adjustments** — add a line per channel to change; check the Step 4 preview.
    3. **Tender Adjustments** — add a line per payment type/channel; check the Step 6 preview.
    4. **Review & Commit** — enter the approved Jira ticket number and confirm its
       approvals, enter the audit reason, tick the confirmation, click **Commit Changes**.
    5. A green message confirms the save, and the Store & Date tab shows the new figures.
    6. Run a **Power BI refresh** to update the reporting. Adjustments dated more than
       7 days ago need a manual partition refresh — contact Support.

    ### ⚠️ Adjustments overwrite, they do not add up
    Committing sales adjustments **replaces** all existing sales adjustments for that
    store/day (and the same for tenders). Any existing line you do not re-enter is set
    to **zero**. To keep an existing adjustment, re-enter it — **↺ Start from existing**
    does this for you.

    Nothing is ever deleted: every commit adds new records, and the full history of
    who adjusted what, and why, is kept.
    """)

    # 5. Troubleshooting
    st.divider()
    st.subheader("🆘 Troubleshooting")

    with st.expander("Commit Changes button is greyed out"):
        st.markdown("""
        The yellow box above the button lists why — usually nothing has been entered
        yet, or a line is missing its channel / payment type, or the same channel is
        entered twice.
        """)

    with st.expander("\"Nothing was saved — the commit was rolled back\""):
        st.markdown(f"""
        Something failed while writing; **none** of the adjustment was saved and your
        entries are still on screen. Try again; if it persists,
        [log a Jira ticket]({_JIRA}) with the message shown.
        """)

    with st.expander("\"Saved … but the mart update failed\""):
        st.markdown(f"""
        The adjustment is stored, but the mart tables were not rebuilt. Click
        **Commit Changes** again to retry (it is safe — it writes the same values).
        If it fails again, [log a Jira ticket]({_JIRA}).
        """)

    with st.expander("\"Store … was not found in the Data Vault store hub\""):
        st.markdown(f"""
        The store exists in reporting but not in the Data Vault, so an adjustment
        cannot be linked to it. [Log a Jira ticket]({_JIRA}).
        """)

    with st.expander("A store or channel is missing from the list"):
        st.markdown(f"""
        - Stores: you only see stores your access allows.
        - Channels / payment types: the lists show what the store traded in the last
          14 days and on the chosen day. Use **Adjustment** if yours is not listed, or
          [log a Jira ticket]({_JIRA}).
        """)

    with st.expander("Access denied / View-only"):
        st.markdown(f"""
        - Check your role at the top of this page
        - [Log a Jira ticket]({_JIRA}) to request editor access
        - Required: `RL_STREAMLIT_EDITOR` or `RL_STREAMLIT_ADMIN`
        """)

    # 6. Support and version
    st.divider()
    st.subheader("🆘 Support")
    st.info(f"**Need help?** [Log a Jira ticket]({_JIRA})")

    st.divider()
    st.caption(f"**Version:** {APP_VERSION} | **Updated:** {_UPDATED} | **By:** Theta Data Team")
