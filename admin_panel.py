import streamlit as st
import pandas as pd
from utils import supabase, SYSTEM_ROLES, AVAILABLE_PERMISSIONS

def render_admin_panel():
    st.title("⚙️ Управление на достъпи и роли")
    st.markdown("Тук можете да задавате глобални роли и детайлни права за достъп на всеки потребител в SequaK.")
    st.markdown("---")

    try:
        res = supabase.table("users").select("*").order("username").execute()
        users_data = res.data
    except Exception as e:
        st.error(f"Грешка при изтегляне на потребителите: {e}")
        return

    if not users_data:
        st.info("Няма намерени потребители.")
        return

    for user in users_data:
        current_role = user.get('role', 'Четец')
        badge_color = "#FFD700" if current_role in ["Супер-админ", "Администратор"] else "#00aaff"
        
        with st.expander(f"👤 {user['username']} (Текуща роля: {current_role})"):
            with st.form(f"form_user_{user['id']}"):
                
                role_idx = SYSTEM_ROLES.index(current_role) if current_role in SYSTEM_ROLES else len(SYSTEM_ROLES)-1
                new_role = st.selectbox("Глобална системна роля:", SYSTEM_ROLES, index=role_idx)
                st.caption("⚠️ **Супер-админ** и **Администратор** имат пълен достъп (игнорират детайлите долу). **Супер-четец** има само и единствено права за 'Четене'.")
                
                st.markdown(f"<h4 style='color: #aaaaaa; margin-top: 15px;'>Детайлни права (Прилагат се за Power User и Четец)</h4>", unsafe_allow_html=True)
                
                current_perms = user.get('permissions') or {}
                new_perms = {}
                
                for mod_key, mod_info in AVAILABLE_PERMISSIONS.items():
                    st.markdown(f"**{mod_info['name']}**")
                    mod_new_actions = {}
                    
                    cols = st.columns(3)
                    col_idx = 0
                    for action_key, action_desc in mod_info['actions'].items():
                        # Вземаме състоянието от JSON-а в базата
                        is_checked = current_perms.get(mod_key, {}).get(action_key, False)
                        
                        with cols[col_idx % 3]:
                            val = st.checkbox(action_desc, value=is_checked, key=f"chk_{user['id']}_{mod_key}_{action_key}")
                            mod_new_actions[action_key] = val
                        col_idx += 1
                    
                    new_perms[mod_key] = mod_new_actions
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                submit_btn = st.form_submit_button("💾 Запази промените за този потребител", type="primary")
                
                if submit_btn:
                    try:
                        supabase.table("users").update({
                            "role": new_role,
                            "permissions": new_perms
                        }).eq("id", user['id']).execute()
                        st.success(f"✅ Правата на {user['username']} са обновени успешно! Презареждане...")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Грешка при запис: {e}")
