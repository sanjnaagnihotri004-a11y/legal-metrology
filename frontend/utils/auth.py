import streamlit as st
from utils.api_client import login as api_login

def sign_in(email, password):
    data = api_login(email, password)
    st.session_state.token = data["access_token"]
    st.session_state.user = data["user"]

def logout():
    for key in ("token", "user", "selected_scan_id", "last_scan", "report_cache"):
        st.session_state[key] = None if key != "report_cache" else {}
