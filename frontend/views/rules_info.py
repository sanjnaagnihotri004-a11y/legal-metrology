import streamlit as st
from utils.api_client import get_rules, ApiError
from utils.ui import severity_badge, error_box

def render():
    st.title("Rules reference")
    st.write("Reference information is loaded from the backend. Clause wording is not hard-coded in the frontend.")
    try:
        rules=get_rules()
        for rule in rules:
            with st.container(border=True):
                a,b=st.columns([3,1])
                a.markdown(f"**{rule.get('rule_id')} — {rule.get('title')}**")
                a.caption(f"{rule.get('clause','')} • {rule.get('description','')}")
                with b: severity_badge(rule.get("severity","major"))
    except ApiError as exc: error_box(exc)
