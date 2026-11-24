import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo
from utils.config import STATUS_LABELS, STATUS_COLORS, SEVERITY_COLORS

def status_badge(status):
    label = STATUS_LABELS.get(status, status.replace("_", " ").title())
    color = STATUS_COLORS.get(status, "#777777")
    st.markdown(f'<span style="background:{color};color:white;padding:5px 10px;border-radius:14px;font-size:0.85rem">{label}</span>', unsafe_allow_html=True)

def severity_badge(severity):
    color = SEVERITY_COLORS.get(severity, "#777777")
    st.markdown(f'<span style="background:{color};color:white;padding:4px 9px;border-radius:12px;font-size:0.8rem">{severity.title()}</span>', unsafe_allow_html=True)

def rule_icon(status):
    return {"pass": "✅", "fail": "❌", "not_checked": "⚪"}.get(status, "⚪")

def ist_time(value):
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return value

def error_box(exc):
    st.error(getattr(exc, "message", str(exc)))

def disclaimer():
    st.caption("Automated screening result. Findings must be verified by an authorised officer.")
