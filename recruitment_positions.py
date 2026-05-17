import streamlit as st
from utils import supabase, check_permission

# -----------------------------------------------------------------------------
# 1. МОДАЛ ЗА РЕДАКЦИЯ НА ОБЯВА И ИЗТРИВАНЕ
# -----------------------------------------------------------------------------
@st.dialog("Редакция на обява", width="large")
def edit_position_modal(pos_data):
    if not check_permission("recruitment", "manage_positions"):
        st.error("Нямате права за редакция на обяви.")
        return

    # АКО ОБЯВАТА Е В КОШЧЕТО
    if pos_data.get('is_deleted', False):
        st.warning("⚠️ Тази обява се намира в Кошчето. За да работите с нея, първо я възстановете.")
        st.markdown(f"### 🗑️ {pos_data.get('title', 'Неизвестна обява')}")
        st.divider()
        
        col_restore, col_hard_delete = st.columns(2)
        with col_restore:
            if st.button("♻️ Възстанови обявата", type="primary", use_container_width=True):
                supabase.table("hr_positions").update({"is_deleted": False}).eq("id", pos_data['id']).execute()
                st.success("Обявата е възстановена!")
                st.rerun()
                
        with col_hard_delete:
            if check_permission("recruitment", "hard_delete"):
                if st.button("☢️ Окончателно изтриване", use_container_width=True):
                    try:
                        # 1. Намираме всички кандидатури (applications) за тази обява
                        apps_res = supabase.table("hr_applications").select("id, candidate_id").eq("position_id", pos_data['id']).execute()
                        application_ids = [app['id'] for app in apps_res.data] if apps_res.data else []
                        candidate_ids = [app['candidate_id'] for app in apps_res.data] if apps_res.data else []

                        # 2. Изтриваме коментарите от hr_comments, свързани с тези кандидатури
                        if application_ids:
                            supabase.table("hr_comments").delete().in_("application_id", application_ids).execute()

                        # 3. Изтриваме самите записи в hr_applications
                        supabase.table("hr_applications").delete().eq("position_id", pos_data['id']).execute()

                        # 4. Изтриваме физическите лица в hr_candidates
                        for cand_id in candidate_ids:
                            supabase.table("hr_candidates").delete().eq("id", cand_id).execute()

                        # 5. Изтриваме самата обява
                        supabase.table("hr_positions").delete().eq("id", pos_data['id']).execute()

                        st.session_state.active_campaign_id = None
                        st.success("Всички данни за обявата са заличени.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Грешка при изтриване: {e}")
        return

    # НОРМАЛНА РЕДАКЦИЯ
    st.markdown(f"### ⚙️ Редакция: {pos_data.get('title', 'Неизвестна обява')}")
    
    with st.form(key=f"form_edit_position_{pos_data.get('id')}"):
        col_left, col_right = st.columns(2)
        with col_left:
            edit_title = st.text_input("Заглавие на обявата", value=pos_data.get('title', ''))
            edit_city = st.text_input("Град", value=pos_data.get('city', ''))
            edit_base = st.text_input("База / Локация", value=pos_data.get('base_location', ''))
        with col_right:
            sal_col1, sal_col2 = st.columns(2)
            with sal_col1:
                edit_salary_min = st.text_input("Заплата от (EUR)", value=pos_data.get('salary_min', ''))
            with sal_col2:
                edit_salary_max = st.text_input("Заплата до (EUR)", value=pos_data.get('salary_max', ''))
            
            prio_options = ["Нормален", "Висок", "Спешен"]
            current_prio = pos_data.get('priority', 'Нормален')
            prio_index = prio_options.index(current_prio) if current_prio in prio_options else 0
            edit_priority = st.selectbox("Приоритет", prio_options, index=prio_index)
            
            status_opts = ["Активна", "Архивирана (Изтекла)"]
            current_status = pos_data.get('status', 'Активна')
            status_index = status_opts.index(current_status) if current_status in status_opts else 0
            edit_status = st.selectbox("Статус на обявата", status_opts, index=status_index)

        st.divider()
        if st.form_submit_button("💾 Запази промените", type="primary"):
            update_fields = {
                "title": edit_title, "city": edit_city, "base_location": edit_base,
                "salary_min": edit_salary_min, "salary_max": edit_salary_max,
                "priority": edit_priority, "status": edit_status
            }
            supabase.table("hr_positions").update(update_fields).eq("id", pos_data['id']).execute()
            st.success("Промените са записани!")
            st.rerun()

    # ОПАСНА ЗОНА
    st.markdown("---")
    st.markdown("#### 🗑️ Опасна зона")
    col_soft, col_hard = st.columns(2)
    with col_soft:
        if check_permission("recruitment", "soft_delete"):
            if st.button("🗑️ Премести в кошчето (Soft Delete)", key="btn_soft_delete_pos", use_container_width=True):
                supabase.table("hr_positions").update({"is_deleted": True}).eq("id", pos_data['id']).execute()
                st.session_state.active_campaign_id = None
                st.rerun()
    with col_hard:
        if check_permission("recruitment", "hard_delete"):
            if st.button("☢️ Окончателно изтриване (Hard Delete)", key="btn_hard_delete_pos", type="primary", use_container_width=True):
                try:
                    apps_res = supabase.table("hr_applications").select("id, candidate_id").eq("position_id", pos_data['id']).execute()
                    app_ids = [a['id'] for a in apps_res.data] if apps_res.data else []
                    cand_ids = [a['candidate_id'] for a in apps_res.data] if apps_res.data else []
                    if app_ids:
                        supabase.table("hr_comments").delete().in_("application_id", app_ids).execute()
                    supabase.table("hr_applications").delete().eq("position_id", pos_data['id']).execute()
                    for c_id in cand_ids:
                        supabase.table("hr_candidates").delete().eq("id", c_id).execute()
                    supabase.table("hr_positions").delete().eq("id", pos_data['id']).execute()
                    st.session_state.active_campaign_id = None
                    st.rerun()
                except Exception as e:
                    st.error(f"Грешка: {e}")

# -----------------------------------------------------------------------------
# 2. СЪЗДАВАНЕ НА НОВА ОБЯВА
# -----------------------------------------------------------------------------
@st.dialog("Създаване на нова обява", width="large")
def create_position_modal(preselected_company):
    if not check_permission("recruitment", "manage_positions"):
        st.error("Нямате права за създаване на обяви.")
        return

    users_data = supabase.table("users").select("username").execute().data
    all_users = [u['username'] for u in users_data] if users_data else []

    with st.form(key="form_create_pos"):
        companies = ["REN", "CIM", "MAS", "BAU", "AST", "RXS", "RXB", "SNW", "DXM", "ICM"]
        c_idx = companies.index(preselected_company) if preselected_company in companies else 0

        c1, c2 = st.columns([1, 3])
        with c1: sel_comp = st.selectbox("Фирма *", companies, index=c_idx)
        with c2: title = st.text_input("Име на позицията *")

        st.markdown("👥 **Мениджъри и HR**")
        r1, r2 = st.columns(2)
        with r1: owners = st.multiselect("Собственици (Мениджъри)", options=all_users)
        with r2: hr = st.selectbox("HR Контакт", options=[""] + all_users)

        eval_method = st.selectbox("Метод за оценка", [
            "Числова оценка 1-6 - обективна и субективна",
            "AI оценка + човешка субективна оценка"
        ])

        col_sal1, col_sal2 = st.columns(2)
        with col_sal1:
            new_salary_min = st.text_input("Мин. възнаграждение (EUR)")
        with col_sal2:
            new_salary_max = st.text_input("Макс. възнаграждение (EUR)")

        col_loc1, col_loc2 = st.columns(2)
        with col_loc1:
            new_city = st.text_input("Град", value="София")
        with col_loc2:
            new_base = st.text_input("База (незадължително)")

        work_type = st.selectbox("Тип работа", ["Присъствено", "Хибридно", "Дистанционно"])
        priority = st.selectbox("Приоритет", ["Нормален", "Висок", "Спешен"])

        st.divider()
        if st.form_submit_button("➕ Създай обява", type="primary"):
            if title and owners:
                data = {
                    "company_name": sel_comp, "title": title, "status": "Активна",
                    "owners": owners, "hr_contact": hr, "evaluation_method": eval_method,
                    "salary_min": new_salary_min, "salary_max": new_salary_max,
                    "city": new_city, "base_location": new_base,
                    "work_type": work_type, "priority": priority,
                    "is_deleted": False
                }
                res = supabase.table("hr_positions").insert(data).execute()
                if res.data:
                    st.success("Обявата е създадена!")
                    st.session_state.active_campaign_id = res.data[0]['id']
                    st.session_state.active_company = sel_comp
                    st.rerun()
                else:
                    st.error("Грешка при запис в базата данни.")
            else:
                st.error("Попълнете задължителните полета!")
