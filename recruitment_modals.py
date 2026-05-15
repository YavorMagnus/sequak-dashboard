import streamlit as st
import pandas as pd
from datetime import datetime
from utils import supabase, check_permission

# Помощна функция за генериране на часове през 15 минути
def generate_time_options():
    return [f"{h:02d}:{m:02d}" for h in range(8, 19) for m in (0, 15, 30, 45)]

# -----------------------------------------------------------------------------
# 1. МОДАЛ ЗА РЕДАКЦИЯ НА ОБЯВА И ИЗТРИВАНЕ
# -----------------------------------------------------------------------------
@st.dialog("Редакция на обява", width="large")
def edit_position_modal(pos_data):
    if not check_permission("recruitment", "manage_positions"):
        st.error("Нямате права за редакция на обяви.")
        return

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
                        apps_res = supabase.table("hr_applications").select("candidate_id").eq("position_id", pos_data['id']).execute()
                        cand_ids = [app['candidate_id'] for app in apps_res.data] if apps_res.data else []

                        supabase.table("hr_applications").delete().eq("position_id", pos_data['id']).execute()
                        
                        # Изчистваме и коментарите за тези кандидати (коригирано на owner_id)
                        if cand_ids:
                            supabase.table("hr_comments").delete().in_("owner_id", cand_ids).execute()
                            for c_id in cand_ids:
                                supabase.table("hr_candidates").delete().eq("id", c_id).execute()

                        supabase.table("hr_positions").delete().eq("id", pos_data['id']).execute()

                        st.session_state.active_campaign_id = None
                        st.success("Обявата и всички нейни кандидати са изтрити физически от базата данни.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Грешка при изтриване: {e}")
        return

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
            supabase.table("hr_positions").update(update_data).eq("id", pos_data['id']).execute()
            st.success("Промените са записани!")
            st.rerun()

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
                    apps_res = supabase.table("hr_applications").select("candidate_id").eq("position_id", pos_data['id']).execute()
                    cand_ids = [app['candidate_id'] for app in apps_res.data] if apps_res.data else []

                    supabase.table("hr_applications").delete().eq("position_id", pos_data['id']).execute()
                    
                    if cand_ids:
                        supabase.table("hr_comments").delete().in_("owner_id", cand_ids).execute()
                        for c_id in cand_ids:
                            supabase.table("hr_candidates").delete().eq("id", c_id).execute()

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
    
    competencies = ["Търговска", "Сервизна", "Строителна/архитектурна", "Юридическа", "IT", "Складова", "Счетоводно-административна", "Управленска"]
    
    # Разделяне на оценките
    total_obj = sum(manual_scores.get(comp, 0) for comp in competencies)
    total_subj = manual_scores.get("Субективна", 0)
    
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
        st.write(f"📧 {cv_data.get('email', 'Няма')}")
        st.write(f"📱 {cv_data.get('phone', 'Няма')}")
        
    with col_status:
        st.info(f"**Статус:** {app_data.get('status', 'Нов')}")
        next_int = int_details.get('interview_date')
        if next_int:
            st.warning(f"📅 Интервю: {next_int} в {int_details.get('interview_time', '')}")
            
        st.markdown(f"**Обективна оценка:** {total_obj}/48<br>**Субективна оценка:** {total_subj}/6", unsafe_allow_html=True)

    st.divider()

    # Извличане на бележките за страничната лента (ВРЪЗКАТА Е ПОПРАВЕНА НА owner_id)
    comments_res = supabase.table("hr_comments").select("*").eq("owner_id", candidate['id']).order("created_at", desc=True).execute()
    all_comments = comments_res.data if comments_res.data else []

    # --- РАЗПРЕДЕЛЕНИЕ С КОЛОНИ (3:1) ЗА ЛЕНТАТА ЗА БЕЛЕЖКИ ---
    col_main, col_side = st.columns([3, 1])

    with col_side:
        st.markdown("### 💬 Последна бележка")
        with st.container(border=True):
            if all_comments:
                latest_c = all_comments[0]
                text = latest_c['comment']
                short_text = text if len(text) <= 500 else text[:500] + "..."
                st.markdown(f"**{latest_c.get('author', 'Неизвестен')}**")
                st.caption(pd.to_datetime(latest_c['created_at']).strftime("%d.%m.%Y %H:%M"))
                st.write(short_text)
            else:
                st.caption("Няма добавени бележки.")

    with col_main:
        # --- ТАБОВЕ ---
        tab_quest, tab_cv, tab_eval, tab_notes, tab_int, tab_status = st.tabs([
            "📝 Въпросник", "📄 CV", "📊 Оценка", "💬 Бележки", "📅 Интервюта", "⚙️ Статус"
        ])

        with tab_quest:
            edit_q = st.toggle("✏️ Редакция на Въпросника", key=f"edit_q_{app_data['id']}")
            if edit_q:
                new_q = st.text_area("Текст", value=cv_data.get('questionnaire', ''), height=200)
                if st.button("💾 Запази Въпросника"):
                    cv_data['questionnaire'] = new_q
                    supabase.table("hr_candidates").update({"raw_cv_data": cv_data}).eq("id", candidate['id']).execute()
                    st.success("Въпросникът е обновен!")
                    st.rerun()
            else:
                st.markdown(cv_data.get('questionnaire', 'Няма въпросник.'))

        with tab_cv:
            edit_cv = st.toggle("✏️ Редакция на CV", key=f"edit_cv_{app_data['id']}")
            if edit_cv:
                new_cv = st.text_area("Текст на CV", value=cv_data.get('cv_text', ''), height=300)
                if st.button("💾 Запази CV"):
                    cv_data['cv_text'] = new_cv
                    supabase.table("hr_candidates").update({"raw_cv_data": cv_data}).eq("id", candidate['id']).execute()
                    st.success("CV-то е обновено!")
                    st.rerun()
            else:
                st.markdown(cv_data.get('cv_text', 'Няма текст на CV.'))

        with tab_eval:
            st.markdown("### 📊 Оценка по компетенции (Обективна)")
            with st.form(key=f"eval_form_{app_data['id']}"):
                new_scores = {}
                cols = st.columns(2)
                for i, comp in enumerate(competencies):
                    with cols[i % 2]:
                        val = manual_scores.get(comp, 1)
                        new_scores[comp] = st.slider(comp, 1, 6, val)
                
                st.divider()
                st.markdown("### 🎭 Субективна оценка (Цялостно впечатление)")
                new_scores["Субективна"] = st.slider("Субективна оценка", 1, 6, manual_scores.get("Субективна", 1))
                
                if st.form_submit_button("💾 Запази оценките", type="primary"):
                    supabase.table("hr_applications").update({"manual_score": new_scores}).eq("id", app_data['id']).execute()
                    st.success("Оценките са записани!")
                    st.rerun()

        with tab_notes:
            st.markdown("### 💬 Добави бележка/коментар")
            new_comment = st.text_area("Текст на бележката:", height=100, key=f"new_comm_{app_data['id']}")
            if st.button("➕ Добави бележка", type="primary"):
                if new_comment.strip():
                    supabase.table("hr_comments").insert({
                        "owner_id": candidate['id'], # КОРИГИРАНО
                        "author": st.session_state.username,
                        "comment": new_comment.strip()
                    }).execute()
                    st.success("Бележката е добавена!")
                    st.rerun()
            
            st.divider()
            st.markdown("### 📜 История на бележките")
            for c in all_comments:
                with st.container(border=True):
                    st.markdown(f"**{c.get('author', 'Неизвестен')}** | *{pd.to_datetime(c['created_at']).strftime('%d.%m.%Y %H:%M')}*")
                    st.write(c['comment'])

        with tab_int:
            time_options = generate_time_options()

            # АКОРДЕОН 1: ТЕЛЕФОННО ИНТЕРВЮ
            with st.expander("📞 1. Телефонно интервю (HR скрининг)", expanded=False):
                col_d1, col_t1 = st.columns(2)
                with col_d1:
                    ph_d_val = datetime.strptime(int_details['ph_date'], "%Y-%m-%d").date() if int_details.get('ph_date') else datetime.now()
                    ph_date = st.date_input("Дата за обаждане", value=ph_d_val, key=f"ph_d_{app_data['id']}")
                with col_t1:
                    ph_t_val = int_details.get('ph_time', '10:00')
                    ph_t_idx = time_options.index(ph_t_val) if ph_t_val in time_options else 0
                    ph_time = st.selectbox("Час", time_options, index=ph_t_idx, key=f"ph_t_{app_data['id']}")
                
                if st.button("📞 Насрочи обаждане", type="primary", use_container_width=True):
                    int_details.update({'ph_date': ph_date.strftime("%Y-%m-%d"), 'ph_time': ph_time, 'interview_type': 'Телефонно'})
                    
                    # --- [HOOK-NOTIFICATION]: Възможно интервю ---
                    supabase.table("hr_applications").update({
                        "interview_details": int_details, 
                        "status": "Възможно интервю"
                    }).eq("id", app_data['id']).execute()
                    
                    st.success("Телефонното обаждане е насрочено! Статусът е променен на 'Възможно интервю'.")
                    st.rerun()

            # АКОРДЕОН 2: ПОКАНА ОТ МЕНИДЖЪР
            with st.expander("💡 2. Покана от Мениджър (Предложение за дати)", expanded=False):
                st.markdown("Предложете две алтернативни дати и часови диапазони на HR-а:")
                c1, c2 = st.columns(2)
                with c1:
                    d1_val = datetime.strptime(int_details['mgr_date1'], "%Y-%m-%d").date() if int_details.get('mgr_date1') else datetime.now()
                    m_d1 = st.date_input("Опция 1: Дата", value=d1_val, key=f"md1_{app_data['id']}")
                    m_t1 = st.text_input("Опция 1: Диапазон (напр. след 14:00)", value=int_details.get('mgr_range1', ''), key=f"mt1_{app_data['id']}")
                with c2:
                    d2_val = datetime.strptime(int_details['mgr_date2'], "%Y-%m-%d").date() if int_details.get('mgr_date2') else datetime.now()
                    m_d2 = st.date_input("Опция 2: Дата", value=d2_val, key=f"md2_{app_data['id']}")
                    m_t2 = st.text_input("Опция 2: Диапазон (напр. 10:00 - 12:00)", value=int_details.get('mgr_range2', ''), key=f"mt2_{app_data['id']}")
                
                if st.button("💡 Предложи интервю", type="primary", use_container_width=True):
                    int_details.update({
                        'mgr_date1': m_d1.strftime("%Y-%m-%d"), 'mgr_range1': m_t1,
                        'mgr_date2': m_d2.strftime("%Y-%m-%d"), 'mgr_range2': m_t2
                    })
                    
                    # --- [HOOK-NOTIFICATION]: Избран за интервю -> Нотифицира контактьора (HR). ---
                    supabase.table("hr_applications").update({
                        "interview_details": int_details, 
                        "status": "Избран за интервю"
                    }).eq("id", app_data['id']).execute()
                    
                    st.success("Предложението е изпратено към HR! Статусът е променен на 'Избран за интервю'.")
                    st.rerun()

            # АКОРДЕОН 3: НАСРОЧВАНЕ НА ОФИЦИАЛНО ИНТЕРВЮ
            with st.expander("🏢 3. Насрочване на официално интервю", expanded=False):
                users_res = supabase.table("users").select("username").execute()
                all_users = [u['username'] for u in users_res.data] if users_res.data else []
                c_int = int_details.get('interviewer_name', st.session_state.username)
                c_idx = all_users.index(c_int) if c_int in all_users else 0
                
                new_interviewer = st.selectbox("Интервюиращ", all_users, index=c_idx, key=f"off_int_{app_data['id']}")
                
                col_d, col_t = st.columns(2)
                with col_d:
                    d_val = datetime.strptime(int_details['interview_date'], "%Y-%m-%d").date() if int_details.get('interview_date') else datetime.now()
                    new_date = st.date_input("Финална Дата", value=d_val, key=f"off_d_{app_data['id']}")
                with col_t:
                    t_val = int_details.get('interview_time', '10:00')
                    t_idx = time_options.index(t_val) if t_val in time_options else 0
                    new_time = st.selectbox("Финален Час", time_options, index=t_idx, key=f"off_t_{app_data['id']}")
                    
                if st.button("🏢 Потвърди интервю", type="primary", use_container_width=True):
                    int_details.update({
                        'interviewer_name': new_interviewer,
                        'interview_date': new_date.strftime("%Y-%m-%d"),
                        'interview_time': new_time,
                        'interview_type': 'Официално'
                    })
                    
                    # --- [HOOK-NOTIFICATION]: Потвърдено интервю -> Нотифицира избрания интервюиращ (Мениджър). ---
                    supabase.table("hr_applications").update({
                        "interview_details": int_details, 
                        "status": "Потвърдено интервю"
                    }).eq("id", app_data['id']).execute()
                    
                    st.success("Интервюто е официално насрочено и вписано в Графика! Статусът е променен.")
                    st.rerun()

        with tab_status:
            st.markdown("### ⚙️ Ръчна смяна на статус")
            statuses = ["Нов", "Установи контакт", "Възможно интервю", "Избран за интервю", "Потвърдено интервю", "Направено предложение", "Отхвърлен", "Отказал", "Преместен"]
            curr_idx = statuses.index(app_data.get('status', 'Нов')) if app_data.get('status') in statuses else 0
            new_status = st.selectbox("Изберете нов статус", statuses, index=curr_idx)
            
            # --- ЛОГИКА ЗА ОТХВЪРЛЕН ---
            if new_status == "Отхвърлен":
                try:
                    settings_data = supabase.table("hr_settings").select("setting_value").eq("setting_key", "reject_reasons").execute()
                    reasons_list = settings_data.data[0].get("setting_value", []) if settings_data.data else ["Друго"]
                except:
                    reasons_list = ["Друго"]
                
                curr_r = int_details.get('rejection_reason')
                r_idx = reasons_list.index(curr_r) if curr_r in reasons_list else 0
                st.selectbox("Причина за отхвърляне", reasons_list, index=r_idx, key=f"sel_reason_{app_data['id']}")
                st.checkbox("Запази като резерва ❓", value=int_details.get('reserve_checkbox', False), key=f"check_reserve_{app_data['id']}")

            # --- ЛОГИКА ЗА ПРЕМЕСТЕН ---
            if new_status == "Преместен":
                act_pos_res = supabase.table("hr_positions").select("id, title, company_name").eq("status", "Активна").eq("is_deleted", False).execute()
                act_pos = act_pos_res.data if act_pos_res.data else []
                # Изключваме текущата обява от списъка с таргети
                target_opts = {p['id']: f"{p['title']} ({p['company_name']})" for p in act_pos if p['id'] != pos_data['id']}
                
                if not target_opts:
                    st.warning("Няма други активни обяви, в които да преместите кандидата.")
                else:
                    target_id = st.selectbox("Изберете обява (Таргет):", options=list(target_opts.keys()), format_func=lambda x: target_opts[x])
                    keep_copy = st.checkbox("Запази копие и в текущата обява ⚠️", value=False)
                    
                    if not keep_copy:
                        st.warning("🚨 Внимание! Не сте избрали да запазите копие. Кандидатът ще бъде премахнат от ТЕКУЩАТА обява завинаги. Сигурни ли сте?")
                        btn_label = "⚠️ Потвърди окончателно преместване"
                    else:
                        btn_label = "🔄 Премести (с копие)"

                    if st.button(btn_label, type="primary"):
                        if keep_copy:
                            supabase.table("hr_applications").insert({
                                "candidate_id": candidate['id'],
                                "position_id": target_id,
                                "status": "Нов",
                                "is_deleted": False,
                                "interview_details": {}
                            }).execute()
                            # --- [HOOK-NOTIFICATION]: Преместен (С Копие) -> Нотифицира мениджъра на ТАРГЕТ-обявата и контактьора. ---
                            st.success("Кандидатът е успешно копиран в новата обява!")
                        else:
                            # --- [HOOK-NOTIFICATION]: Преместен (Без Копие) -> Нотифицира мениджъра на ТАРГЕТ-обявата и контактьора. ---
                            supabase.table("hr_applications").update({
                                "position_id": target_id,
                                "status": "Нов",
                                "interview_details": {} 
                            }).eq("id", app_data['id']).execute()
                            st.success("Кандидатът е окончателно преместен!")
                        st.rerun()

            # Бутон за стандартните статуси
            if new_status != "Преместен":
                if st.button("🔄 Запази статуса", use_container_width=True, type="primary"):
                    if new_status == "Отхвърлен":
                        if f"sel_reason_{app_data['id']}" in st.session_state:
                            int_details['rejection_reason'] = st.session_state[f"sel_reason_{app_data['id']}"]
                        if f"check_reserve_{app_data['id']}" in st.session_state:
                            int_details['reserve_checkbox'] = st.session_state[f"check_reserve_{app_data['id']}"]
                    
                    # --- [HOOK-NOTIFICATION]: Нов -> Нотифицира мениджъра И контактьора.
                    # --- [HOOK-NOTIFICATION]: Установи контакт -> Нотифицира само контактьора.
                    supabase.table("hr_applications").update({"status": new_status, "interview_details": int_details}).eq("id", app_data['id']).execute()
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
                        supabase.table("hr_applications").delete().eq("id", app_data['id']).execute()
                        # Изчистваме коментарите (коригирано на owner_id)
                        supabase.table("hr_comments").delete().eq("owner_id", app_data['candidate_id']).execute()
                        supabase.table("hr_candidates").delete().eq("id", app_data['candidate_id']).execute()
                        st.success("Кандидатурата е изтрита физически.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Грешка при изтриване: {e}")

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
