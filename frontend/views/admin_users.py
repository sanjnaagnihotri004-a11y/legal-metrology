import streamlit as st
from utils.api_client import list_users, create_user, update_user, ApiError
from utils.ui import error_box, ist_time

def render():
    if st.session_state.user.get("role") != "admin":
        st.error("You do not have access."); return
    st.title("User management")
    try:
        users=list_users()
        for user in users:
            with st.container(border=True):
                a,b,c,d=st.columns([2,2,1,1])
                a.markdown(f"**{user.get('name')}**")
                a.caption(user.get("email"))
                b.write(f"Role: {user.get('role')} • {'Active' if user.get('is_active') else 'Inactive'}")
                if user.get("id") != st.session_state.user.get("id"):
                    with c:
                        new_role=st.selectbox("Role",["inspector","admin"],index=0 if user.get("role")=="inspector" else 1,key=f"role_{user['id']}")
                        if st.button("Update role",key=f"rolebtn_{user['id']}"):
                            update_user(user["id"],{"role":new_role}); st.rerun()
                    with d:
                        if st.button("Deactivate" if user.get("is_active") else "Activate",key=f"active_{user['id']}"):
                            update_user(user["id"],{"is_active":not user.get("is_active",True)}); st.rerun()
                else:
                    c.caption("Your account")
        st.divider()
        st.subheader("Add user")
        with st.form("add_user"):
            name=st.text_input("Full name")
            email=st.text_input("Email")
            password=st.text_input("Password",type="password")
            role=st.selectbox("Role",["inspector","admin"])
            submit=st.form_submit_button("Create user",type="primary")
        if submit:
            if not name or not email or len(password)<8: st.error("Enter all details. Password must be at least 8 characters.")
            else:
                try:
                    create_user({"name":name,"email":email,"password":password,"role":role})
                    st.success("User created."); st.rerun()
                except ApiError as exc:
                    error_box(exc)
                    for field,msg in exc.fields.items(): st.error(f"{field}: {msg}")
    except ApiError as exc: error_box(exc)
