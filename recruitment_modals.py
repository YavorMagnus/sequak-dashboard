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
    col_photo, col_name, col_upcoming, col_status = st.columns([1, 1.5, 2, 1])
    
    with col_photo:
        if candidate.get('photo_thumbnail'):
            st.image(f"data:image/png;base64,{candidate['photo_thumbnail']}", use_container_width=True)
        else:
            st.write("<div style='font-size: 60px; text-align: center; color: gray;'>👤</div>", unsafe_allow_html=True)
            
    with col_name:
        st.subheader(candidate.get('full_name', 'Неизвестен'))
        
    with col_upcoming:
        st.markdown("**📅 Предстоящи стъпки:**")
        ph_d = interview_info.get('ph_date')
        if ph_d:
            st.markdown(f"📞 Телефонно: **{ph_d}** в **{interview_info.get('ph_time', '')}**")
            
        mgr_d1 = interview_info.get('mgr_date1')
        if mgr_d1:
            mgr_r1 = interview_info.get('mgr_range1', '')
            mgr_d2 = interview_info.get('mgr_date2', '')
            mgr_r2 = interview_info.get('mgr_range2', '')
            
            opt1_text = f"{mgr_d1} ({mgr_r1})" if mgr_r1 else f"{mgr_d1}"
            opt2_text = f"{mgr_d2} ({mgr_r2})" if mgr_r2 else f"{mgr_d2}"
            
            st.markdown(f"💡 Предложени: **{opt1_text}** / **{opt2_text}**")
            
        off_d = interview_info.get('interview_date')
        if off_d:
            st.markdown(f"🏢 **Потвърдено:** {off_d} в {interview_info.get('interview_time', '')}")
            
        if not ph_d and not mgr_d1 and not off_d:
            st.caption("Няма насрочени стъпки.")
        
    with col_status:
        st.info(f"**Статус:** {app_data.get('status', 'Нов')}")
        st.markdown(f"**Обективна:** {obj_total}/48<br>**Субективна:** {subj_total}/6", unsafe_allow_html=True)

    st.divider()

    # --- ЗАРЕЖДАНЕ НА БЕЛЕЖКИТЕ ---
    comments_query = supabase.table("hr_comments").select("*").eq("application_id", app_data['id']).order("created_at", desc=True).execute()
    all_comments = comments_query.data if comments_query.data else []

    # --- ШИРОКИ БАНЕРИ НАД ТАБОВЕТЕ ---
    if pos_data:
        p_title = pos_data.get('title', 'Неизвестна')
        p_city = pos_data.get('city', 'Няма')
        s_min = pos_data.get('salary_min', '0')
        s_max = pos_data.get('salary_max', '0')
        st.info(f"🎯 **Обява:** {p_title} ({p_city}) | **Възнаграждение:** EUR {s_min} - {s_max}")

    if all_comments:
        latest_note = all_comments[0]
        dt_str = pd.to_datetime(latest_note['created_at']).strftime('%d.%m.%Y %H:%M')
        full_text = latest_note.get('comment_text', '')
        display_text = full_text if len(full_text) <= 500 else full_text[:500] + "..."
        st.warning(f"💬 **Последна бележка ({latest_note.get('author_name', 'Система')} - {dt_str}):** {display_text}")

    st.write("<br>", unsafe_allow_html=True)

    # --- ТАБОВЕ ---
    tab_list = st.tabs(["📝 Въпросник", "📄 CV", "📊 Оценка", "💬 Бележки", "📅 Интервюта", "⚙️ Статус"])

    # ТАБ 1: ВЪПРОСНИК
    with tab_list[0]:
        if st.toggle("✏️ Редакция на текста", key=f"edit_toggle_q_{app_data['id']}"):
            updated_q = st.text_area("Въпросник (Редакция)", value=cv_info.get('questionnaire', ''), height=250)
            if st.button("💾 Запази Въпросник"):
                cv_info['questionnaire'] = updated_q
                supabase.table("hr_candidates").update({"raw_cv_data": cv_info}).eq("id", candidate['id']).execute()
                st.toast("✅ Въпросникът е запазен успешно!")
        else:
            st.markdown(cv_info.get('questionnaire', 'Няма въпросник.'))

    # ТАБ 2: CV
    with tab_list[1]:
        if st.toggle("✏️ Редакция на текста", key=f"edit_toggle_cv_{app_data['id']}"):
            updated_cv = st.text_area("CV Текст (Редакция)", value=cv_info.get('cv_text', ''), height=350)
            if st.button("💾 Запази CV"):
                cv_info['cv_text'] = updated_cv
                supabase.table("hr_candidates").update({"raw_cv_data": cv_info}).eq("id", candidate['id']).execute()
                st.toast("✅ CV-то е запазено успешно!")
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
                st.toast("✅ Оценките са обновени!")

    # ТАБ 4: БЕЛЕЖКИ (ИСТОРИЯ И ДОБАВЯНЕ)
    with tab_list[3]:
        st.markdown("### 💬 Добави нова бележка")
        note_to_add = st.text_area("Въведете коментар тук:", height=100, key=f"input_note_{app_data['id']}")
        if st.button("➕ Добави бележка", type="primary"):
            if note_to_add.strip():
                new_note_entry = {
                    "application_id": app_data['id'],
                    "author_name": st.session_state.username,
                    "comment_text": note_to_add.strip(),
                    "comment_type": "Бележка"
                }
                res = supabase.table("hr_comments").insert(new_note_entry).execute()
                if res.data:
                    all_comments.insert(0, res.data[0]) 
                st.toast("✅ Бележката е добавена успешно!")
                
        st.divider()
        st.markdown("### 📜 История")
        for comment in all_comments:
            with st.container(border=True):
                st.markdown(f"**{comment.get('author_name')}** | {pd.to_datetime(comment.get('created_at', datetime.now())).strftime('%d.%m.%Y %H:%M')}")
                st.write(comment.get('comment_text'))

    # ТАБ 5: ИНТЕРВЮТА (ТРИТЕ АКОРДЕОНА)
    with tab_list[4]:
        time_slots = generate_time_options()
        
        # 1. ТЕЛЕФОННО ИНТЕРВЮ
        with st.expander("📞 1. Телефонно интервю (HR Скрининг)", expanded=False):
            col_date1, col_time1 = st.columns(2)
            with col_date1:
                ph_d_val = datetime.strptime(interview_info['ph_date'], "%Y-%m-%d").date() if interview_info.get('ph_date') else datetime.now()
                phone_date = st.date_input("Дата на обаждане", value=ph_d_val, key=f"phone_date_{app_data['id']}")
            with col_time1:
                ph_t_val = interview_info.get('ph_time', '10:00')
                phone_time = st.selectbox("Час", time_slots, index=time_slots.index(ph_t_val) if ph_t_val in time_slots else 0, key=f"phone_time_{app_data['id']}")
            
            if st.button("📞 Запази график", type="primary", use_container_width=True):
                interview_info.update({'ph_date': phone_date.strftime("%Y-%m-%d"), 'ph_time': phone_time})
                supabase.table("hr_applications").update({"interview_details": interview_info}).eq("id", app_data['id']).execute()
                st.toast("✅ Графикът за телефонно интервю е запазен!")

        # 2. ПОКАНА ОТ МЕНИДЖЪР
        with st.expander("💡 2. Покана от мениджър (Предложение за дати)", expanded=False):
            st.info("Мениджърът предлага варианти за среща:")
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                m1_val = datetime.strptime(interview_info['mgr_date1'], "%Y-%m-%d").date() if interview_info.get('mgr_date1') else datetime.now()
                m_date1 = st.date_input("Вариант 1: Дата", value=m1_val, key=f"mgr_d1_{app_data['id']}")
                m_range1 = st.text_input("Вариант 1: Диапазон", value=interview_info.get('mgr_range1', ''), placeholder="напр. 10:00 - 12:00", key=f"mgr_r1_{app_data['id']}")
            with col_m2:
                m2_val = datetime.strptime(interview_info['mgr_date2'], "%Y-%m-%d").date() if interview_info.get('mgr_date2') else datetime.now()
                m_date2 = st.date_input("Вариант 2: Дата", value=m2_val, key=f"mgr_d2_{app_data['id']}")
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
            users_resp = supabase.table("users").select("username").execute()
            user_list = [u['username'] for u in users_resp.data] if users_resp.data else []
            curr_int = interview_info.get('interviewer_name', st.session_state.username)
            selected_interviewer = st.selectbox("Интервюиращ", user_list, index=user_list.index(curr_int) if curr_int in user_list else 0, key=f"sel_interv_{app_data['id']}")
            
            col_f_date, col_f_time = st.columns(2)
            with col_f_date:
                f_val = datetime.strptime(interview_info['interview_date'], "%Y-%m-%d").date() if interview_info.get('interview_date') else datetime.now()
                final_date = st.date_input("Финална Дата", value=f_val, key=f"final_date_{app_data['id']}")
            with col_f_time:
                f_t_val = interview_info.get('interview_time', '10:00')
                final_time = st.selectbox("Финален Час", time_slots, index=time_slots.index(f_t_val) if f_t_val in time_slots else 0, key=f"final_time_{app_data['id']}")
            
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

    # =========================================================================
    # ТАБ 6: СТАТУС (Опакован във Фрагмент, за да не подскача скролът)
    # =========================================================================
    @st.fragment
    def render_status_tab():
        st.markdown("### ⚙️ Смяна на статус")
        all_statuses = ["Нов", "Установи контакт", "Възможно интервю", "Избран за интервю", "Потвърдено интервю", "Направено предложение", "Отхвърлен", "Отказал", "Преместен"]
        current_status_name = app_data.get('status', 'Нов')
        new_status_selection = st.selectbox("Изберете нов статус", all_statuses, index=all_statuses.index(current_status_name) if current_status_name in all_statuses else 0)
        
        # Логика за "Отхвърлен"
        if new_status_selection == "Отхвърлен":
            reject_data = supabase.table("hr_settings").select("setting_value").eq("setting_key", "reject_reasons").execute()
            reject_reasons = reject_data.data[0].get("setting_value", ["Друго"]) if reject_data.data else ["Друго"]
            
            # Четем от правилните колони на hr_applications
            curr_r = app_data.get('rejection_reason')
            is_res = app_data.get('is_backup', False)
            
            st.selectbox("Причина за отхвърляне", reject_reasons, index=reject_reasons.index(curr_r) if curr_r in reject_reasons else 0, key=f"reject_reason_sel_{app_data['id']}")
            st.checkbox("Запази в резерва?", value=is_res, key=f"is_reserve_check_{app_data['id']}")

        # Логика за "Преместен / Копиран"
        if new_status_selection == "Преместен":
            pos_resp = supabase.table("hr_positions").select("id, title, company_name").eq("status", "Активна").eq("is_deleted", False).execute()
            target_positions = {p['id']: f"{p['title']} ({p['company_name']})" for p in pos_resp.data if p['id'] != pos_data['id']}
            
            if target_positions:
                target_id = st.selectbox("Премести в обява:", options=list(target_positions.keys()), format_func=lambda x: target_positions[x])
                keep_current = st.checkbox("Запази копие и в текущата обява?", value=False)
                
                if not keep_current:
                    # ПОПРАВЕНО СЪОБЩЕНИЕ ПО ИЗИСКВАНЕ НА ПОТРЕБИТЕЛЯ
                    st.warning("🚨 ВНИМАНИЕ: Кандидатът ще бъде прехвърлен в група 'Преместени'. Сигурни ли сте?")
                    confirm_btn_label = "⚠️ Потвърди окончателно преместване"
                else:
                    confirm_btn_label = "🔄 Премести (с копие)"
                    
                if st.button(confirm_btn_label, type="primary"):
                    target_pos_name = target_positions[target_id]
                    old_pos_name = f"{pos_data.get('title', '')} ({pos_data.get('company_name', '')})" if pos_data else "Неизвестна обява"
                    
                    if keep_current:
                        action_verb_old = "копиран в"
                        action_verb_new = "копиран от"
                    else:
                        action_verb_old = "преместен в"
                        action_verb_new = "преместен от"

                    # 1. Създаваме новия запис
                    new_app_res = supabase.table("hr_applications").insert({
                        "candidate_id": candidate['id'], 
                        "position_id": target_id, 
                        "status": "Нов"
                    }).execute()
                    
                    if new_app_res.data:
                        new_app_id = new_app_res.data[0]['id']
                        current_user = st.session_state.get('username', 'Система')
                        
                        # 2. Системна бележка в новия картон (Вариант Б)
                        supabase.table("hr_comments").insert({
                            "application_id": new_app_id,
                            "author_name": current_user,
                            "comment_text": f"Автоматично съобщение: Кандидатът е {action_verb_new} обява {old_pos_name}.",
                            "comment_type": "Системна"
                        }).execute()
                        
                        # 3. Системна бележка в стария картон (Вариант Б)
                        supabase.table("hr_comments").insert({
                            "application_id": app_data['id'],
                            "author_name": current_user,
                            "comment_text": f"Автоматично съобщение: Кандидатът беше {action_verb_old} обява {target_pos_name}.",
                            "comment_type": "Системна"
                        }).execute()
                        
                    # 4. Обновяване на стария статус (ако не е копие)
                    if not keep_current:
                        supabase.table("hr_applications").update({
                            "status": "Преместен"
                        }).eq("id", app_data['id']).execute()
                        
                    st.rerun()

        # Бутон за запазване на standard статуси
        if new_status_selection != "Преместен":
            if st.button("🔄 Запази новия статус", type="primary", use_container_width=True):
                update_payload = {
                    "status": new_status_selection,
                    "interview_details": interview_info
                }
                
                # Ако е отхвърлен, добавяме полетата за отхвърляне в правилните колони
                if new_status_selection == "Отхвърлен":
                    if f"reject_reason_sel_{app_data['id']}" in st.session_state:
                        update_payload['rejection_reason'] = st.session_state[f"reject_reason_sel_{app_data['id']}"]
                    if f"is_reserve_check_{app_data['id']}" in st.session_state:
                        update_payload['is_backup'] = st.session_state[f"is_reserve_check_{app_data['id']}"]
                else:
                    # Зачистваме ги, ако се върне в друг статус
                    update_payload['rejection_reason'] = None
                    update_payload['is_backup'] = False
                
                supabase.table("hr_applications").update(update_payload).eq("id", app_data['id']).execute()
                st.rerun()

    # ИЗВИКВАНЕ НА ФРАГМЕНТА В ТАБ 6
    with tab_list[5]:
        render_status_tab()

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
                supabase.table("hr_comments").delete().eq("application_id", app_data['id']).execute()
                supabase.table("hr_applications").delete().eq("id", app_data['id']).execute()
                supabase.table("hr_candidates").delete().eq("id", candidate['id']).execute()
                st.rerun()

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
