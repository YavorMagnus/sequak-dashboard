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

    # --- 2. ИЗБОР НА ФИРМА И НОВА ОБЯВА ---
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

    # --- 5. ГАЛЕРИЯ НА КАНДИДАТИТЕ (Новият Game Changer) ---
    st.markdown(f"### 👥 Кандидати (Галерия)")

    apps_query = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("position_id", selected_pos_id).eq("is_deleted", False)
    applications = apps_query.execute().data

    if not applications:
        st.info("Няма кандидати по тази обява. Използвайте менюто за Upload по-горе.")
    else:
        # 5.1 Подготовка на броячите
        base_statuses = ["Нов", "Установи контакт", "Възможно интервю", "Избран за интервю", "Потвърдено интервю", "Направено предложение", "Отхвърлен", "Отказал", "Преместен"]
        status_counts = {"Всички": len(applications)}
        
        for s in base_statuses:
            status_counts[s] = sum(1 for app in applications if app.get('status') == s)
            
        # 5.2 Генериране на етикетите с броячи (напр. "Нов (3)")
        pill_options = [f"Всички ({status_counts['Всички']})"] + [f"{s} ({status_counts[s]})" for s in base_statuses]
        
        if "gallery_filter" not in st.session_state:
            st.session_state.gallery_filter = pill_options[0]
            
        selected_pill = st.pills("Филтър по статус:", pill_options, default=st.session_state.gallery_filter, selection_mode="single")
        
        if not selected_pill:
            selected_pill = pill_options[0]
            
        st.session_state.gallery_filter = selected_pill
        
        # Извличане на чистото име на статуса (без бройката в скобите)
        active_status_name = selected_pill.rsplit(" (", 1)[0]
        
        # 5.3 Филтриране на картите
        if active_status_name == "Всички":
            filtered_apps = applications
        else:
            filtered_apps = [app for app in applications if app.get('status') == active_status_name]
            
        st.write("<br>", unsafe_allow_html=True)
        
        # 5.4 Визуализация на картите в мрежа (3 колони)
        if not filtered_apps:
            st.info(f"Няма кандидати със статус '{active_status_name}'.")
        else:
            cols = st.columns(3)
            for i, app in enumerate(filtered_apps):
                with cols[i % 3]:
                    cand = app.get("hr_candidates", {})
                    full_name = cand.get('full_name', 'Неизвестен')
                    int_details = app.get('interview_details') or {}
                    manual_scores = app.get('manual_score') or {}
                    
                    is_reserve = int_details.get('reserve_checkbox', False)
                    total_score = sum(manual_scores.values()) if manual_scores else 0
                    
                    # Самата карта
                    with st.container(border=True):
                        card_col1, card_col2 = st.columns([1, 3])
                        with card_col1:
                            if cand.get('photo_thumbnail'):
                                st.image(f"data:image/png;base64,{cand['photo_thumbnail']}", use_container_width=True)
                            else:
                                st.markdown("<div style='font-size: 35px; text-align: center; color: gray;'>👤</div>", unsafe_allow_html=True)
                        with card_col2:
                            reserve_icon = " <span style='color: #ffb400; font-weight: bold;'>❓</span>" if is_reserve else ""
                            st.markdown(f"**{full_name}**{reserve_icon}", unsafe_allow_html=True)
                            st.caption(f"Оценка: {total_score}/48")
                            # Показваме статуса в картата, само ако сме на таб "Всички" (иначе е излишно повторение)
                            if active_status_name == "Всички":
                                st.caption(f"Статус: {app.get('status')}")
                            
                        if st.button("📂 Отвори", key=f"gal_btn_{app['id']}", use_container_width=True):
                            candidate_card_modal(cand, app, selected_pos_data)
