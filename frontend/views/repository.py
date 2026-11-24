import streamlit as st
from datetime import date
from utils.api_client import list_scans, ApiError
from utils.ui import status_badge, ist_time, error_box
from utils.config import CATEGORY_OPTIONS

def render():
    st.title("Scan repository")
    with st.expander("Search and filters", expanded=True):
        a,b,c = st.columns(3)
        q = a.text_input("Search product, brand or barcode")
        status = b.selectbox("Status",["All","compliant","non_compliant","needs_review"])
        category = c.selectbox("Category",["All"]+list(CATEGORY_OPTIONS.values()))
        d,e,f = st.columns(3)
        brand = d.text_input("Brand")
        date_from = e.date_input("From date", value=None)
        date_to = f.date_input("To date", value=None)
        if st.button("Clear filters"):
            st.rerun()
    page = st.session_state.get("repo_page",1)
    params = {"q":q,"page":page,"page_size":20}
    if status != "All": params["status"] = status
    if category != "All": params["category"] = category
    if brand: params["brand"] = brand
    if date_from: params["date_from"] = str(date_from)
    if date_to: params["date_to"] = str(date_to)
    try:
        result = list_scans(params)
        items = result.get("items",[])
        st.caption(f"{result.get('total',0)} scans found")
        if not items: st.info("No scans match your filters.")
        for item in items:
            with st.container(border=True):
                x,y,z = st.columns([3,2,1])
                x.markdown(f"**#{item.get('id')} — {item.get('product_name','Product')}**")
                x.caption(f"{item.get('brand','')} • {item.get('category','')} • {ist_time(item.get('created_at'))}")
                with y: status_badge(item.get("status","needs_review"))
                z.metric("Score",f"{item.get('score',0):.1f}%")
                if st.button("Open result",key=f"open_{item.get('id')}"):
                    st.session_state.selected_scan_id = item.get("id")
                    st.session_state.pending_page = "Scan Result"
                    st.rerun()
        total_pages = max(1,(result.get("total",0)+result.get("page_size",20)-1)//result.get("page_size",20))
        prev,nextc = st.columns(2)
        if prev.button("← Previous",disabled=page<=1): st.session_state.repo_page=page-1; st.rerun()
        if nextc.button("Next →",disabled=page>=total_pages): st.session_state.repo_page=page+1; st.rerun()
        st.caption(f"Page {page} of {total_pages}")
    except ApiError as exc: error_box(exc)
