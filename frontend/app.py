import streamlit as st
from utils.api_client import health, me
from utils.auth import logout
from views import login, scan, result, repository, dashboard, admin_users, rules_info

st.set_page_config(page_title="Legal Metrology Compliance Checker", page_icon="⚖️", layout="wide")

st.markdown("""
<style>
    :root { color-scheme: light; }
    .stApp, [data-testid="stAppViewContainer"] { background: linear-gradient(145deg, #f5f7ff 0%, #fff7ed 52%, #effbf6 100%); color: #172033; }
    [data-testid="stHeader"] { background: rgba(245,247,255,.94); }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #263b78 0%, #53378c 100%); }
    [data-testid="stSidebar"] *, [data-testid="stSidebar"] label, [data-testid="stSidebar"] p { color: #fff !important; }
    [data-testid="stSidebar"] div.stButton > button { color: #172033 !important; background: #fff !important; border-color: #d2dcf0 !important; }
    [data-testid="stSidebar"] div.stButton > button:hover { color: #172033 !important; background: #eef2ff !important; }
    .stApp h1, .stApp h2, .stApp h3, .stApp h4 { color: #1b2c50 !important; font-weight: 750; }
    .stApp p, .stApp label, .stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stCaptionContainer"] { color: #202b3f; }
    .stApp [data-testid="stCaptionContainer"] { color: #48566d !important; }
    [data-testid="stMetric"] { background: #fff; color: #172033; border: 1px solid #c8d5ef; border-top: 4px solid #5865d9; padding: 16px; border-radius: 14px; box-shadow: 0 4px 14px #243a6418; }
    [data-testid="stMetric"] label, [data-testid="stMetricValue"] { color: #172033 !important; }
    .stApp input, .stApp textarea, .stApp [data-baseweb="select"] > div { background: #fff !important; color: #172033 !important; border-color: #8999b4 !important; }
    .stApp input::placeholder, .stApp textarea::placeholder { color: #66748b !important; opacity: 1; }
    .stApp [data-baseweb="select"] *, .stApp [role="option"] { color: #172033 !important; }
    div.stButton > button, div.stFormSubmitButton > button { border-radius: 10px; font-weight: 700; border: 1px solid #4353bd; transition: transform .15s ease, box-shadow .15s ease; }
    div.stButton > button:hover, div.stFormSubmitButton > button:hover { transform: translateY(-2px); box-shadow: 0 5px 14px #293c842d; }
    div.stForm, [data-testid="stExpander"], [data-testid="stFileUploader"] { border-radius: 14px; }
    [data-testid="stFileUploader"] section { background: #fff; border: 2px dashed #5865d9; border-radius: 14px; }
    [data-testid="stTabs"] button[role="tab"] { color: #34415a; font-weight: 700; }
    [data-testid="stTabs"] button[aria-selected="true"] { color: #3547bf !important; border-bottom-color: #5865d9 !important; }
    [data-testid="stAlert"] { border-radius: 12px; }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { transition-duration: .01ms !important; animation-duration: .01ms !important; } }
</style>
""", unsafe_allow_html=True)

DISCLAIMER = "Automated screening result. Findings must be verified by an authorised officer."

def init_state():
    defaults = {"token": None, "user": None, "selected_scan_id": None,
                "last_scan": None, "report_cache": {}, "repo_page": 1,
                "notice": None, "selected_page": "Dashboard"}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_state()

if not st.session_state.token:
    login.render()
else:
    try:
        current = me()
        st.session_state.user = current
    except Exception as exc:
        st.session_state.notice = "Session expired. Please log in again."
        logout()
        st.rerun()

    user = st.session_state.user or {}
    role = user.get("role", "inspector")
    # Apply cross-page navigation before the radio widget is created. Updating
    # its state after creation raises a StreamlitAPIException.
    pending_page = st.session_state.pop("pending_page", None)
    if pending_page:
        st.session_state.selected_page = pending_page
    with st.sidebar:
        st.markdown("## ⚖️ Legal Metrology")
        st.caption("Compliance Checker")
        st.write(user.get("name", "User"))
        st.caption(role.title())
        st.divider()
        pages = {
            "Dashboard": dashboard.render,
            "New Scan": scan.render,
            "Repository": repository.render,
            "Scan Result": result.render,
            "Rules Reference": rules_info.render,
        }
        if role == "admin":
            pages["Admin Users"] = admin_users.render
        if st.session_state.selected_page not in pages:
            st.session_state.selected_page = "Dashboard"
        selected = st.radio("Navigation", list(pages.keys()), key="selected_page", label_visibility="collapsed")
        st.divider()
        if st.button("Log out", use_container_width=True):
            logout()
            st.rerun()
    try:
        status = health()
        if status.get("status") != "ok":
            st.warning("Backend not reachable.")
    except Exception:
        st.warning("Backend not reachable. Check that the FastAPI server is running.")
    pages[selected]()
    st.divider()
    st.caption(DISCLAIMER)
