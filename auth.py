"""Authentication Module for Streamlit PDF Translation App"""
import streamlit as st
from supabase_client import get_supabase_client
from typing import Optional

def init_auth_state():
    """Initialize authentication state in session"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None
    if "supabase" not in st.session_state:
        try:
            st.session_state.supabase = get_supabase_client()
        except ValueError as e:
            # If Supabase not configured, set to None (local testing mode)
            st.session_state.supabase = None
    if "auth_enabled" not in st.session_state:
        # Auth is enabled only if Supabase is configured
        st.session_state.auth_enabled = st.session_state.supabase is not None

    # Try to restore session from Supabase if auth is enabled
    if st.session_state.auth_enabled and not st.session_state.authenticated:
        try:
            user_response = st.session_state.supabase.client.auth.get_user()
            if user_response and user_response.user:
                st.session_state.authenticated = True
                st.session_state.user = user_response.user
        except Exception:
            # No valid session found, user needs to login
            pass

def login_page():
    """Display login page"""
    # Center the login form with columns (wider middle column)
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.title("PDF Translator - Login")
        st.markdown("Please sign in to access the PDF translation service")

        with st.form("login_form"):
            email = st.text_input("Email", placeholder="your.email@example.com")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Sign In", width="stretch")

            if submit:
                if not email or not password:
                    st.error("Please enter both email and password")
                else:
                    try:
                        # Sign in with Supabase
                        response = st.session_state.supabase.sign_in(email, password)

                        if response and response.user:
                            st.session_state.authenticated = True
                            st.session_state.user = response.user
                            st.success("Login successful!")
                            st.rerun()
                        else:
                            st.error("Invalid email or password")
                    except Exception as e:
                        st.error(f"Login failed: {str(e)}")

def logout():
    """Log out current user"""
    try:
        st.session_state.supabase.sign_out()
    except Exception:
        pass

    st.session_state.authenticated = False
    st.session_state.user = None
    st.rerun()

def require_auth():
    """
    Require authentication to access the page.
    Call this at the start of your main app.

    Returns:
        True if authenticated or auth disabled (local mode), otherwise shows login page and stops execution
    """
    init_auth_state()

    # If auth is not enabled (no Supabase config), allow access for local testing
    if not st.session_state.auth_enabled:
        return True

    # Auth is enabled, require login
    if not st.session_state.authenticated:
        login_page()
        st.stop()

    return True

def get_current_user() -> Optional[dict]:
    """
    Get current authenticated user

    Returns:
        User dict or None if not authenticated
    """
    if st.session_state.get("authenticated") and st.session_state.get("user"):
        return st.session_state.user
    return None

def get_user_id() -> Optional[str]:
    """
    Get current user ID

    Returns:
        User ID string or None if not authenticated
    """
    user = get_current_user()
    if user:
        return user.id
    return None

def display_user_info():
    """Display current user info in sidebar"""
    user = get_current_user()
    if user:
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**Logged in as:**")
        st.sidebar.markdown(f"{user.email}")

        if st.sidebar.button("🚪 Logout", width="stretch"):
            logout()
