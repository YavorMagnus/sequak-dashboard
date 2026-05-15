import streamlit as st
import pandas as pd
from datetime import datetime
from utils import supabase, check_permission

# Помощна функция за генериране на часове през 15 минути за падащите менюта
def generate_time_options():
    time_list = []
    for hour in range(8, 19):  # От 08:00 до 18:00
        for minute in [0, 15, 30, 45]:
            time_list.append(f"{hour:02d}:{minute:02d}")
    return time_list

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
# 2. ИНТЕЛИГЕНТЕН КАРТОН НА КАНДИДАТА
# -----------------------------------------------------------------------------
@st.dialog("Картон на кандидата", width="large")
def candidate_card_modal(candidate, app_data, pos_data=None):
    # Данни
    cv_info = candidate.get('raw_cv_data') or {}
    interview_info = app_data.get('interview_details') or {}
    scores = app_data.get('manual_score') or {}
    
    # Обективни категории
    categories = ["Търговска", "Сервизна", "Строителна/архитектурна", "Юридическа", "IT", "Складова", "Счетоводно-административна", "Управленска"]
    
    # Изчисляване на точките
    obj_total = sum(scores.get(cat, 0) for cat in categories)
    subj_total = scores.get("Субективна", 0)
    
    # --- ХЕДЪР ---
    col_photo, col_info, col_status = st.columns([1, 2, 1.5])
    with col_photo:
        if candidate.get('photo_thumbnail'):
            st.image(f"data:image/png;base64,{candidate['photo_thumbnail']}", use_container_width=True)
        else:
            st.write("<div style='font-size: 60px; text-align: center; color: gray;'>👤</div>", unsafe_allow_html=True)
            
    with col_info:
        st.subheader(candidate.get('full_name', 'Неизвестен'))
        if pos_data:
            st.markdown(f"<span style='color: #00aaff; font-weight: bold;'>Обява:</span> {pos_data.get('title', '')} ({pos_data.get('city', '')})", unsafe_allow_html=True)
        st.write(f"📧 {cv_info.get('email', 'Няма имейл')}")
        st.write(f"📱 {cv_info.get('phone', 'Няма телефон')}")
        
    with col_status:
        st.info(f"**Статус:** {app_data.get('status', 'Нов')}")
        st.markdown(f"**Обективна оценка:** {obj_total}/48<br>**Субективна оценка:** {subj_total}/6", unsafe_allow_html=True)

    st.divider()

    # Извличане на история на бележките от hr_comments (използвайки правилното име application_id)
    comments_query = supabase.table("hr_comments").select("*").eq("application_id", app_data['id']).order("created_at", desc=True).execute()
    all_comments = comments_query.data if comments_query.data else []

    # --- СТРУКТУРА: ОСНОВНА ЧАСТ И СТРАНИЧНА ЛЕНТА (3:1) ---
    col_main_content, col_side_notes = st.columns([3, 1])

    # СТРАНИЧНА ЛЕНТА (Последна бележка)
    with col_side_notes:
        st.markdown("### 💬 Последна бележка")
        if all_comments:
            latest_note = all_comments[0]
            with st.container(border=True):
                st.markdown(f"**{latest_note.get('author_id', 'Система')}**")
                st.caption(pd.to_datetime(latest_note['created_at']).strftime("%d.%m.%Y %H:%M"))
                full_text = latest_note.get('comment_text', '')
                display_text = full_text if len(full_text) <= 500 else full_text[:500] + "..."
                st.write(display_text)
        else:
            st.caption("Няма добавени бележки за този кандидат.")

    # ОСНОВНА ЧАСТ (ТАБОВЕ)
    with col_main_content:
        tab_list = st.tabs(["📝 Въпросник", "📄 CV", "📊 Оценка", "💬 Бележки", "📅 Интервюта", "⚙️ Статус"])

        # ТАБ 1: ВЪПРОСНИК
        with tab_list[0]:
            if st.toggle("✏️ Редакция на текста", key=f"edit_toggle_q_{app_data['id']}"):
                updated_q = st.text_area("Въпросник (Редакция)", value=cv_info.get('questionnaire', ''), height=250)
                if st.button("💾 Запази Въпросника"):
                    cv_info['questionnaire'] = updated_q
                    supabase.table("hr_candidates").update({"raw_cv_data": cv_info}).eq("id", candidate['id']).execute()
                    st.success("Записано!")
                    st.rerun()
            else:
                st.markdown(cv_info.get('questionnaire', 'Няма въпросник.'))

        # ТАБ 2: CV
        with tab_list[1]:
            if st.toggle("✏️ Редакция на текста", key=f"edit_toggle_cv_{app_data['id']}"):
                updated_cv = st.text_area("CV Текст (Редакция)", value=cv_info.get('cv_text', ''), height=350)
                if st.button("💾 Запази CV"):
                    cv_info['cv_text'] = updated_cv
                    supabase.table("hr_candidates").update({"raw_cv_data": cv_info}).eq("id", candidate['id']).execute()
                    st.success("Записано!")
                    st.rerun()
            else:
                st.markdown(cv_info.get('cv_text', 'Няма зареден текст на CV.'))

        # ТАБ 3: ОЦЕНКА
        with tab_list[2]:
            st.markdown("### 📊 Оценка по компетенции")
            with st.form(key=f"form_evaluation_{app_data['id']}"):
                new_manual_scores = {}
                score_cols = st.columns(2)
                for index, category in enumerate(categories):
                    with score_cols[index % 2]:
                        current_val = scores.get(category, 1)
                        new_manual_scores[category] = st.slider(category, 1, 6, current_val)
                st.divider()
                st.markdown("### 🎭 Субективна оценка (Цялостно впечатление)")
                new_manual_scores["Субективна"] = st.slider("Обща субективна оценка", 1, 6, scores.get("Субективна", 1))
                
                if st.form_submit_button("💾 Запази всички оценки", type="primary"):
                    supabase.table("hr_applications").update({"manual_score": new_manual_scores}).eq("id", app_data['id']).execute()
                    st.success("Оценките са обновени!")
                    st.rerun()

        # ТАБ 4: БЕЛЕЖКИ (ИСТОРИЯ)
        with tab_list[3]:
            st.markdown("### 💬 Добави нова бележка")
            note_to_add = st.text_area("Въведете коментар тук:", height=100, key=f"input_note_{app_data['id']}")
            if st.button("➕ Добави бележка", type="primary"):
                if note_to_add.strip():
                    supabase.table("hr_comments").insert({
                        "application_id": app_data['id'],
                        "author_id": st.session_state.username,
                        "comment_text": note_to_add.strip(),
                        "comment_type": "Бележка"
                    }).execute()
                    st.rerun()
            st.divider()
            st.markdown("### 📜 История")
            for comment in all_comments:
                with st.container(border=True):
                    st.markdown(f"**{comment.get('author_id')}** | {pd.to_datetime(comment['created_at']).strftime('%d.%m.%Y %H:%M')}")
                    st.write(comment.get('comment_text'))

        # ТАБ 5: ИНТЕРВЮТА (ТРИТЕ АКОРДЕОНА)
        with tab_list[4]:
            time_slots = generate_time_options()
            
            # 1. ТЕЛЕФОННО ИНТЕРВЮ
            with st.expander("📞 1. Телефонно интервю (HR Скрининг)", expanded=False):
                col_date1, col_time1 = st.columns(2)
                with col_date1:
                    phone_date = st.date_input("Дата на обаждане", value=datetime.now(), key=f"phone_date_{app_data['id']}")
                with col_time1:
                    phone_time = st.selectbox("Час", time_slots, key=f"phone_time_{app_data['id']}")
                if st.button("📞 Насрочи обаждане", type="primary", use_container_width=True):
                    interview_info.update({'ph_date': phone_date.strftime("%Y-%m-%d"), 'ph_time': phone_time})
                    # [HOOK-NOTIFICATION]: Установи контакт / Възможно интервю
                    supabase.table("hr_applications").update({
                        "interview_details": interview_info, 
                        "status": "Възможно интервю"
                    }).eq("id", app_data['id']).execute()
                    st.rerun()

            # 2. ПОКАНА ОТ МЕНИДЖЪР
            with st.expander("💡 2. Покана от мениджър (Предложение за дати)", expanded=False):
                st.info("Мениджърът предлага варианти за среща:")
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    m_date1 = st.date_input("Вариант 1: Дата", key=f"mgr_d1_{app_data['id']}")
                    m_range1 = st.text_input("Вариант 1: Диапазон", value=interview_info.get('mgr_range1', ''), placeholder="напр. 10:00 - 12:00", key=f"mgr_r1_{app_data['id']}")
                with col_m2:
                    m_date2 = st.date_input("Вариант 2: Дата", key=f"mgr_d2_{app_data['id']}")
                    m_range2 = st.text_input("Вариант 2: Диапазон", value=interview_info.get('mgr_range2', ''), placeholder="напр. след 15:30", key=f"mgr_r2_{app_data['id']}")
                if st.button("💡 Предложи интервю", type="primary", use_container_width=True):
                    interview_info.update({
                        'mgr_date1': m_date1.strftime("%Y-%m-%d"), 'mgr_range1': m_range1,
                        'mgr_date2': m_date2.strftime("%Y-%m-%d"), 'mgr_range2': m_range2
                    })
                    # [HOOK-NOTIFICATION]: Избран за интервю
                    supabase.table("hr_applications").update({
                        "interview_details": interview_info, 
                        "status": "Избран за интервю"
                    }).eq("id", app_data['id']).execute()
                    st.rerun()

            # 3. НАСРОЧВАНЕ НА ОФИЦИАЛНО ИНТЕРВЮ
            with st.expander("🏢 3. Насрочване на интервю с мениджър", expanded=False):
                # Списък потребители за интервюиращ
                users_resp = supabase.table("users").select("username").execute()
                user_list = [u['username'] for u in users_resp.data] if users_resp.data else []
                selected_interviewer = st.selectbox("Интервюиращ", user_list, key=f"sel_interv_{app_data['id']}")
                
                col_f_date, col_f_time = st.columns(2)
                with col_f_date:
                    final_date = st.date_input("Финална Дата", key=f"final_date_{app_data['id']}")
                with col_f_time:
                    final_time = st.selectbox("Финален Час", time_slots, key=f"final_time_{app_data['id']}")
                
                if st.button("🏢 Потвърди интервю", type="primary", use_container_width=True):
                    interview_info.update({
                        'interviewer_name': selected_interviewer, 
                        'interview_date': final_date.strftime("%Y-%m-%d"), 
                        'interview_time': final_time
                    })
                    # [HOOK-NOTIFICATION]: Потвърдено интервю
                    supabase.table("hr_applications").update({
                        "interview_details": interview_info, 
                        "status": "Потвърдено интервю"
                    }).eq("id", app_data['id']).execute()
                    st.rerun()

        # ТАБ 6: СТАТУС (РЪЧНА СМЯНА И ПРЕМЕСТВАНЕ)
        with tab_list[5]:
            st.markdown("### ⚙️ Смяна на статус")
            all_statuses = ["Нов", "Установи контакт", "Възможно интервю", "Избран за интервю", "Потвърдено интервю", "Направено предложение", "Отхвърлен", "Отказал", "Преместен"]
            current_status_name = app_data.get('status', 'Нов')
            new_status_selection = st.selectbox("Изберете нов статус", all_statuses, index=all_statuses.index(current_status_name) if current_status_name in all_statuses else 0)
            
            # Логика за "Отхвърлен"
            if new_status_selection == "Отхвърлен":
                reject_data = supabase.table("hr_settings").select("setting_value").eq("setting_key", "reject_reasons").execute()
                reject_reasons = reject_data.data[0].get("setting_value", ["Друго"]) if reject_data.data else ["Друго"]
                st.selectbox("Причина за отхвърляне", reject_reasons, key=f"reject_reason_sel_{app_data['id']}")
                st.checkbox("Запази в резерва?", value=interview_info.get('reserve', False), key=f"is_reserve_check_{app_data['id']}")

            # Логика за "Преместен" (С ПРЕДУПРЕЖДЕНИЕ)
            if new_status_selection == "Преместен":
                pos_resp = supabase.table("hr_positions").select("id, title, company_name").eq("status", "Активна").eq("is_deleted", False).execute()
                target_positions = {p['id']: f"{p['title']} ({p['company_name']})" for p in pos_resp.data if p['id'] != pos_data['id']}
                
                if target_positions:
                    target_id = st.selectbox("Премести в обява:", options=list(target_positions.keys()), format_func=lambda x: target_positions[x])
                    keep_current = st.checkbox("Запази копие и в текущата обява?", value=False)
                    
                    if not keep_current:
                        st.warning("🚨 ВНИМАНИЕ: Кандидатът ще бъде премахнат от ТЕКУЩАТА обява. Сигурни ли сте?")
                        confirm_btn_label = "⚠️ Потвърди окончателно преместване"
                    else:
                        confirm_btn_label = "🔄 Премести (с копие)"
                        
                    if st.button(confirm_btn_label, type="primary"):
                        if keep_current:
                            supabase.table("hr_applications").insert({
                                "candidate_id": candidate['id'], 
                                "position_id": target_id, 
                                "status": "Нов"
                            }).execute()
                        else:
                            supabase.table("hr_applications").update({
                                "position_id": target_id, 
                                "status": "Нов"
                            }).eq("id", app_data['id']).execute()
                        st.rerun()

            # Бутон за запазване на стандартни статуси
            if new_status_selection != "Преместен":
                if st.button("🔄 Запази новия статус", type="primary", use_container_width=True):
                    # [HOOK-NOTIFICATION]: Смяна на статус (Нов, Установи контакт и т.н.)
                    supabase.table("hr_applications").update({"status": new_status_selection}).eq("id", app_data['id']).execute()
                    st.rerun()

    # --- ОПАСНА ЗОНА (ИЗТРИВАНЕ НА КАНДИДАТ) ---
    st.markdown("---")
    with st.expander("🗑️ Управление на записа (Изтриване)", expanded=False):
        c_del1, c_del2 = st.columns(2)
        with c_del1:
            if st.button("🗑️ Премести в кошчето", key=f"soft_del_cand_{app_data['id']}", use_container_width=True):
                supabase.table("hr_applications").update({"is_deleted": True}).eq("id", app_data['id']).execute()
                st.rerun()
        with c_del2:
            if st.button("☢️ Окончателно изтриване", type="primary", key=f"hard_del_cand_{app_data['id']}", use_container_width=True):
                # Първо чистим коментарите по application_id
                supabase.table("hr_comments").delete().eq("application_id", app_data['id']).execute()
                # После трием кандидатурата и кандидата
                supabase.table("hr_applications").delete().eq("id", app_data['id']).execute()
                supabase.table("hr_candidates").delete().eq("id", candidate['id']).execute()
                st.rerun()

# -----------------------------------------------------------------------------
# 3. СЪЗДАВАНЕ НА НОВА ОБЯВА
# -----------------------------------------------------------------------------
@st.dialog("Създаване на нова обява", width="large")
def create_position_modal(preselected_company):
    if not check_permission("recruitment", "manage_positions"):
        st.error("Нямате права.")
        return
    
    users_resp = supabase.table("users").select("username").execute()
    usernames = [u['username'] for u in users_resp.data] if users_resp.data else []
    
    with st.form(key="form_create_new_pos"):
        comp_list = ["REN", "CIM", "MAS", "BAU", "AST", "RXS", "RXB", "SNW", "DXM", "ICM"]
        sel_comp = st.selectbox("Фирма", comp_list, index=comp_list.index(preselected_company) if preselected_company in comp_list else 0)
        pos_title = st.text_input("Заглавие на позицията")
        
        st.markdown("Мениджъри и HR")
        owners_list = st.multiselect("Собственици на обявата", usernames)
        hr_contact_name = st.selectbox("HR Контакт", usernames)
        
        if st.form_submit_button("➕ Създай обява", type="primary"):
            if pos_title and owners_list:
                new_pos_data = {
                    "company_name": sel_comp, 
                    "title": pos_title, 
                    "owners": owners_list, 
                    "hr_contact": hr_contact_name, 
                    "status": "Активна",
                    "is_deleted": False
                }
                insert_res = supabase.table("hr_positions").insert(new_pos_data).execute()
                if insert_res.data:
                    st.session_state.active_campaign_id = insert_res.data[0]['id']
                    st.rerun()
            else:
                st.error("Попълнете заглавие и собственици!")
