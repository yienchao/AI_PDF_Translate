"""Simple Password Authentication for PDF Translation App"""
import streamlit as st
import os

# Get password from environment variable
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

def require_auth():
    """
    Simple password protection.
    Set APP_PASSWORD environment variable to enable.
    If not set, app runs without authentication.
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

    # Show password form
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.title("PDF Translator")
        st.markdown("Enter password to access the app")

        password = st.text_input("Password", type="password", key="password_input")

        if st.button("Enter", type="primary", use_container_width=True):
            if password == APP_PASSWORD:
                st.session_state.authenticated = True
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
            st.rerun()

def get_user_id():
    """Return None - no user tracking with simple password auth"""
    return None

def get_current_user():
    """Return None - no user tracking with simple password auth"""
    return None
