import streamlit as st
from utils.config import CATEGORY_OPTIONS
from utils.api_client import create_scan, ApiError
from utils.ui import error_box

def render():
    st.title("📷 New product label scan")
    st.write("Upload a clear photograph of the packaged product label for automated screening.")
    with st.expander("📸 Photo tips", expanded=True):
        st.write("• Lay the pack flat. • Photograph the face carrying declarations. • Avoid glare. • Keep the whole label in frame. • Use good lighting.")
    upload_tab, camera_tab = st.tabs(["🖼️ Upload photo", "📸 Take photo"])
    with upload_tab:
        uploaded = st.file_uploader("Choose a label image", type=["jpg","jpeg","png"], key="label_upload")
        st.caption("💡 crop the photo tightly around the label")
    with camera_tab:
        camera = st.camera_input("📸 Take a photo of the label", key="label_camera", help="crop the photo tightly around the label")
    image = camera or uploaded
    if image:
        st.image(image, caption="Selected label image", use_container_width=True)
        st.caption(f"File size: {len(image.getvalue())/1024/1024:.2f} MB")
    with st.form("scan_form"):
        c1, c2 = st.columns(2)
        with c1:
            product_name = st.text_input("Product name *", max_chars=120)
            brand = st.text_input("Brand *", max_chars=80)
            category_label = st.selectbox("Category *", list(CATEGORY_OPTIONS))
        with c2:
            width = st.number_input("Real label width (mm), optional", min_value=0.0, max_value=1000.0, value=0.0, step=1.0,
                                    help="0 means unknown: the numeral-height check will show 'needs review'.")
            barcode = st.text_input("Barcode (optional)", max_chars=14)
            notes = st.text_area("Notes (optional)", max_chars=500)
        st.info("Measure the real width in mm of the area covered by the whole photo, left to right. Crop the photo tightly around the label for best results. Leave it at 0 if unknown: the numeral-height check will then show 'needs review'.")
        submitted = st.form_submit_button("🔎 Analyse label", type="primary", use_container_width=True)
    if submitted:
        errors = []
        if not image: errors.append("Please upload or take a photo.")
        if image and len(image.getvalue()) > 10*1024*1024: errors.append("Image must be 10 MB or smaller.")
        if not product_name.strip(): errors.append("Product name is required.")
        if not brand.strip(): errors.append("Brand is required.")
        
        if barcode and (not barcode.isdigit() or not 8 <= len(barcode) <= 14): errors.append("Barcode must contain 8 to 14 digits.")
        if errors:
            for e in errors: st.error(e)
        else:
            payload = {"product_name":product_name.strip(),"brand":brand.strip(),"category":CATEGORY_OPTIONS[category_label],
                       "barcode":barcode,"notes":notes}
            if width > 0:
                payload["label_width_mm"] = str(width)            
            try:
                with st.spinner("Analysing label... This may take up to 30 seconds."):
                    data = create_scan(payload, image)
                st.session_state.last_scan = data
                st.session_state.selected_scan_id = data.get("id")
                st.session_state.pending_page = "Scan Result"
                st.success("Scan completed.")
                st.rerun()
            except ApiError as exc:
                error_box(exc)
                for field, msg in exc.fields.items(): st.error(f"{field}: {msg}")
