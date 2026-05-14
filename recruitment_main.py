import streamlit as st
import pandas as pd
from utils import supabase, check_permission
from recruitment_modals import edit_position_modal, candidate_card_modal, create_position_modal

def run_recruitment():
    st.title("🎯 Подбор на персонал (Recruitment)")
    
    # -------------------------------------------------------------------------
    # 1. ИНИЦИАЛИЗАЦИЯ НА СЕСИЯТА
    # -------------------------------------------------------------------------
    if "active_company" not in st.session_state:
        st.session_state.active_company = "REN" 
    if "active_campaign_id" not in st.session_state:
        st.session_state.active_campaign_id = None
    if "active_status_filter" not in st.session_state:
        st.session_state.active_status_filter = "Всички"
    if "deep_link_triggered" not in st.session_state:
        st.session_state.deep_link_triggered = False

    # -------------------------------------------------------------------------
    # 2. ПРОЦЕС 1: ВЪНШЕН DEEP LINK
    # -------------------------------------------------------------------------
    query_params = st.query_params
    if "app_id" in query_params and not st.session_state.deep_link_triggered:
        target_app_id = query_params["app_id"]
        target_app = supabase.table("hr_applications").select("*, hr_candidates(*), hr_positions(*)").eq("id", target_app_id).execute()
        
        if target_app.data:
            app_data = target_app.data[0]
            pos_data = app_data.get("hr_positions", {})
            candidate_data = app_data.get("hr_candidates", {})
            if pos_data:
                st.session_state.active_company = pos_data.get("company_name", "REN")
                st.session_state.active_campaign_id = pos_data.get("id")
            st.session_state.deep_link_triggered = True
            candidate_card_modal(candidate_data, app_data)

    # -------------------------------------------------------------------------
    # 3. ИЗБОР НА ФИРМА И НОВА КАМПАНИЯ
    # -------------------------------------------------------------------------
    # ТОЧНИТЕ 10 ФИРМИ
    companies = ["REN", "CIM", "MAS", "BAU", "AST", "RXS", "RXB", "SNW", "DXM", "ICM"]
    col_comp, col_new = st.columns([3, 1])
    
    with col_comp:
        current_index = companies.index(st.session_state.active_company) if st.session_state.active_company in companies else 0
        selected_company = st.selectbox("🏢 Изберете фирма:", options=companies, index=current_index)
    
    with col_new:
        st.write("<br>", unsafe_allow_html=True)
        if st.button("➕ Нова кампания", use_container_width=True, type="primary"):
            create_position_modal(selected_company)

    if selected_company != st.session_state.active_company:
        st.session_state.active_company = selected_company
        st.session_state.active_campaign_id = None
        st.session_state.active_status_filter = "Всички"
        st.rerun()

    st.divider()

    # -------------------------------------------------------------------------
    # 4. СПИСЪК С КАМПАНИИ
    # -------------------------------------------------------------------------
    col_search, col_toggle = st.columns([3, 1])
    with col_search:
        search_term = st.text_input("🔍 Търсене на кампания...")
    with col_toggle:
        show_archived = st.toggle("Покажи архивирани", value=False)

    query = supabase.table("hr_positions").select("*").eq("company_name", st.session_state.active_company)
    if not show_archived:
        query = query.eq("is_active", True)
    positions = query.execute().data

    if not positions:
        st.info(f"Няма активни кампании за {st.session_state.active_company}.")
        st.stop()

    if search_term:
        positions = [p for p in positions if search_term.lower() in p.get('title', '').lower() or search_term.lower() in p.get('city', '').lower()]

    # Функция за визуално показване на "Пожарите"
    def get_prio_icon(prio):
        if prio == "Спешен": return "🔥"
        if prio == "Висок": return "⚡"
        return "🟢"

    pos_options = {p['id']: f"{get_prio_icon(p.get('priority', 'Нормален'))} {p['title']} ({p.get('city', 'София')})" for p in positions}
    
    if not pos_options:
        st.warning("Няма кампании по този филтър.")
        st.stop()

    current_pos_id = st.session_state.active_campaign_id
    start_index = list(pos_options.keys()).index(current_pos_id) if current_pos_id in pos_options else 0

    selected_pos_id = st.selectbox("📂 Изберете кампания:", options=list(pos_options.keys()), format_func=lambda x: pos_options[x], index=start_index)

    if selected_pos_id != st.session_state.active_campaign_id:
        st.session_state.active_campaign_id = selected_pos_id
        st.rerun()

    selected_pos_data = next((p for p in positions if p['id'] == selected_pos_id), None)

    if st.button("⚙️ Редакция на параметри", use_container_width=True):
        edit_position_modal(selected_pos_data)
            
    st.divider()

    # -------------------------------------------------------------------------
    # 5. КАНДИДАТИ
    # -------------------------------------------------------------------------
    st.markdown(f"### 👥 Кандидати: {selected_pos_data.get('title', '')}")
    all_statuses = ["Всички", "Нов", "Установи контакт", "Възможно интервю", "Избран за интервю", "Потвърдено интервю", "Направено предложение", "Отхвърлен", "Отказал", "Преместен"]

    status_index = all_statuses.index(st.session_state.active_status_filter) if st.session_state.active_status_filter in all_statuses else 0
    selected_status = st.selectbox("📌 Филтър по статус:", options=all_statuses, index=status_index)

    if selected_status != st.session_state.active_status_filter:
        st.session_state.active_status_filter = selected_status
        st.rerun()

    apps_query = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("position_id", selected_pos_id)
    if st.session_state.active_status_filter != "Всички":
        apps_query = apps_query.eq("status", st.session_state.active_status_filter)
    applications = apps_query.execute().data

    if not applications:
        st.info("Няма кандидати с този статус.")
    else:
        for app in applications:
            cand = app.get("hr_candidates", {})
            btn_label = f"👤 {cand.get('first_name', '')} {cand.get('last_name', '')} | {app.get('status', 'Нов')}"
            if st.button(btn_label, key=f"btn_cand_{app['id']}", use_container_width=True):
                candidate_card_modal(cand, app)
