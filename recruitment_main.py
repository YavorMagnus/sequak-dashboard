import streamlit as st
import pandas as pd
from utils import supabase, check_permission
from recruitment_modals import edit_position_modal, candidate_card_modal, create_position_modal
# ИМПОРТ САМО НА СТАРИТЕ, РАБОТЕЩИ ПАРСЪРИ
from parsers import parse_jobs_zip, parse_spreadsheet
# Импорт на модула за календара
from recruitment_calendar import render_interview_calendar

# ДЕФИНИРАНЕ НА CSS ЗА КАНБАН ДЪСКАТА И БУТОНИТЕ
KANBAN_CSS = """
<style>
/* Заглавия на Канбан колоните */
.kanban-header {
    text-align: center;
    font-size: 14px;
    font-weight: bold;
    padding: 8px;
    background-color: #2e303e;
    border-radius: 8px 8px 0 0;
    margin-bottom: 0px;
    border-bottom: 2px solid #5a5e71;
}

/* Стилизиране на бутоните като квадратни картички */
.stButton > button {
    height: 100px;
    width: 100% !important;
    border-radius: 8px;
    background-color: #1a1c24;
    border: 1px solid #3d4151;
    color: white;
    padding: 10px;
    transition: all 0.3s ease;
    margin-bottom: 8px;
}

.stButton > button:hover {
    border-color: #ffb400 !important;
    background-color: #2e303e;
}

/* Стилизиране на името на кандидата */
.kanban-cand-name {
    font-weight: bold;
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    display: block;
    width: 100%;
}

/* Стилизиране на иконката */
.kanban-cand-icon {
    font-size: 18px;
    margin-right: 5px;
}

/* Стилизиране на ЗЛАТНАТА РАМКА за Резерва */
div[data-is-reserve="true"] button {
    border: 2px solid #ffb400 !important;
}

/* Заглавие на секцията за Архивирани */
.inactive-header {
    margin-top: 15px;
    margin-bottom: 5px;
    font-weight: bold;
}

/* === УГОЛЕМЯВАНЕ НА PILLS (ФИЛТРИТЕ) === */
div[data-testid="stPills"] label {
    padding: 10px 20px !important;
    font-size: 16px !important;
    min-height: 45px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
div[data-testid="stPills"] {
    gap: 12px;
}
</style>
"""

def run_recruitment():
    st.markdown(KANBAN_CSS, unsafe_allow_html=True)
    
    # Заглавието и бутонът за Календара са разположени в две колони
    col_title, col_cal = st.columns([4, 1])
    with col_title:
        st.title("🎯 Подбор на персонал (Recruitment)")
    with col_cal:
        st.write("<br>", unsafe_allow_html=True)
        if st.button("📅 График интервюта", type="primary", use_container_width=True):
            render_interview_calendar()
    
    # --- ИНИЦИАЛИЗАЦИЯ НА СЕСИЯТА ---
    if "active_company" not in st.session_state:
        st.session_state.active_company = "ВСИЧКИ" 
    if "prev_company" not in st.session_state:
        st.session_state.prev_company = "ВСИЧКИ"
    if "active_campaign_id" not in st.session_state:
        st.session_state.active_campaign_id = None
    if "deep_link_triggered" not in st.session_state:
        st.session_state.deep_link_triggered = False
    if "pending_candidate_card" not in st.session_state:
        st.session_state.pending_candidate_card = None

    # --- 0. ЩАФЕТА ОТ КАЛЕНДАРА (RELAY CATCHER) ---
    if st.session_state.pending_candidate_card:
        p_data = st.session_state.pending_candidate_card
        st.session_state.pending_candidate_card = None  # Изчистваме веднага
        candidate_card_modal(p_data["candidate"], p_data["app_data"], p_data["pos_data"])

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
        selected_company = st.pills("Изберете фирма:", companies, default=st.session_state.active_company, selection_mode="single")
        if not selected_company: 
            selected_company = "ВСИЧКИ"
            
        # ЛОГИКА ЗА ИЗЧИСТВАНЕ ПРИ СМЯНА НА ФИРМАТА
        if selected_company != st.session_state.prev_company:
            st.session_state.active_company = selected_company
            st.session_state.prev_company = selected_company
            st.session_state.active_campaign_id = None # Изчистваме фокуса
            st.rerun()
            
    with col_new:
        st.write("<br>", unsafe_allow_html=True)
        if st.button("➕ Нова обява", type="secondary", use_container_width=True):
            create_position_modal(st.session_state.active_company if st.session_state.active_company != "ВСИЧКИ" else "REN")

    st.divider()

    # --- 3. ИЗВЛИЧАНЕ И ФИЛТРИРАНЕ НА БАЗАТА С ОБЯВИ ---
    query = supabase.table("hr_positions").select("*")
    if st.session_state.active_company != "ВСИЧКИ":
        query = query.eq("company_name", st.session_state.active_company)
        
    all_positions = query.execute().data

    if not all_positions:
        st.info(f"Няма регистрирани обяви за тази фирма.")
        st.stop()

    if st.session_state.active_campaign_id is None:
        # ---------------------------------------------------------------------
        # РЕЖИМ А: DASHBOARD (СПИСЪК С ВСИЧКИ ОБЯВИ)
        # ---------------------------------------------------------------------
        col_search, col_archived, col_trash, col_sort = st.columns([2, 1, 1, 2])
        
        with col_search: 
            search_term = st.text_input("🔍 Търсене на обява...")
        with col_archived: 
            st.write("<br>", unsafe_allow_html=True)
            show_archived = st.toggle("Архивирани", value=False)
        with col_trash:
            st.write("<br>", unsafe_allow_html=True)
            show_trash = False
            if st.session_state.get("user_role") in ["Супер-админ", "Администратор"]:
                show_trash = st.toggle("🗑️ Кошче", value=False)
        with col_sort:
            st.write("<br>", unsafe_allow_html=True)
            sort_order = st.radio("Подреждане:", ["Най-нови отгоре", "По приоритет"], horizontal=True, label_visibility="collapsed")

        # Филтриране по статус и кошче
        if show_trash:
            filtered_positions = [p for p in all_positions if p.get('is_deleted', False)]
        else:
            filtered_positions = [p for p in all_positions if not p.get('is_deleted', False)]
            if not show_archived:
                filtered_positions = [p for p in filtered_positions if p.get('status') == "Активна"]

        # Търсене по текст
        if search_term:
            filtered_positions = [p for p in filtered_positions if search_term.lower() in p.get('title', '').lower() or search_term.lower() in p.get('city', '').lower()]

        if not filtered_positions:
            st.warning("Няма обяви, отговарящи на избраните филтри.")
            st.stop()

        # ЛОГИКА ЗА СОРТИРАНЕ НА СПИСЪКА
        def get_prio_weight(prio_str):
            if prio_str == "Спешен": return 3
            if prio_str == "Висок": return 2
            return 1

        if sort_order == "По приоритет":
            filtered_positions.sort(key=lambda x: get_prio_weight(x.get('priority', 'Нормален')), reverse=True)
        else:
            filtered_positions.sort(key=lambda x: str(x.get('id', '')), reverse=True)

        st.markdown("### 📋 Списък с обяви")
        
        for pos in filtered_positions:
            with st.container(border=True):
                c_info, c_btn = st.columns([4, 1], vertical_alignment="center")
                
                with c_info:
                    p_icon = "🗑️" if pos.get('is_deleted', False) else ("🔥" if pos.get('priority') == "Спешен" else ("⚡" if pos.get('priority') == "Висок" else "🟢"))
                    st.markdown(f"**{p_icon} {pos.get('title', 'Неизвестна')}** | {pos.get('company_name', '')}")
                    st.caption(f"📍 {pos.get('city', 'София')} | 💶 EUR {pos.get('salary_min', '0')} - {pos.get('salary_max', '0')} | Статус: {pos.get('status', 'Неизвестен')}")
                    
                with c_btn:
                    if st.button("📂 Влез в обявата", key=f"open_pos_{pos['id']}", use_container_width=True, type="primary"):
                        st.session_state.active_campaign_id = pos['id']
                        st.rerun()

    else:
        # ---------------------------------------------------------------------
        # РЕЖИМ Б: ДЕТАЙЛЕН ИЗГЛЕД НА КОНКРЕТНА ОБЯВА
        # ---------------------------------------------------------------------
        selected_pos_data = next((p for p in all_positions if p['id'] == st.session_state.active_campaign_id), None)
        
        if not selected_pos_data:
            st.session_state.active_campaign_id = None
            st.rerun()

        if st.button("⬅️ Назад към всички обяви", type="secondary"):
            st.session_state.active_campaign_id = None
            st.rerun()
            
        st.write("<br>", unsafe_allow_html=True)

        p_icon = "🗑️" if selected_pos_data.get('is_deleted', False) else ("🔥" if selected_pos_data.get('priority') == "Спешен" else ("⚡" if selected_pos_data.get('priority') == "Висок" else "🟢"))
        st.info(f"**АКТИВНА ОБЯВА:** {p_icon} {selected_pos_data.get('title', 'Неизвестна')} | 📍 {selected_pos_data.get('city', 'София')} | {selected_pos_data.get('company_name', '')}")

        if st.button("⚙️ Редакция и Управление на обявата", use_container_width=True):
            edit_position_modal(selected_pos_data)
                
        st.divider()

        # --- 4. ЪПЛОУД НА КАНДИДАТИ ---
        if check_permission("recruitment", "upload_candidates") and not selected_pos_data.get('is_deleted', False):
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
                                        "position_id": st.session_state.active_campaign_id,
                                        "status": "Нов",
                                        "is_deleted": False,
                                        "interview_details": {}
                                    }).execute()
                                    success_count += 1
                                    
                    st.success(f"Успешно добавени {success_count} кандидати към обявата!")
                    st.rerun()
                    
        st.divider()

        # --- 5. ГАЛЕРИЯ НА КАНДИДАТИТЕ ---
        st.markdown(f"### 👥 Кандидати (Галерия)")

        apps_query = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("position_id", st.session_state.active_campaign_id).eq("is_deleted", False)
        applications = apps_query.execute().data

        if not applications:
            st.info("Няма кандидати по тази обява. Използвайте менюто за Upload по-горе.")
        else:
            base_statuses = ["Нов", "Установи контакт", "Възможно интервю", "Избран за интервю", "Потвърдено интервю", "Направено предложение", "Отхвърлен", "Отказал", "Преместен"]
            status_counts = {"Всички": len(applications)}
            
            for s in base_statuses:
                status_counts[s] = sum(1 for app in applications if app.get('status') == s)
                
            pill_options = [f"Всички ({status_counts['Всички']})"] + [f"{s} ({status_counts[s]})" for s in base_statuses]
            
            if "gallery_base_status" not in st.session_state:
                st.session_state.gallery_base_status = "Всички"
                
            default_pill = next((p for p in pill_options if p.startswith(st.session_state.gallery_base_status + " (")), pill_options[0])
            
            selected_pill = st.pills("Филтър по статус:", pill_options, default=default_pill, selection_mode="single")
            
            if selected_pill:
                st.session_state.gallery_base_status = selected_pill.rsplit(" (", 1)[0]
            else:
                selected_pill = default_pill
                
            active_status_name = selected_pill.rsplit(" (", 1)[0]
            
            if active_status_name == "Всички":
                filtered_apps = applications
            else:
                filtered_apps = [app for app in applications if app.get('status') == active_status_name]
                
            st.write("<br>", unsafe_allow_html=True)
            
            if not filtered_apps:
                st.info(f"Няма кандидати със статус '{active_status_name}'.")
            else:
                cols = st.columns(3)
                for i, app in enumerate(filtered_apps):
                    with cols[i % 3]:
                        cand = app.get("hr_candidates", {})
                        full_name = cand.get('full_name', 'Неизвестен')
                        
                        # НОВАТА ЛОГИКА: Четем is_backup директно от app
                        is_reserve = app.get('is_backup', False)
                        
                        manual_scores = app.get('manual_score') or {}
                        categories = ["Търговска", "Сервизна", "Строителна/архитектурна", "Юридическа", "IT", "Складова", "Счетоводно-административна", "Управленска"]
                        total_obj = sum(manual_scores.get(comp, 0) for comp in categories)
                        
                        # Слагаме златна рамка, ако е резерва
                        container_attr = {"data-is-reserve": "true"} if is_reserve else {}
                        
                        with st.container(border=True, **container_attr):
                            card_col1, card_col2 = st.columns([1, 3])
                            with card_col1:
                                if cand.get('photo_thumbnail'):
                                    st.image(f"data:image/png;base64,{cand['photo_thumbnail']}", use_container_width=True)
                                else:
                                    st.markdown("<div style='font-size: 35px; text-align: center; color: gray;'>👤</div>", unsafe_allow_html=True)
                            with card_col2:
                                reserve_icon = " <span style='color: #ffb400; font-weight: bold;'>❓</span>" if is_reserve else ""
                                st.markdown(f"**{full_name}**{reserve_icon}", unsafe_allow_html=True)
                                st.caption(f"Обективна: {total_obj}/48")
                                if active_status_name == "Всички":
                                    st.caption(f"Статус: {app.get('status')}")
                                
                            if st.button("📂 Отвори", key=f"gal_btn_{app['id']}", use_container_width=True):
                                candidate_card_modal(cand, app, selected_pos_data)
