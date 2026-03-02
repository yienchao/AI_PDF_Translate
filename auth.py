"""Simple Password Authentication for PDF Translation App"""
import hashlib
import streamlit as st
import os

# Get password from environment variable
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

def _get_auth_token():
    """Generate a short token from the password for session persistence."""
    if APP_PASSWORD:
        return hashlib.sha256(APP_PASSWORD.encode()).hexdigest()[:12]
    return None

def require_auth():
    """
    Simple password protection.
    Set APP_PASSWORD environment variable to enable.
    If not set, app runs without authentication.

    Auth state is persisted via URL query param so it survives
    Streamlit session reconnections (e.g., during long translations).
    """
    # If no password is configured, allow access (local dev mode)
    if not APP_PASSWORD:
        return True

    # Initialize session state
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    # If already authenticated, allow access
    if st.session_state.authenticated:
        return True

    # Check for persistent auth token in URL (survives session reconnections)
    auth_token = _get_auth_token()
    if auth_token and st.query_params.get("s") == auth_token:
        st.session_state.authenticated = True
        return True

    # Show password form
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.title("PDF Translator")
        st.markdown("Enter password to access the app")

        password = st.text_input("Password", type="password", key="password_input")

        if st.button("Enter", type="primary", use_container_width=True):
            if password == APP_PASSWORD:
                st.session_state.authenticated = True
                st.query_params["s"] = auth_token  # Persist in URL
                st.rerun()
            else:
                st.error("Incorrect password")

        st.stop()

def display_user_info():
    """Display logout button in sidebar if authenticated"""
    if APP_PASSWORD and st.session_state.get("authenticated"):
        st.sidebar.markdown("---")
        if st.sidebar.button("Logout", use_container_width=True):
            st.session_state.authenticated = False
            if "s" in st.query_params:
                del st.query_params["s"]
            st.rerun()

def get_user_id():
    """Return None - no user tracking with simple password auth"""
    return None

def get_current_user():
    """Return None - no user tracking with simple password auth"""
    return None
