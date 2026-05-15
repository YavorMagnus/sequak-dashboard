import streamlit as st
import pandas as pd
from utils import supabase, SYSTEM_ROLES, AVAILABLE_PERMISSIONS

def render_admin_panel():
    st.title("⚙️ Управление на достъпи и потребители")
    st.markdown("Пълен контрол над профилите, сигурността и детайлните права в SequaK.")
    st.markdown("---")

    # ==========================================
    # --- СЪЗДАВАНЕ НА НОВ ПОТРЕБИТЕЛ ---
    # ==========================================
    with st.expander("➕ Създаване на нов потребител", expanded=False):
        with st.form("new_user_form", clear_on_submit=True):
            st.markdown("#### Въведете данни за новия профил")
            col1, col2, col3 = st.columns(3)
            with col1: new_username = st.text_input("Потребителско име *")
            with col2: new_password = st.text_input("Парола *", type="password")
            with col3: new_role = st.selectbox("Глобална роля *", SYSTEM_ROLES, index=SYSTEM_ROLES.index("Четец"))
            
            submit_new = st.form_submit_button("Създай профил", type="primary")
            if submit_new:
                if not new_username or not new_password:
                    st.error("⚠️ Моля, попълнете потребителско име и парола.")
                else:
                    # Проверка дали потребителят вече съществува
                    check_res = supabase.table("users").select("id").eq("username", new_username).execute()
                    if check_res.data:
                        st.error(f"⚠️ Потребител с име '{new_username}' вече съществува в системата!")
                    else:
                        try:
                            supabase.table("users").insert({
                                "username": new_username,
                                "password": new_password,
                                "role": new_role,
                                "permissions": {}
                            }).execute()
                            st.success(f"✅ Потребителят '{new_username}' е създаден успешно!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Грешка при създаване: {e}")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 👥 Съществуващи потребители")
    
    try:
        res = supabase.table("users").select("*").order("username").execute()
        users_data = res.data
    except Exception as e:
        st.error(f"Грешка при изтегляне на потребителите: {e}")
        return

    if not users_data:
        st.info("Няма намерени потребители.")
        return

    # ==========================================
    # --- РЕДАКЦИЯ НА ПОТРЕБИТЕЛИ ---
    # ==========================================
    for user in users_data:
        current_role = user.get('role', 'Четец')
        is_current_user = (user['username'] == st.session_state.username)
        badge = " <span style='color: #00aaff;'>(Твоят профил)</span>" if is_current_user else ""
        
        with st.expander(f"👤 {user['username']} - {current_role}"):
            if is_current_user:
                st.markdown(badge, unsafe_allow_html=True)
                
            tab_perms, tab_sec = st.tabs(["🛡️ Права и Роля", "🔑 Сигурност и Изтриване"])
            
            # --- ТАБ 1: Права ---
            with tab_perms:
                with st.form(f"form_user_{user['id']}"):
                    role_idx = SYSTEM_ROLES.index(current_role) if current_role in SYSTEM_ROLES else len(SYSTEM_ROLES)-1
                    
                    # ЗАЩИТА ОТ САМОУБИЙСТВО: Ако е твоят профил, падащото меню е замразено (disabled)
                    new_role = st.selectbox("Глобална системна роля:", SYSTEM_ROLES, index=role_idx, disabled=is_current_user)
                    
                    current_perms = user.get('permissions') or {}
                    new_perms = {}
                    
                    # СКРИВАНЕ НА ИЗЛИШНИТЕ ЧЕКБОКСОВЕ ЗА ВИСШИ РОЛИ
                    if new_role in ["Супер-админ", "Администратор"]:
                        st.info(f"ℹ️ Потребителят с роля **{new_role}** има глобални права. Детайлна настройка на модулите по-долу не е необходима.")
                        # Запазваме старите права непокътнати, в случай че някога бъде деградиран
                        new_perms = current_perms
                    else:
                        st.markdown(f"<h4 style='color: #aaaaaa; margin-top: 15px;'>Детайлни права (Прилагат се за Power User, Четец и AI)</h4>", unsafe_allow_html=True)
                        
                        for mod_key, mod_info in AVAILABLE_PERMISSIONS.items():
                            st.markdown(f"**{mod_info['name']}**")
                            mod_new_actions = {}
                            
                            cols = st.columns(3)
                            col_idx = 0
                            for action_key, action_desc in mod_info['actions'].items():
                                is_checked = current_perms.get(mod_key, {}).get(action_key, False)
                                
                                with cols[col_idx % 3]:
                                    val = st.checkbox(action_desc, value=is_checked, key=f"chk_{user['id']}_{mod_key}_{action_key}")
                                    mod_new_actions[action_key] = val
                                col_idx += 1
                            
                            new_perms[mod_key] = mod_new_actions
                            st.markdown("<br>", unsafe_allow_html=True)
                            
                    submit_btn = st.form_submit_button("💾 Запази правата и ролята", type="primary")
                    
                    if submit_btn:
                        try:
                            supabase.table("users").update({
                                "role": new_role,
                                "permissions": new_perms
                            }).eq("id", user['id']).execute()
                            
                            st.success(f"✅ Правата на {user['username']} са обновени успешно!")
                            
                            # Опресняваме сесията, ако потребителят редактира себе си (напр. свои чекбоксове, ако е Power User)
                            if is_current_user:
                                st.session_state.user_role = new_role
                                st.session_state.user_permissions = new_perms
                                
                            st.rerun()
                        except Exception as e:
                            st.error(f"Грешка при запис: {e}")

            # --- ТАБ 2: Сигурност ---
            with tab_sec:
                st.markdown("#### Смяна на парола")
                new_pass = st.text_input("Въведете нова парола за този потребител:", type="password", key=f"pass_{user['id']}")
                if st.button("🔑 Обнови паролата", key=f"btn_pass_{user['id']}"):
                    if new_pass.strip():
                        try:
                            supabase.table("users").update({"password": new_pass}).eq("id", user['id']).execute()
                            st.success("✅ Паролата е сменена успешно!")
                        except Exception as e:
                            st.error(f"Грешка при смяна на парола: {e}")
                    else:
                        st.error("⚠️ Моля, въведете валидна нова парола.")
                
                st.markdown("---")
                st.markdown("#### Опасна зона")
                if is_current_user:
                    st.warning("🛡️ Защита: Не можете да изтриете собствения си профил.")
                else:
                    st.error("Внимание: Това действие е необратимо и потребителят ще загуби достъп до системата веднага.")
                    if st.button("❌ ИЗТРИЙ ПОТРЕБИТЕЛЯ", type="secondary", key=f"btn_del_{user['id']}"):
                        try:
                            supabase.table("users").delete().eq("id", user['id']).execute()
                            st.success(f"✅ Потребителят {user['username']} беше изтрит!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Грешка при изтриване: {e}")
