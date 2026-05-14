import streamlit as st
import pandas as pd
from utils import supabase, check_permission
from recruitment_modals import edit_position_modal, candidate_card_modal, create_position_modal
# ИМПОРТ САМО НА СТАРИТЕ, РАБОТЕЩИ ПАРСЪРИ
from parsers import parse_jobs_zip, parse_spreadsheet

def run_recruitment():
    st.title("🎯 Подбор на персонал (Recruitment)")
    
    # --- ИНИЦИАЛИЗАЦИЯ НА СЕСИЯТА ---
    if "active_company" not in st.session_state:
        st.session_state.active_company = "ВСИЧКИ" 
    if "active_campaign_id" not in st.session_state:
        st.session_state.active_campaign_id = None
    if "deep_link_triggered" not in st.session_state:
        st.session_state.deep_link_triggered = False

    # --- 1. DEEP LINK ---
    query_params = st.query_params
    if "app_id" in query_params and not st.session_state.deep_link_triggered:
        target_app_id = query_params["app_id"]
        target_app = supabase.table("hr_applications").select("*, hr_candidates(*), hr_positions(*)").eq("id", target_app_id).execute()
        if target_app.data:
            app_data = target_app.data[0]
            pos_data = app_data.get("hr_positions", {})
            if pos_data:
                st.session_state.active_company = pos_data.get("company_name", "REN")
                st.session_state.active_campaign_id = pos_data.get("id")
            st.session_state.deep_link_triggered = True
            candidate_card_modal(app_data.get("hr_candidates", {}), app_data, pos_data)

    # --- 2. ИЗБОР НА ФИРМА (Pills) И НОВА ОБЯВА ---
    companies = ["ВСИЧКИ", "REN", "CIM", "MAS", "BAU", "AST", "RXS", "RXB", "SNW", "DXM", "ICM"]
    
    col_comp, col_new = st.columns([5, 1])
    with col_comp:
        st.session_state.active_company = st.pills("Изберете фирма:", companies, default="ВСИЧКИ", selection_mode="single")
        if not st.session_state.active_company: 
            st.session_state.active_company = "ВСИЧКИ"
            
    with col_new:
        st.write("<br>", unsafe_allow_html=True)
        if st.button("➕ Нова обява", type="secondary", use_container_width=True):
            create_position_modal(st.session_state.active_company if st.session_state.active_company != "ВСИЧКИ" else "REN")

    st.divider()

    # --- 3. СПИСЪК С ОБЯВИ ---
    col_search, col_toggle = st.columns([3, 1])
    with col_search: search_term = st.text_input("🔍 Търсене на обява...")
    with col_toggle: show_archived = st.toggle("Покажи архивирани", value=False)

    query = supabase.table("hr_positions").select("*").eq("is_deleted", False)
    if st.session_state.active_company != "ВСИЧКИ":
        query = query.eq("company_name", st.session_state.active_company)
    if not show_archived:
        query = query.eq("status", "Активна")
        
    positions = query.execute().data

    if not positions:
        st.info(f"Няма активни обяви.")
        st.stop()

    if search_term:
        positions = [p for p in positions if search_term.lower() in p.get('title', '').lower() or search_term.lower() in p.get('city', '').lower()]

    def get_prio_icon(prio):
        if prio == "Спешен": return "🔥"
        if prio == "Висок": return "⚡"
        return "🟢"

    pos_options = {p['id']: f"{get_prio_icon(p.get('priority', 'Нормален'))} {p['title']} | {p.get('city', 'София')} ({p.get('base_location', '-')}) | EUR {p.get('salary_min', '0')} - {p.get('salary_max', '0')}" for p in positions}
    
    if not pos_options:
        st.warning("Няма обяви по този филтър.")
        st.stop()

    current_pos_id = st.session_state.active_campaign_id
    start_index = list(pos_options.keys()).index(current_pos_id) if current_pos_id in pos_options else 0

    selected_pos_id = st.selectbox("📂 Изберете обява:", options=list(pos_options.keys()), format_func=lambda x: pos_options[x], index=start_index)

    if selected_pos_id != st.session_state.active_campaign_id:
        st.session_state.active_campaign_id = selected_pos_id
        st.rerun()

    selected_pos_data = next((p for p in positions if p['id'] == selected_pos_id), None)

    if st.button("⚙️ Редакция на параметри", use_container_width=True):
        edit_position_modal(selected_pos_data)
            
    st.divider()

    # --- 4. ЪПЛОУД НА КАНДИДАТИ ---
    if check_permission("recruitment", "manage_positions"):
        with st.expander("📥 Добави нови кандидати (Upload)", expanded=False):
            uploaded_files = st.file_uploader("Качете ZIP (Jobs.bg), CSV или XLSX файлове", accept_multiple_files=True, type=['zip', 'csv', 'xlsx'])
            
            if uploaded_files and st.button("🚀 Обработи и запиши", type="primary"):
                with st.spinner("Парсване и запис в базата..."):
                    success_count = 0
                    for file in uploaded_files:
                        extracted_cands = []
                        if file.name.lower().endswith('.zip'): extracted_cands = [parse_jobs_zip(file)]
                        elif file.name.lower().endswith(('.csv', '.xlsx')): extracted_cands = parse_spreadsheet(file)
                        
                        for cand in extracted_cands:
                            name, cv_data, photo = cand
                            cand_insert = supabase.table("hr_candidates").insert({
                                "full_name": name,
                                "source": "Uploaded",
                                "raw_cv_data": cv_data,
                                "photo_thumbnail": photo
                            }).execute()
                            
                            if cand_insert.data:
                                cand_id = cand_insert.data[0]['id']
                                supabase.table("hr_applications").insert({
                                    "candidate_id": cand_id,
                                    "position_id": selected_pos_id,
                                    "status": "Нов",
                                    "is_deleted": False,
                                    "interview_details": {}
                                }).execute()
                                success_count += 1
                                
                st.success(f"Успешно добавени {success_count} кандидати към обявата!")
                st.rerun()
                
    st.divider()

    # --- 5. КАНБАН ДЪСКА (ЕТАП 3) ---
    st.markdown(f"### 👥 Фуния на подбора (Kanban)")

    apps_query = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("position_id", selected_pos_id).eq("is_deleted", False)
    applications = apps_query.execute().data

    if not applications:
        st.info("Няма кандидати по тази обява. Използвайте менюто за Upload по-горе.")
    else:
        active_statuses = ["Нов", "Установи контакт", "Възможно интервю", "Избран за интервю", "Потвърдено интервю", "Направено предложение"]
        inactive_statuses = ["Отхвърлен", "Отказал", "Преместен"]
        
        # 5.1 АКТИВНИ КОЛОНИ
        cols = st.columns(len(active_statuses))
        for i, status in enumerate(active_statuses):
            with cols[i]:
                # Стилизирано заглавие на колоната
                st.markdown(f"<div style='text-align: center; font-size: 14px; font-weight: bold; padding: 5px; background-color: #2e303e; border-radius: 5px; margin-bottom: 10px;'>{status}</div>", unsafe_allow_html=True)
                
                status_apps = [app for app in applications if app.get('status') == status]
                for app in status_apps:
                    cand = app.get("hr_candidates", {})
                    full_name = cand.get('full_name', 'Неизвестен кандидат')
                    
                    # Бутон-картичка
                    if st.button(f"👤 {full_name}", key=f"kanban_btn_{app['id']}", use_container_width=True):
                        candidate_card_modal(cand, app, selected_pos_data)

        st.write("<br>", unsafe_allow_html=True)
        
        # 5.2 АРХИВИРАНИ КАНДИДАТИ (Сгъваем панел)
        inactive_apps = [app for app in applications if app.get('status') in inactive_statuses]
        if inactive_apps:
            with st.expander(f"🗄️ Архивирани / Приключени кандидати ({len(inactive_apps)})"):
                in_cols = st.columns(3)
                for i, i_status in enumerate(inactive_statuses):
                    with in_cols[i]:
                        st.markdown(f"**{i_status}**")
                        i_status_apps = [app for app in inactive_apps if app.get('status') == i_status]
                        for app in i_status_apps:
                            cand = app.get("hr_candidates", {})
                            full_name = cand.get('full_name', 'Неизвестен')
                            
                            if st.button(f"👤 {full_name}", key=f"kanban_in_btn_{app['id']}", use_container_width=True):
                                candidate_card_modal(cand, app, selected_pos_data)
