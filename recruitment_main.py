import streamlit as st
import pandas as pd
from utils import supabase, check_permission
from recruitment_modals import edit_position_modal, candidate_card_modal, create_position_modal
# ИМПОРТ САМО НА СТАРИТЕ, РАБОТЕЩИ ПАРСЪРИ
from parsers import parse_jobs_zip, parse_spreadsheet
# НОВО: Импорт на модула за календара
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
    
    # ОБНОВЕНО: Заглавието и бутонът за Календара са разположени в две колони
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

    # --- 3. СПИСЪК С ОБЯВИ И КОШЧЕ ---
    col_search, col_toggle1, col_toggle2 = st.columns([2, 1, 1])
    with col_search: 
        search_term = st.text_input("🔍 Търсене на обява...")
    with col_toggle1: 
        show_archived = st.toggle("Архивирани", value=False)
    with col_toggle2:
        show_trash = False
        if st.session_state.get("user_role") in ["Супер-админ", "Администратор"]:
            show_trash = st.toggle("🗑️ Кошче", value=False)

    query = supabase.table("hr_positions").select("*")
    if st.session_state.active_company != "ВСИЧКИ":
        query = query.eq("company_name", st.session_state.active_company)
        
    if show_trash:
        query = query.eq("is_deleted", True)
    else:
        query = query.eq("is_deleted", False)
        if not show_archived:
            query = query.eq("status", "Активна")
        
    positions = query.execute().data

    if not positions:
        st.info(f"Няма обяви по зададените критерии.")
        st.stop()

    if search_term:
        positions = [p for p in positions if search_term.lower() in p.get('title', '').lower() or search_term.lower() in p.get('city', '').lower()]

    def get_prio_icon(prio, is_del):
        if is_del: return "🗑️"
        if prio == "Спешен": return "🔥"
        if prio == "Висок": return "⚡"
        return "🟢"

    pos_options = {p['id']: f"{get_prio_icon(p.get('priority', 'Нормален'), p.get('is_deleted', False))} {p['title']} | {p.get('city', 'София')} ({p.get('base_location', '-')}) | EUR {p.get('salary_min', '0')} - {p.get('salary_max', '0')}" for p in positions}
    
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
                                    "position_id": selected_pos_id,
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

    apps_query = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("position_id", selected_pos_id).eq("is_deleted", False)
    applications = apps_query.execute().data

    if not applications:
        st.info("Няма кандидати по тази обява. Използвайте менюто за Upload по-горе.")
    else:
        base_statuses = ["Нов", "Установи контакт", "Възможно интервю", "Избран за интервю", "Потвърдено интервю", "Направено предложение", "Отхвърлен", "Отказал", "Преместен"]
        status_counts = {"Всички": len(applications)}
        
        for s in base_statuses:
            status_counts[s] = sum(1 for app in applications if app.get('status') == s)
            
        pill_options = [f"Всички ({status_counts['Всички']})"] + [f"{s} ({status_counts[s]})" for s in base_statuses]
        
        # ЗАЩИТА СРЕЩУ СРИВ (Запомняме само базовата дума, без числата)
        if "gallery_base_status" not in st.session_state:
            st.session_state.gallery_base_status = "Всички"
            
        # Намираме актуалното хапче, което започва с тази базова дума
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
                    int_details = app.get('interview_details') or {}
                    manual_scores = app.get('manual_score') or {}
                    
                    is_reserve = int_details.get('reserve_checkbox', False)
                    total_score = sum(manual_scores.values()) if manual_scores else 0
                    
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
                            if active_status_name == "Всички":
                                st.caption(f"Статус: {app.get('status')}")
                            
                        if st.button("📂 Отвори", key=f"gal_btn_{app['id']}", use_container_width=True):
                            candidate_card_modal(cand, app, selected_pos_data)
