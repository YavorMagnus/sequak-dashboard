import streamlit as st
import pandas as pd
from datetime import datetime
from utils import supabase, check_permission

# -----------------------------------------------------------------------------
# 1. МОДАЛ ЗА РЕДАКЦИЯ НА ОБЯВА И ИЗТРИВАНЕ
# -----------------------------------------------------------------------------
@st.dialog("Редакция на обява", width="large")
def edit_position_modal(pos_data):
    if not check_permission("recruitment", "manage_positions"):
        st.error("Нямате права за редакция на обяви.")
        return

    # АКО ОБЯВАТА Е В КОШЧЕТО - ПОКАЗВАМЕ САМО ВЪЗСТАНОВЯВАНЕ И ХАРД ДИЛИЙТ
    if pos_data.get('is_deleted', False):
        st.warning("⚠️ Тази обява се намира в Кошчето. За да работите с нея, първо я възстановете.")
        st.markdown(f"### 🗑️ {pos_data.get('title', 'Неизвестна обява')}")
        st.divider()
        
        col_res, col_hard = st.columns(2)
        with col_res:
            if st.button("♻️ Възстанови обявата", type="primary", use_container_width=True):
                supabase.table("hr_positions").update({"is_deleted": False}).eq("id", pos_data['id']).execute()
                st.success("Обявата е възстановена!")
                st.rerun()
                
        with col_hard:
            if check_permission("recruitment", "hard_delete"):
                if st.button("☢️ Окончателно изтриване", use_container_width=True):
                    try:
                        # 1. Взимаме ID-тата на всички кандидати за тази обява
                        apps_res = supabase.table("hr_applications").select("candidate_id").eq("position_id", pos_data['id']).execute()
                        cand_ids = [app['candidate_id'] for app in apps_res.data] if apps_res.data else []

                        # 2. Трием връзките
                        supabase.table("hr_applications").delete().eq("position_id", pos_data['id']).execute()

                        # 3. Трием самите кандидати
                        if cand_ids:
                            supabase.table("hr_candidates").delete().in_("id", cand_ids).execute()

                        # 4. Трием обявата
                        supabase.table("hr_positions").delete().eq("id", pos_data['id']).execute()

                        st.session_state.active_campaign_id = None
                        st.success("Обявата и всички нейни кандидати са изтрити физически от базата данни.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Грешка при изтриване: {e}")
        return # Спираме изпълнението тук

    # НОРМАЛНА РЕДАКЦИЯ
    st.markdown(f"### ⚙️ Редакция: {pos_data.get('title', 'Неизвестна обява')}")
    
    with st.form(key=f"form_edit_pos_{pos_data.get('id', 'new')}"):
        col1, col2 = st.columns(2)
        with col1:
            new_title = st.text_input("Заглавие на обявата", value=pos_data.get('title', ''))
            new_city = st.text_input("Град", value=pos_data.get('city', ''))
            new_base = st.text_input("База / Локация", value=pos_data.get('base_location', ''))
        with col2:
            sal_col1, sal_col2 = st.columns(2)
            with sal_col1:
                new_salary_min = st.text_input("Заплата от (EUR)", value=pos_data.get('salary_min', ''))
            with sal_col2:
                new_salary_max = st.text_input("Заплата до (EUR)", value=pos_data.get('salary_max', ''))
            
            priority_options = ["Нормален", "Висок", "Спешен"]
            curr_prio = pos_data.get('priority', 'Нормален')
            prio_idx = priority_options.index(curr_prio) if curr_prio in priority_options else 0
            new_priority = st.selectbox("Приоритет", priority_options, index=prio_idx)
            
            status_options = ["Активна", "Архивирана (Изтекла)"]
            curr_status = pos_data.get('status', 'Активна')
            status_idx = status_options.index(curr_status) if curr_status in status_options else 0
            new_status = st.selectbox("Статус на обявата", status_options, index=status_idx)

        st.divider()
        if st.form_submit_button("💾 Запази промените", type="primary"):
            update_data = {
                "title": new_title, "city": new_city, "base_location": new_base,
                "salary_min": new_salary_min, "salary_max": new_salary_max,
                "priority": new_priority, "status": new_status
            }
            res = supabase.table("hr_positions").update(update_data).eq("id", pos_data['id']).execute()
            if res.data:
                st.success("Промените са записани!")
                st.rerun()

    # === ОПАСНА ЗОНА ЗА ОБЯВАТА ===
    st.markdown("---")
    st.markdown("#### 🗑️ Опасна зона")
    
    col_del1, col_del2 = st.columns(2)
    with col_del1:
        if check_permission("recruitment", "soft_delete"):
            if st.button("🗑️ Премести в кошчето (Soft Delete)", key="btn_soft_del_pos", use_container_width=True):
                supabase.table("hr_positions").update({"is_deleted": True}).eq("id", pos_data['id']).execute()
                st.session_state.active_campaign_id = None
                st.success("Обявата е преместена в кошчето.")
                st.rerun()
                
    with col_del2:
        if check_permission("recruitment", "hard_delete"):
            if st.button("☢️ Окончателно изтриване (Hard Delete)", key="btn_hard_del_pos", type="primary", use_container_width=True):
                try:
                    # 1. Взимаме ID-тата на всички кандидати за тази обява
                    apps_res = supabase.table("hr_applications").select("candidate_id").eq("position_id", pos_data['id']).execute()
                    cand_ids = [app['candidate_id'] for app in apps_res.data] if apps_res.data else []

                    # 2. Трием връзките
                    supabase.table("hr_applications").delete().eq("position_id", pos_data['id']).execute()

                    # 3. Трием самите кандидати
                    if cand_ids:
                        supabase.table("hr_candidates").delete().in_("id", cand_ids).execute()

                    # 4. Трием обявата
                    supabase.table("hr_positions").delete().eq("id", pos_data['id']).execute()

                    st.session_state.active_campaign_id = None
                    st.success("Обявата и всички нейни кандидати са изтрити физически от базата данни.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Грешка при изтриване: {e}")

# -----------------------------------------------------------------------------
# 2. ИНТЕЛИГЕНТЕН КАРТОН НА КАНДИДАТА
# -----------------------------------------------------------------------------
@st.dialog("Картон на кандидата", width="large")
def candidate_card_modal(candidate, app_data, pos_data=None):
    cv_data = candidate.get('raw_cv_data') or {}
    int_details = app_data.get('interview_details') or {}
    manual_scores = app_data.get('manual_score') or {}
    
    # --- ХЕДЪР ---
    col_photo, col_info, col_status = st.columns([1, 2, 1.5])
    
    with col_photo:
        if candidate.get('photo_thumbnail'):
            st.image(f"data:image/png;base64,{candidate['photo_thumbnail']}", use_container_width=True)
        else:
            st.write("<div style='font-size: 60px; text-align: center; color: gray;'>👤</div>", unsafe_allow_html=True)
            
    with col_info:
        st.subheader(candidate.get('full_name', 'Неизвестен'))
        st.write(f"📧 {cv_data.get('email', 'Няма')}")
        st.write(f"📱 {cv_data.get('phone', 'Няма')}")
        
    with col_status:
        st.info(f"**Статус:** {app_data.get('status', 'Нов')}")
        next_int = int_details.get('interview_date')
        if next_int:
            st.warning(f"📅 Интервю: {next_int} в {int_details.get('interview_time', '')}")
        
        total_score = sum(manual_scores.values()) if manual_scores else 0
        st.metric("Обща оценка", f"{total_score}/48", f"{int(total_score/48*100)}%")

    # --- ТАБОВЕ ---
    tab_quest, tab_cv, tab_eval, tab_int, tab_status = st.tabs([
        "📝 Въпросник", "📄 CV", "📊 Оценка и Бележки", "📅 Интервюта", "⚙️ Статус"
    ])

    with tab_quest:
        st.markdown(cv_data.get('questionnaire', 'Няма въпросник.'))

    with tab_cv:
        st.markdown(cv_data.get('cv_text', 'Няма текст на CV.'))

    with tab_eval:
        st.markdown("### 📊 Оценка по компетенции (1-6)")
        competencies = [
            "Търговска", "Сервизна", "Строителна/архитектурна", "Юридическа", 
            "IT", "Складова", "Счетоводно-административна", "Управленска"
        ]
        
        with st.form(key=f"eval_form_{app_data['id']}"):
            new_scores = {}
            cols = st.columns(2)
            for i, comp in enumerate(competencies):
                with cols[i % 2]:
                    val = manual_scores.get(comp, 1)
                    new_scores[comp] = st.slider(comp, 1, 6, val)
            
            st.divider()
            new_notes = st.text_area("Допълнителни бележки / Субективна оценка", value=int_details.get('notes', ''), height=150)
            
            if st.form_submit_button("💾 Запази оценките и бележките", type="primary"):
                int_details['notes'] = new_notes
                supabase.table("hr_applications").update({
                    "manual_score": new_scores,
                    "interview_details": int_details
                }).eq("id", app_data['id']).execute()
                st.success("Данните са записани!")
                st.rerun()

    with tab_int:
        st.markdown("### 📅 Планиране на интервю")
        with st.form(key=f"int_form_{app_data['id']}"):
            d = st.date_input("Дата", value=datetime.now())
            t = st.time_input("Час")
            interviewer = st.text_input("Интервюиращ", value=int_details.get('interviewer_name', ''))
            
            if st.form_submit_button("📅 Насрочи интервю"):
                int_details.update({
                    'interview_date': d.strftime("%Y-%m-%d"),
                    'interview_time': t.strftime("%H:%M"),
                    'interviewer_name': interviewer
                })
                supabase.table("hr_applications").update({"interview_details": int_details, "status": "Потвърдено интервю"}).eq("id", app_data['id']).execute()
                st.success("Интервюто е насрочено!")
                st.rerun()

    with tab_status:
        st.markdown("### ⚙️ Смяна на статус")
        statuses = ["Нов", "Установи контакт", "Възможно интервю", "Избран за интервю", "Потвърдено интервю", "Направено предложение", "Отхвърлен", "Отказал", "Преместен"]
        curr_idx = statuses.index(app_data.get('status', 'Нов')) if app_data.get('status') in statuses else 0
        new_status = st.selectbox("Изберете нов статус", statuses, index=curr_idx)
        
        rejection_reason_index = 0
        reasons_list = []
        is_reserve_value = False
        
        if new_status == "Отхвърлен":
            try:
                settings_data = supabase.table("hr_settings").select("setting_value").eq("setting_key", "reject_reasons").execute()
                if settings_data.data:
                    reasons_list = settings_data.data[0].get("setting_value", [])
            except Exception as e:
                st.error(f"Грешка при зареждане на причини: {e}")
            
            if not reasons_list:
                reasons_list = ["Друго"]
            
            current_reason = int_details.get('rejection_reason')
            if current_reason and current_reason in reasons_list:
                rejection_reason_index = reasons_list.index(current_reason)
                
            st.selectbox("Причина за отхвърляне", reasons_list, index=rejection_reason_index, key=f"sel_reason_{app_data['id']}")
            
            is_reserve_value = int_details.get('reserve_checkbox', False)
            st.checkbox("Запази като резерва ❓", value=is_reserve_value, key=f"check_reserve_{app_data['id']}")
            
        if st.button("🔄 Промени статуса", use_container_width=True, type="primary"):
            if new_status == "Отхвърлен":
                if f"sel_reason_{app_data['id']}" in st.session_state:
                    int_details['rejection_reason'] = st.session_state[f"sel_reason_{app_data['id']}"]
                if f"check_reserve_{app_data['id']}" in st.session_state:
                    int_details['reserve_checkbox'] = st.session_state[f"check_reserve_{app_data['id']}"]
            
            supabase.table("hr_applications").update({
                "status": new_status,
                "interview_details": int_details
            }).eq("id", app_data['id']).execute()
            
            st.success(f"Статусът е променен на {new_status}")
            st.rerun()

    # === ОПАСНА ЗОНА ЗА КАНДИДАТА ===
    st.markdown("---")
    with st.expander("🗑️ Управление на записа (Изтриване)", expanded=False):
        col_cdel1, col_cdel2 = st.columns(2)
        with col_cdel1:
            if check_permission("recruitment", "soft_delete"):
                if st.button("🗑️ Премести в кошчето", key=f"soft_del_cand_{app_data['id']}", use_container_width=True):
                    supabase.table("hr_applications").update({"is_deleted": True}).eq("id", app_data['id']).execute()
                    st.success("Кандидатът е скрит (Soft Delete).")
                    st.rerun()
        with col_cdel2:
            if check_permission("recruitment", "hard_delete"):
                if st.button("☢️ Окончателно изтриване", type="primary", key=f"hard_del_cand_{app_data['id']}", use_container_width=True):
                    try:
                        # 1. Изтриваме връзката
                        supabase.table("hr_applications").delete().eq("id", app_data['id']).execute()
                        # 2. Изтриваме физически самия човек
                        supabase.table("hr_candidates").delete().eq("id", app_data['candidate_id']).execute()
                        
                        st.success("Кандидатурата е изтрита физически.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Грешка при изтриване: {e}")

    # --- ИНФО ЛЕНТА ---
    if pos_data:
        st.divider()
        st.info(f"📍 **Обява:** {pos_data.get('title', '')} | **Град:** {pos_data.get('city', '')} | **Заплата:** {pos_data.get('salary_min', '')}-{pos_data.get('salary_max', '')} EUR")

# -----------------------------------------------------------------------------
# 3. СЪЗДАВАНЕ НА НОВА ОБЯВА
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
