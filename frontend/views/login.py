import streamlit as st
from utils.auth import sign_in
from utils.api_client import ApiError, health
from utils.ui import error_box

def render():
    left, center, right = st.columns([1, 1.2, 1])
    with center:
        st.markdown("<h1 style='text-align:center'>⚖️ Legal Metrology</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;color:gray'>Packaged Commodities Compliance Checker</p>", unsafe_allow_html=True)
        if st.session_state.get("notice"):
            st.warning(st.session_state.pop("notice"))
        try:
            health()
        except Exception:
            st.warning("Backend not reachable. You can still explore the interface in mock mode.")
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="name@example.com")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True, type="primary")
        if submitted:
            if not email or not password:
                st.error("Enter your email and password.")
            else:
                try:
                    sign_in(email, password)
                    st.rerun()
                except ApiError as exc:
                    error_box(exc)
                except Exception as exc:
                    st.error(str(exc))
        st.caption("Development accounts are supplied by your backend developer.")
