import streamlit as st
import pandas as pd
from utils import supabase, check_permission, SYSTEM_ROLES
from parsers import parse_jobs_zip, parse_spreadsheet
import time
from datetime import datetime

# --- ИНИЦИАЛИЗАЦИЯ НА СЕСИЯТА ---
if "active_company" not in st.session_state: 
    st.session_state.active_company = None
if "active_campaign_id" not in st.session_state: 
    st.session_state.active_campaign_id = None
if "force_open_global_interviews" not in st.session_state: 
    st.session_state.force_open_global_interviews = False

# Карта на емоджитата за статус
EMOJI_MAP = {
    "Нов": "✨",
    "Установи контакт": "📞",
    "В процес на контакт": "⏳",
    "Възможно интервю": "➕",
    "Избран за интервю": "📅",
    "Потвърдено интервю": "✅",
    "Направено предложение": "🏆",
    "Отхвърлен": "❌",
    "Отказал": "🛑",
    "Преместен": "📦"
}

# --- ПОМОЩНИ ФУНКЦИИ ---
def log_status_change(app_id, old_status, new_status):
    current_user = st.session_state.get("username", "Unknown")
    try:
        supabase.table("hr_status_history").insert({
            "application_id": app_id,
            "old_status": old_status,
            "new_status": new_status,
            "changed_by": current_user
        }).execute()
    except Exception:
        pass

def get_traffic_light_6(val):
    if val <= 2: 
        return "🔴"
    if val <= 4: 
        return "🟡"
    return "🟢"

def get_traffic_light_perc(val):
    if val < 50: 
        return "🔴"
    if val < 75: 
        return "🟡"
    return "🟢"

def get_pos_display_name(p):
    base_str = f" ({p.get('base_location')})" if p.get('base_location') else ""
    city_str = f" | 📍 {p.get('city', 'Непосочен')}{base_str}"
    status_str = " 🗄️[АРХИВ]" if p.get('status') == 'Архивирана' else ""
    return f"{p['title']}{city_str}{status_str}"

# --- МОДАЛИ ---
@st.dialog("➕ Създаване на нова кампания", width="large")
def open_new_campaign_modal(company_name, sys_users):
    st.write(f"🏢 Фирма: **{company_name}**")
    
    with st.form("new_pos_form", clear_on_submit=True):
        t = st.text_input("Име на позицията *")
        
        st.write("👥 **Роли по кампанията (за Action Center)**")
        r_col1, r_col2 = st.columns(2)
        with r_col1: 
            selected_owners = st.multiselect(
                "Собственици (Мениджъри):", 
                sys_users, 
                help="Получават задачи за Нови, Възможни и Потвърдени интервюта."
            )
        with r_col2: 
            selected_hr = st.selectbox(
                "HR (Установяващ контакт):", 
                ["--- Избери ---"] + sys_users, 
                help="Получава задачи за Установяване на контакт и Направени предложения."
            )
        
        pos_method = st.selectbox(
            "Метод за оценка", 
            ["Числова оценка 1-6 - обективна и субективна", "AI Оценка + Профилна матрица"]
        )
        
        cc1, cc2 = st.columns(2)
        with cc1: 
            s_min = st.text_input("Мин. възнаграждение (EUR)")
            s_max = st.text_input("Макс. възнаграждение (EUR)")
        with cc2: 
            city = st.text_input("Град")
            base_loc = st.text_input("База (незадължително)")
        
        w_type = st.selectbox("Тип работа", ["Присъствено", "Хибрид", "Remote"])
        priority = st.selectbox("Приоритет", ["Оглеждаме се", "Нормално", "Спешно", "🔥 ПОЖАР"], index=1)
        
        submit_btn = st.form_submit_button("💾 Регистрирай кампанията", type="primary")
        
        if submit_btn:
            if not t.strip():
                st.error("⚠️ Моля, въведете име на позицията!")
            else:
                hr_val = selected_hr if selected_hr != "--- Избери ---" else None
                supabase.table("hr_positions").insert({
                    "company_name": company_name, 
                    "title": t, 
                    "evaluation_method": pos_method, 
                    "salary_min": s_min, 
                    "salary_max": s_max, 
                    "city": city, 
                    "base_location": base_loc, 
                    "work_type": w_type, 
                    "priority": priority, 
                    "status": "Активна", 
                    "owners": selected_owners, 
                    "hr_contact": hr_val
                }).execute()
                
                st.success("✅ Кампанията е създадена успешно!")
                time.sleep(1)
                st.rerun()

@st.dialog("📅 Глобален График Интервюта", width="large")
def open_interview_dashboard(apps_data, global_pos_map=None):
    show_archived = st.checkbox("Покажи архив (приключени събития)", value=False)
    
    interviews = []
    for app in apps_data:
        details = app.get("interview_details")
        if details and details.get("interviewer"):
            comp_title = global_pos_map[app['position_id']]['company_name'] if global_pos_map and app['position_id'] in global_pos_map else ""
            i_type = details.get("type", "В процес на контакт")
            is_active = (app["status"] == i_type)
            
            if show_archived or is_active:
                interviews.append({
                    "app_id": app["id"], 
                    "pos_id": app["position_id"], 
                    "company": comp_title,
                    "interviewer": details["interviewer"], 
                    "date": details.get("date", ""), 
                    "time": details.get("time", ""), 
                    "candidate": app["hr_candidates"]["full_name"], 
                    "status": app["status"], 
                    "type": i_type, 
                    "is_active": is_active
                })
            
    if not interviews: 
        st.info("Няма интервюта, отговарящи на критериите.")
        return
        
    interviewers = sorted(list(set([i["interviewer"] for i in interviews])))
    
    col1, col2 = st.columns(2)
    with col1: 
        selected_int = st.selectbox("👤 Избери Интервюиращ:", interviewers)
    with col2: 
        filter_type = st.radio("Филтър по вид:", ["Всички", "В процес на контакт", "Потвърдено интервю"], horizontal=True)
    
    st.divider()
    
    filtered_ints = [i for i in interviews if i["interviewer"] == selected_int]
    if filter_type != "Всички": 
        filtered_ints = [i for i in filtered_ints if i["type"] == filter_type]
        
    filtered_ints.sort(key=lambda x: (x["date"], x["time"]))
    
    if filtered_ints:
        for i in filtered_ints:
            icon = "📞" if i["type"] == "В процес на контакт" else "🤝"
            status_badge = "" if i["is_active"] else f" *(Статус: {i['status']})*"
            
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"**{i['date']} | {i['time']} ч.** {icon} **{i['candidate']}** *(Фирма: {i['company']})*{status_badge}")
            
            if c2.button("Отвори", key=f"btn_route_{i['app_id']}"):
                if global_pos_map and i['pos_id'] in global_pos_map:
                    st.session_state.active_company = global_pos_map[i['pos_id']]['company_name']
                    st.session_state.active_campaign_id = i['pos_id']
                    st.session_state.force_open_app_id = i['app_id']
                    st.rerun()
    else: 
        st.warning("Няма интервюта от този тип за избрания колега.")
@st.dialog("📄 Картон на кандидата", width="large")
def open_candidate_card(app_id, candidate_id, candidate_name, status, raw_cv_data, photo_base64, manual_score, all_global_positions_raw, all_active_positions, current_pos_id, created_at, interview_details, sys_reject_reasons, sys_decline_reasons, score_categories, sys_users, is_backup):
    can_evaluate = check_permission("recruitment", "evaluate")
    can_soft_delete = check_permission("recruitment", "soft_delete")
    current_user = st.session_state.get("username", "Unknown")
    
    comments_res = supabase.table("hr_comments").select("*").eq("application_id", app_id).order("created_at").execute()
    comments = comments_res.data or []
    is_ghost_record = (status == "Преместен")
    
    curr_manual = manual_score if isinstance(manual_score, dict) else {}
    curr_sub_rating = curr_manual.get("subjective_rating", 0)
    curr_sub_motive = curr_manual.get("subjective_motive", "")
    curr_sc_active = curr_manual.get("scorecard_active", False)
    curr_matrix = curr_manual.get("profile_matrix", {})
    curr_sc_perc = curr_manual.get("scorecard_percentage", 0)
    
    last_human_comment = None
    meeting_request = None
    for c in reversed(comments):
        if "🤖 Система" not in c["author_name"] and not last_human_comment: 
            last_human_comment = c
        if "🟡 ЗАЯВКА ЗА СРЕЩА" in c["comment_text"] and status == "Избран за интервю" and not meeting_request: 
            meeting_request = c
    
    col_img, col_info = st.columns([1, 4])
    with col_img:
        if photo_base64: 
            st.markdown(f'<img src="data:image/png;base64,{photo_base64}" style="width:100%; border-radius:10px;">', unsafe_allow_html=True)
        else: 
            st.info("Няма снимка")
            
    with col_info:
        st.subheader(f"👤 {candidate_name}")
        st.caption(f"Статус: **{status}** | Качен: {created_at[:10]}")
        
        if can_evaluate:
            new_backup = st.checkbox("❓ Маркирай като 'Резерва / За обмисляне'", value=is_backup)
            if new_backup != is_backup:
                supabase.table("hr_applications").update({"is_backup": new_backup}).eq("id", app_id).execute()
                st.session_state.force_open_app_id = app_id
                st.rerun()

        if curr_sub_rating > 0: 
            tl = get_traffic_light_6(curr_sub_rating)
            m_text = f" *(Мотив: {curr_sub_motive})*" if curr_sub_motive.strip() else ""
            st.info(f"**🎯 Заключителна оценка:** {curr_sub_rating} / 6 {tl} {m_text}")
        
        if curr_sc_active:
            tl_p = get_traffic_light_perc(curr_sc_perc)
            st.info(f"**📊 Област на компетентност:** {curr_sc_perc}% {tl_p}")
            matrix_details = [f"{k}: {v} {get_traffic_light_6(v)}" for k, v in curr_matrix.items()]
            if matrix_details: 
                st.caption(f"Профил: {' | '.join(matrix_details)}")
                
        if interview_details: 
            st.warning(f"⏰ **Интервю:** {interview_details.get('type', 'В процес на контакт')} | {interview_details.get('date')} - {interview_details.get('time')} с {interview_details.get('interviewer')}")
        
        if meeting_request:
            req_text = meeting_request['comment_text'].replace('🟡 ЗАЯВКА ЗА СРЕЩА:\n', '').replace('🟡 ЗАЯВКА ЗА СРЕЩА:', '').strip()
            st.warning(f"🎯 **Заявка за интервю от {meeting_request['author_name']}**:\n{req_text}")
        
        if last_human_comment:
            trunc_txt = last_human_comment['comment_text'][:120] + "..." if len(last_human_comment['comment_text']) > 120 else last_human_comment['comment_text']
            st.markdown(f"<div style='font-size: 0.85em; color: #aaa; margin-top: 5px; padding-left: 10px; border-left: 2px solid #555;'>💬 <b>{last_human_comment['author_name']}:</b> {trunc_txt}</div>", unsafe_allow_html=True)

st.divider()
    tabs = st.tabs(["📋 Въпросник", "📝 Бележки", "📄 CV", "📅 Интервюта", "📊 Оценка"])
    cv_dict = raw_cv_data if isinstance(raw_cv_data, dict) else {}
    
    with tabs[0]: 
        if can_evaluate and st.button("✏️ Редактирай Въпросник", key=f"edit_q_{app_id}"): 
            st.session_state[f"q_edit_{app_id}"] = not st.session_state.get(f"q_edit_{app_id}", False)
        if st.session_state.get(f"q_edit_{app_id}", False):
            new_q = st.text_area("Редакция", value=cv_dict.get("questionnaire", ""), height=300, key=f"txt_q_{app_id}")
            if st.button("💾 Запази", key=f"save_q_{app_id}"):
                cv_dict["questionnaire"] = new_q
                supabase.table("hr_candidates").update({"raw_cv_data": cv_dict}).eq("id", candidate_id).execute()
                st.session_state[f"q_edit_{app_id}"] = False
                st.session_state.force_open_app_id = app_id
                st.rerun()
        else: 
            st.markdown(cv_dict.get("questionnaire", "Няма данни"))
    
    with tabs[1]:
        for comm in comments:
            is_sys = "🤖 Система" in comm['author_name']
            with st.chat_message("assistant" if is_sys else "user"):
                c1, c2 = st.columns([9,1])
                c1.write(f"**{comm['author_name']}** ({comm['created_at'][:16]})\n\n{comm['comment_text']}")
                if not is_sys and comm['author_name'] == current_user and "🗑️" not in comm['comment_text']:
                    if c2.button("🗑️", key=f"del_c_{comm['id']}", help="Изтрий бележката"):
                        supabase.table("hr_comments").update({"comment_text": f"🗑️ *Бележката е изтрита от {comm['author_name']} на {datetime.now().strftime('%Y-%m-%d %H:%M')}*"}).eq("id", comm['id']).execute()
                        st.session_state.force_open_app_id = app_id
                        st.rerun()
                        
        if not is_ghost_record and can_evaluate:
            with st.form("new_comment", clear_on_submit=True):
                comment_txt = st.text_area("Добави коментар:")
                if st.form_submit_button("Добави бележка") and comment_txt:
                    supabase.table("hr_comments").insert({"application_id": app_id, "author_name": current_user, "comment_text": comment_txt}).execute()
                    st.session_state.force_open_app_id = app_id
                    st.rerun()

    with tabs[2]: 
        if can_evaluate and st.button("✏️ Редактирай CV", key=f"edit_cv_{app_id}"): 
            st.session_state[f"cv_edit_{app_id}"] = not st.session_state.get(f"cv_edit_{app_id}", False)
        if st.session_state.get(f"cv_edit_{app_id}", False):
            new_cv = st.text_area("Редакция", value=cv_dict.get("cv_text", ""), height=400, key=f"txt_cv_{app_id}")
            if st.button("💾 Запази", key=f"save_cv_{app_id}"):
                cv_dict["cv_text"] = new_cv
                supabase.table("hr_candidates").update({"raw_cv_data": cv_dict}).eq("id", candidate_id).execute()
                st.session_state[f"cv_edit_{app_id}"] = False
                st.session_state.force_open_app_id = app_id
                st.rerun()
        else: 
            st.markdown(cv_dict.get("cv_text", "Няма данни"))
    
    with tabs[3]:
        if not is_ghost_record and check_permission("recruitment", "schedule"):
            with st.form("propose_dates"):
                st.markdown("#### 🎯 Заявка за интервю (Към HR)")
                c1, c2 = st.columns(2)
                d1 = c1.date_input("Дата 1")
                d2 = c2.date_input("Дата 2")
                if st.form_submit_button("🎯 Заяви 'Избран за интервю'"):
                    supabase.table("hr_applications").update({"status": "Избран за интервю"}).eq("id", app_id).execute()
                    supabase.table("hr_comments").insert({"application_id": app_id, "author_name": current_user, "comment_text": f"🟡 ЗАЯВКА ЗА СРЕЩА: Опции {d1} и {d2}"}).execute()
                    st.session_state.force_open_app_id = app_id
                    st.rerun()
                    
    with tabs[4]:
        st.write("### 🎯 Оценка")
        new_sub = st.slider("Оценка", 0, 6, int(curr_sub_rating), disabled=(is_ghost_record or not can_evaluate))
        if not is_ghost_record and can_evaluate and st.button("💾 Запиши оценка", use_container_width=True):
            supabase.table("hr_applications").update({"manual_score": {"subjective_rating": new_sub}}).eq("id", app_id).execute()
            st.session_state.force_open_app_id = app_id
            st.rerun()
   
# --- ОСНОВЕН РЕНДЕР ---
def render_recruitment_module():
    if "active_company" not in st.session_state: 
        st.session_state.active_company = None
    if "active_campaign_id" not in st.session_state: 
        st.session_state.active_campaign_id = None

    # DEEP LINKING
    if "app_id" in st.query_params:
        deep_app_id = st.query_params["app_id"]
        st.query_params.clear() 
        try:
            dl_res = supabase.table("hr_applications").select("position_id, hr_positions(company_name)").eq("id", deep_app_id).execute()
            if dl_res.data:
                st.session_state.active_company = dl_res.data[0]["hr_positions"]["company_name"]
                st.session_state.active_campaign_id = dl_res.data[0]["position_id"]
                st.session_state.force_open_app_id = deep_app_id
        except Exception:
            pass

    COMPANIES = ["REN", "CIM", "MAS", "BAU", "AST", "CMX", "RXS", "SNW", "RXB", "DXM"]
    current_user = st.session_state.get("username", "Unknown")
    
    # ПРАВА
    can_manage_pos = check_permission("recruitment", "manage_positions")
    can_soft_delete = check_permission("recruitment", "soft_delete")
    
    settings_res = supabase.table("hr_settings").select("*").execute()
    settings_dict = {row["setting_key"]: row["setting_value"] for row in settings_res.data} if settings_res.data else {}
    sys_reject_reasons = settings_dict.get("reject_reasons", ["Липса на опит", "Друго"])
    sys_decline_reasons = settings_dict.get("decline_reasons", ["Започнал друга работа", "Друго"])
    score_categories = settings_dict.get("score_categories", ["Умения"])

    users_res = supabase.table("users").select("username").execute()
    sys_users = sorted([u['username'] for u in users_res.data]) if users_res.data else []

    all_pos_res = supabase.table("hr_positions").select("*").order("company_name").order("title").execute()
    all_global_positions_raw = all_pos_res.data or []
    
    all_active_positions = [p for p in all_global_positions_raw if not p.get("is_deleted")]
    deleted_positions = [p for p in all_global_positions_raw if p.get("is_deleted")]
    global_pos_map = {p["id"]: p for p in all_active_positions}

    # ACTION CENTER
    watched_statuses = ["Нов", "Установи контакт", "Възможно интервю", "Избран за интервю", "Потвърдено интервю", "Направено предложение"]
    active_apps = supabase.table("hr_applications").select("position_id, status").eq("is_deleted", False).in_("status", watched_statuses).execute().data or []
    
    tasks = []
    for pos in all_active_positions:
        if pos.get("status") == "Архивирана": 
            continue
        if current_user in (pos.get("owners") or []) or current_user == pos.get("hr_contact"):
            pos_apps = [a for a in active_apps if a["position_id"] == pos["id"]]
            if pos_apps: 
                tasks.append({"text": f"Задачи: {len(pos_apps)}", "pos": pos})

    with st.sidebar:
        if tasks:
            with st.expander(f"📬 Задачи ({len(tasks)})", expanded=True):
                for i, task in enumerate(tasks):
                    st.write(f"**{task['pos']['title']}**")
                    if st.button("➡️ Към обявата", key=f"t_{i}", use_container_width=True):
                        st.session_state.active_company = task['pos']['company_name']
                        st.session_state.active_campaign_id = task['pos']['id']
                        st.rerun()

    c1, c2 = st.columns([3,1])
    c1.header("📋 Модул Подбор (V40.3 Final)")
    with c2:
        if st.button("📅 Глобален график", use_container_width=True):
            all_int_apps = supabase.table("hr_applications").select("*, hr_candidates(*)").neq("interview_details", "null").eq("is_deleted", False).execute().data or []
            open_interview_dashboard(all_int_apps, global_pos_map)

    selected_nav = st.pills("Навигация", ["🌍 Дашборд"] + COMPANIES, default=st.session_state.active_company or "🌍 Дашборд")
    
    if selected_nav == "🌍 Дашборд":
        st.session_state.active_company = None
        st.session_state.active_campaign_id = None
        st.write("### 🌍 Активни обяви")
        
        for p in all_active_positions:
            with st.container(border=True):
                cc1, cc2 = st.columns([4, 1])
                cc1.write(f"**{p['title']}** ({p['company_name']})")
                if cc2.button("Отвори", key=f"dash_{p['id']}", use_container_width=True):
                    st.session_state.active_company = p['company_name']
                    st.session_state.active_campaign_id = p['id']
                    st.rerun()
            
        if st.session_state.get('user_role') in ["Супер-админ", "Администратор"]:
            st.divider()
            with st.expander("🗑️ Системно кошче (Суперадмин)"):
                t1, t2 = st.tabs(["Кандидати", "Кампании"])
                with t1:
                    deleted_apps = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("is_deleted", True).execute().data or []
                    for d_app in deleted_apps:
                        col_tx, col_b1, col_b2 = st.columns([4, 1, 1])
                        col_tx.write(f"👤 {d_app['hr_candidates']['full_name']}")
                        if col_b1.button("♻️", key=f"r_app_{d_app['id']}", help="Възстанови"):
                            supabase.table("hr_applications").update({"is_deleted": False}).eq("id", d_app['id']).execute()
                            st.rerun()
                        if col_b2.button("❌", key=f"h_app_{d_app['id']}", help="Хард Делийт"):
                            supabase.table("hr_applications").delete().eq("id", d_app['id']).execute()
                            st.rerun()
                with t2:
                    for d_pos in deleted_positions:
                        col_tx, col_b1, col_b2 = st.columns([4, 1, 1])
                        col_tx.write(f"📁 {d_pos['title']} ({d_pos['company_name']})")
                        if col_b1.button("♻️", key=f"r_pos_{d_pos['id']}", help="Възстанови"):
                            supabase.table("hr_positions").update({"is_deleted": False}).eq("id", d_pos['id']).execute()
                            supabase.table("hr_applications").update({"is_deleted": False}).eq("position_id", d_pos['id']).execute()
                            st.rerun()
                        if col_b2.button("❌", key=f"h_pos_{d_pos['id']}", help="Хард Делийт"):
                            supabase.table("hr_applications").delete().eq("position_id", d_pos['id']).execute()
                            supabase.table("hr_positions").delete().eq("id", d_pos['id']).execute()
                            st.rerun()
        return

    st.session_state.active_company = selected_nav
    current_company_positions = [p for p in all_active_positions if p["company_name"] == selected_nav]
    
    if not current_company_positions:
        st.warning("Няма активни кампании.")
        if can_manage_pos and st.button("➕ Създай кампания"): 
            open_new_campaign_modal(selected_nav, sys_users)
        return

    camp_options = {p["id"]: get_pos_display_name(p) for p in current_company_positions}
    if st.session_state.active_campaign_id not in camp_options: 
        st.session_state.active_campaign_id = list(camp_options.keys())[0]
    
    selected_pos_id = st.selectbox(
        "Изберете кампания:", 
        options=list(camp_options.keys()), 
        format_func=lambda x: camp_options[x], 
        index=list(camp_options.keys()).index(st.session_state.active_campaign_id)
    )
    st.session_state.active_campaign_id = selected_pos_id
    pos_info = next(p for p in current_company_positions if p["id"] == selected_pos_id)

    # УПРАВЛЕНИЕ (С ПРОВЕРКА НА ПРАВА)
    if can_manage_pos or can_soft_delete:
        with st.expander("⚙️ Управление на обявата"):
            if can_manage_pos:
                with st.form("edit_pos"):
                    st.write("📝 Параметри")
                    st.form_submit_button("💾 Запиши")
            if can_soft_delete:
                if st.button("🚨 Изтрий кампанията (В Кошчето)", type="primary", use_container_width=True):
                    supabase.table("hr_positions").update({"is_deleted": True}).eq("id", selected_pos_id).execute()
                    supabase.table("hr_applications").update({"is_deleted": True}).eq("position_id", selected_pos_id).execute()
                    st.session_state.active_campaign_id = None
                    st.rerun()

    # ИМПОРТ
    if check_permission("recruitment", "upload_candidates"):
        with st.expander("📥 Импорт (ZIP, Excel, CSV)"):
            up_f = st.file_uploader("Файлове", type=["zip", "xlsx", "xls", "csv"], accept_multiple_files=True)
            if up_f and st.button("▶️ Старт импорт", type="primary"):
                sc, dc = 0, 0
                for f in up_f:
                    cands = [parse_jobs_zip(f)] if f.name.lower().endswith(".zip") else parse_spreadsheet(f)
                    for n, d, p in cands:
                        email, phone = d.get("email"), d.get("phone")
                        q = supabase.table("hr_applications").select("id, hr_candidates!inner(id)").eq("position_id", selected_pos_id).eq("is_deleted", False)
                        
                        if email: 
                            q = q.eq("hr_candidates.raw_cv_data->>email", email)
                        if phone: 
                            q = q.eq("hr_candidates.raw_cv_data->>phone", phone)
                            
                        if q.execute().data: 
                            dc += 1
                            continue
                            
                        c = supabase.table("hr_candidates").insert({"full_name": n, "raw_cv_data": d, "photo_thumbnail": p}).execute()
                        if c.data: 
                            supabase.table("hr_applications").insert({"candidate_id": c.data[0]["id"], "position_id": selected_pos_id, "status": "Нов"}).execute()
                            sc += 1
                            
                st.success(f"Качени: {sc}. Дубликати: {dc}")
                time.sleep(2)
                st.rerun()

    st.divider()
    apps = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("position_id", selected_pos_id).eq("is_deleted", False).execute().data or []
    
    if apps:
        cols = st.columns(4)
        for i, app in enumerate(apps):
            with cols[i % 4]:
                with st.container(border=True):
                    st.write(f"**{app['hr_candidates']['full_name']}**")
                    st.caption(app['status'])
                    if st.button("📄 Отвори", key=f"a_{app['id']}", use_container_width=True):
                        open_candidate_card(
                            app["id"], 
                            app["hr_candidates"]["id"], 
                            app["hr_candidates"]["full_name"], 
                            app["status"], 
                            app["hr_candidates"]["raw_cv_data"], 
                            app["hr_candidates"]["photo_thumbnail"], 
                            app["manual_score"], 
                            all_global_positions_raw, 
                            all_active_positions, 
                            selected_pos_id, 
                            app["created_at"], 
                            app.get("interview_details", {}), 
                            sys_reject_reasons, 
                            sys_decline_reasons, 
                            score_categories, 
                            sys_users, 
                            app.get("is_backup", False)
                        )
    else: 
        st.info("Няма кандидати.")

    if "force_open_app_id" in st.session_state and st.session_state.force_open_app_id:
        f_app = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("id", st.session_state.force_open_app_id).execute().data
        if f_app: 
            st.session_state.force_open_app_id = None
            open_candidate_card(
                f_app[0]["id"], 
                f_app[0]["hr_candidates"]["id"], 
                f_app[0]["hr_candidates"]["full_name"], 
                f_app[0]["status"], 
                f_app[0]["hr_candidates"]["raw_cv_data"], 
                f_app[0]["hr_candidates"]["photo_thumbnail"], 
                f_app[0]["manual_score"], 
                all_global_positions_raw, 
                all_active_positions, 
                f_app[0]["position_id"], 
                f_app[0]["created_at"], 
                f_app[0].get("interview_details", {}), 
                sys_reject_reasons, 
                sys_decline_reasons, 
                score_categories, 
                sys_users, 
                f_app[0].get("is_backup", False)
            )

if __name__ == "__main__":
    render_recruitment_module()
