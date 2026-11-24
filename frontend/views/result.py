import streamlit as st
from utils.api_client import get_scan, get_image_bytes, recheck_scan, add_evidence, download_report, ApiError
from utils.ui import status_badge, severity_badge, rule_icon, ist_time, error_box

FIELD_LABELS = {"manufacturer_name_address":"Manufacturer / packer / importer",
                "net_quantity":"Net quantity","mrp":"MRP","mfg_date":"Manufacture date",
                "consumer_care":"Consumer care"}

def render():
    st.title("Scan result")
    scan_id = st.session_state.get("selected_scan_id")
    if not scan_id:
        st.info("Select a scan from the Repository or create a New Scan.")
        return
    try:
        data = get_scan(scan_id)
    except ApiError as exc:
        error_box(exc); return
    product = data.get("product", {})
    c1,c2,c3,c4 = st.columns([2,1,1,1])
    c1.subheader(product.get("name","Product"))
    c1.caption(f"{product.get('brand','')} • {product.get('category','')}")
    with c2: status_badge(data.get("status","needs_review"))
    c3.metric("Compliance score", f"{data.get('score',0):.1f}%")
    c4.metric("Violations", data.get("violations_count",0))
    st.caption(f"Inspector: {data.get('inspector',{}).get('name','—')} • {ist_time(data.get('created_at'))}")
    if data.get("corrected"): st.info("✏️ Corrected manually")
    st.subheader("Rule-by-rule results")
    for rule in data.get("rule_results", []):
        with st.container(border=True):
            a,b,c = st.columns([.5,2,1])
            a.write(rule_icon(rule.get("status")))
            b.markdown(f"**{rule.get('rule_id')} — {rule.get('title')}**")
            b.caption(f"{rule.get('clause','')} • {rule.get('message','')}")
            with c: severity_badge(rule.get("severity","major"))
    st.subheader("Label images")
    col1,col2 = st.columns(2)
    for col, key, title in [(col1,"image_url","Original image"),(col2,"annotated_image_url","Backend annotated image")]:
        with col:
            st.markdown(f"**{title}**")
            path = data.get(key)
            if path:
                try: st.image(get_image_bytes(path), use_container_width=True)
                except Exception: st.caption("Image could not be loaded.")
            else: st.info("Image preview is available when connected to the backend.")
    st.subheader("Extracted declarations")
    fields = data.get("extracted_fields",{})
    for key, label in FIELD_LABELS.items():
        item = fields.get(key,{})
        found = item.get("found",False)
        confidence = item.get("confidence")
        value = item.get("value") if found else "Not found"
        suffix = f" • Confidence: {confidence*100:.0f}%" if confidence is not None else ""
        st.write(f"**{label}:** {value}{suffix}")
        if key == "net_quantity":
            st.caption(f"Quantity: {item.get('quantity','—')} {item.get('unit') or ''} | Font height: {item.get('font_height_mm','—')} mm | Minimum: {item.get('min_font_height_mm','—')} mm")
    with st.expander("Manual correction — edit OCR text"):
        st.caption("Only changed fields are sent to the backend for a fresh compliance check.")
        corrections = {}
        for key,label in FIELD_LABELS.items():
            old = fields.get(key,{}).get("value") or ""
            corrections[key] = st.text_input(label, value=old, key=f"correct_{scan_id}_{key}")
        if st.button("Re-run compliance check", type="primary"):
            changed = {k:v for k,v in corrections.items() if v != (fields.get(k,{}).get("value") or "")}
            if not changed: st.info("No changes to submit.")
            else:
                try:
                    with st.spinner("Rechecking corrected declarations..."):
                        updated = recheck_scan(scan_id, changed)
                    st.session_state.last_scan = updated
                    st.session_state.report_cache = {}
                    st.success("Compliance check updated."); st.rerun()
                except ApiError as exc: error_box(exc)
    st.subheader("Evidence")
    for ev in data.get("evidence",[]):
        st.write(f"📎 {ev.get('note') or 'Evidence'} — uploaded by {ev.get('uploaded_by','—')}")
    with st.form("evidence_form"):
        evidence_file = st.file_uploader("Attach evidence (JPG, PNG or PDF)", type=["jpg","jpeg","png","pdf"])
        evidence_note = st.text_input("Evidence note", max_chars=300)
        add = st.form_submit_button("Upload evidence")
    if add:
        if not evidence_file: st.error("Choose an evidence file.")
        elif len(evidence_file.getvalue()) > 10*1024*1024: st.error("File must be 10 MB or smaller.")
        else:
            try:
                add_evidence(scan_id,evidence_file,evidence_note)
                st.session_state.report_cache = {}; st.success("Evidence uploaded."); st.rerun()
            except ApiError as exc: error_box(exc)
    with st.expander("Raw OCR text"): st.text(data.get("ocr_text") or "No OCR text returned.")
    st.subheader("Download report")
    cols = st.columns(3)
    for col,fmt in zip(cols,["pdf","docx","csv"]):
        with col:
            key = (scan_id,fmt)
            if st.button(f"Prepare {fmt.upper()}", key=f"prepare_{fmt}"):
                try:
                    st.session_state.report_cache[key] = download_report(scan_id,fmt)
                except ApiError as exc: error_box(exc)
            if key in st.session_state.report_cache:
                st.download_button(f"Download {fmt.upper()}", st.session_state.report_cache[key],
                                   file_name=f"LM_Report_{scan_id}.{fmt}", key=f"download_{fmt}")
    st.caption("Automated screening result. Findings must be verified by an authorised officer.")
