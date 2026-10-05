"""Authentication and permission utilities.

Inside Streamlit in Snowflake, CURRENT_ROLE() is the *app owner's* role, not the
viewer's, so every check goes through SHOW GRANTS TO USER instead. Role
inheritance is not walked: grant the editor role to users directly.

Every function fails closed — a broken permission check must never grant access.
"""
import streamlit as st

EDIT_ROLES = {'RL_STREAMLIT_ADMIN', 'RL_STREAMLIT_EDITOR'}

_ROLES_KEY = '_user_roles'
_DISPLAY_ROLE_KEY = '_user_display_role'


def get_user_roles(session):
    """Return the set of roles directly granted to the current user.

    Cached in session state: this is two round-trips to Snowflake, and the app
    would otherwise re-run it on every interaction. A failed lookup is not
    cached, so a transient error does not pin the user to view-only for the
    rest of the session.
    """
    if _ROLES_KEY in st.session_state:
        return st.session_state[_ROLES_KEY]
    try:
        username = session.sql("SELECT CURRENT_USER()").collect()[0][0]
        # Quoted: usernames are generally email addresses
        result = session.sql(f'SHOW GRANTS TO USER "{username}"').collect()
        roles = {row['role'].upper() for row in result if row['role'] is not None}
    except Exception:
        return set()
    st.session_state[_ROLES_KEY] = roles
    return roles


def has_edit_permission(session):
    """Check if the invoking user has edit permissions based on their granted roles"""
    return bool(get_user_roles(session) & EDIT_ROLES)


def get_display_role(session):
    """Return the most relevant app role for display, falling back to CURRENT_ROLE().

    Display only — never branch on this.
    """
    if _DISPLAY_ROLE_KEY in st.session_state:
        return st.session_state[_DISPLAY_ROLE_KEY]
    try:
        user_roles = get_user_roles(session)
        role = None
        for candidate in ('RL_STREAMLIT_ADMIN', 'RL_STREAMLIT_EDITOR'):
            if candidate in user_roles:
                role = candidate
                break
        if role is None:
            # Fall back to the actual session role
            result = session.sql("SELECT CURRENT_ROLE()").collect()
            role = result[0][0] if result else "UNKNOWN"
    except Exception:
        return "UNKNOWN"
    st.session_state[_DISPLAY_ROLE_KEY] = role
    return role
