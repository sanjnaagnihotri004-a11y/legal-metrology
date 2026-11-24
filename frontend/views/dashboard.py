import streamlit as st
import pandas as pd
import plotly.express as px
from utils.api_client import get_stats, ApiError
from utils.ui import status_badge, ist_time, error_box

def render():
    st.title("📊 Compliance dashboard")
    a,b,c = st.columns([1,1,2])
    start = a.date_input("From",value=None,key="dash_from")
    end = b.date_input("To",value=None,key="dash_to")
    if c.button("↻ Refresh"): st.rerun()
    params={}
    if start: params["date_from"]=str(start)
    if end: params["date_to"]=str(end)
    try:
        data=get_stats(params)
        metrics=[("Total scans",data.get("total_scans",0)),("Compliant",data.get("compliant",0)),
                 ("Non-compliant",data.get("non_compliant",0)),("Needs review",data.get("needs_review",0)),
                 ("Compliance rate",f"{data.get('compliance_rate',0):.1f}%"),("Scans today",data.get("scans_today",0))]
        cols=st.columns(3)
        for i,(label,value) in enumerate(metrics): cols[i%3].metric(label,value)
        st.divider()
        left,right=st.columns(2)
        with left:
            st.subheader("Scan status")
            chart=pd.DataFrame({"Status":["Compliant","Non-compliant","Needs review"],
                                "Count":[data.get("compliant",0),data.get("non_compliant",0),data.get("needs_review",0)]})
            if chart["Count"].sum(): st.plotly_chart(px.pie(chart,names="Status",values="Count",hole=.55),use_container_width=True)
            else: st.info("No scan data for this period.")
        with right:
            st.subheader("Top violated rules")
            rules=pd.DataFrame(data.get("top_violated_rules",[]))
            if not rules.empty:
                rules["label"]=rules["rule_id"]+": "+rules["title"]
                st.plotly_chart(px.bar(rules,x="count",y="label",orientation="h"),use_container_width=True)
            else: st.info("No violations recorded.")
        st.subheader("Violations over time")
        trend=pd.DataFrame(data.get("violations_over_time",[]))
        if not trend.empty: st.plotly_chart(px.line(trend,x="date",y="count",markers=True),use_container_width=True)
        else: st.info("No trend data available.")
        st.subheader("Scans by category")
        cats=pd.DataFrame(data.get("by_category",[]))
        if not cats.empty: st.plotly_chart(px.bar(cats,x="category",y=["compliant","non_compliant"],barmode="stack"),use_container_width=True)
        else: st.info("No category data available.")
        st.subheader("🕘 Recent scans")
        for item in data.get("recent_scans",[]):
            with st.container(border=True):
                x,y,z=st.columns([3,2,1])
                x.write(f"**{item.get('product_name')} — {item.get('brand')}**")
                x.caption(ist_time(item.get("created_at")))
                with y: status_badge(item.get("status","needs_review"))
                if z.button("↗ Open",key=f"dash_open_{item.get('id')}"):
                    st.session_state.selected_scan_id = item.get("id")
                    st.session_state.pending_page = "Scan Result"
                    st.rerun()
    except ApiError as exc: error_box(exc)
