import streamlit as st
from datetime import datetime
import pandas as pd
from utils import supabase
from recruitment_modals import candidate_card_modal

# Речници за превод на дните и месеците на български
BG_DAYS = {0: "Понеделник", 1: "Вторник", 2: "Сряда", 3: "Четвъртък", 4: "Петък", 5: "Събота", 6: "Неделя"}
BG_MONTHS = {1: "Януари", 2: "Февруари", 3: "Март", 4: "Април", 5: "Май", 6: "Юни", 7: "Юли", 8: "Август", 9: "Септември", 10: "Октомври", 11: "Ноември", 12: "Декември"}

def format_bg_date(date_obj):
    day_name = BG_DAYS[date_obj.weekday()]
    month_name = BG_MONTHS[date_obj.month]
    return f"{day_name}, {date_obj.day} {month_name} {date_obj.year}"

@st.dialog("📅 График за интервюта", width="large")
def render_interview_calendar():
    st.markdown("### Мениджърски график")
    
    # 1. Извличане на всички кандидатури от базата (които не са изтрити)
    res = supabase.table("hr_applications").select("*, hr_candidates(*), hr_positions(*)").eq("is_deleted", False).execute()
    apps = res.data if res.data else []

    # 2. Филтриране само на тези, които имат насрочена дата за интервю
    scheduled_apps = []
    interviewers = set()
    
    for app in apps:
        int_details = app.get('interview_details') or {}
        i_date = int_details.get('interview_date')
        i_time = int_details.get('interview_time')
        i_name = int_details.get('interviewer_name')
        
        if i_date:
            try:
                # Превръщаме текста "YYYY-MM-DD" в истински Python Date обект
                d_obj = datetime.strptime(i_date, "%Y-%m-%d").date()
                if i_name: interviewers.add(i_name)
                scheduled_apps.append({
                    'app': app,
                    'date_obj': d_obj,
                    'time_str': i_time or "00:00",
                    'interviewer': i_name or "Непосочен",
                })
            except:
                pass # Игнорираме грешни формати на дати

    if not scheduled_apps:
        st.info("ℹ️ В момента няма насрочени интервюта в системата.")
        return

    # 3. ФИЛТРИ (Горе в модала)
    col_f1, col_f2 = st.columns([2, 1])
    
    with col_f1:
        all_interviewers = ["Всички"] + sorted(list(interviewers))
        # Опитваме се да преселектираме автоматично текущия логнат потребител
        curr_user = st.session_state.get('username')
        def_idx = all_interviewers.index(curr_user) if curr_user in all_interviewers else 0
        sel_interviewer = st.pills("👤 Интервюиращ:", all_interviewers, default=all_interviewers[def_idx], selection_mode="single")
        if not sel_interviewer: sel_interviewer = "Всички"
        
    with col_f2:
        sel_period = st.pills("⏳ Период:", ["Предстоящи", "Минали"], default="Предстоящи", selection_mode="single")
        if not sel_period: sel_period = "Предстоящи"

    # 4. ПРИЛАГАНЕ НА ФИЛТРИТЕ
    today = datetime.now().date()
    filtered_apps = []
    
    for item in scheduled_apps:
        # Филтър по човек
        if sel_interviewer != "Всички" and item['interviewer'] != sel_interviewer:
            continue
        
        # Филтър по период
        is_upcoming = item['date_obj'] >= today
        if sel_period == "Предстоящи" and not is_upcoming: continue
        if sel_period == "Минали" and is_upcoming: continue
        
        filtered_apps.append(item)

    # 5. СОРТИРАНЕ НА СПИСЪКА
    if sel_period == "Предстоящи":
        # За предстоящи: от днес напред (възходящ ред)
        filtered_apps.sort(key=lambda x: (x['date_obj'], x['time_str']))
    else:
        # За минали: от вчера назад (низходящ ред)
        filtered_apps.sort(key=lambda x: (x['date_obj'], x['time_str']), reverse=True)

    if not filtered_apps:
        st.info(f"Няма {sel_period.lower()} интервюта за този избор.")
        return

    # 6. ГРУПИРАНЕ ПО ДНИ И ЧЕРТАЕНЕ НА ВРЕМЕВАТА ЛИНИЯ (Timeline)
    st.divider()
    
    grouped_apps = {}
    for item in filtered_apps:
        d_str = format_bg_date(item['date_obj'])
        if d_str not in grouped_apps:
            grouped_apps[d_str] = []
        grouped_apps[d_str].append(item)

    # CSS за красива времева линия вътре в модала
    st.markdown("""
    <style>
    .timeline-date { color: #ffb400; font-size: 1.2rem; font-weight: bold; margin-top: 20px; margin-bottom: 10px; border-bottom: 2px solid #333; padding-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

    for d_str, items in grouped_apps.items():
        st.markdown(f"<div class='timeline-date'>📅 {d_str}</div>", unsafe_allow_html=True)
        
        for item in items:
            app = item['app']
            cand = app.get('hr_candidates', {})
            pos = app.get('hr_positions', {})
            
            c_name = cand.get('full_name', 'Неизвестен')
            p_title = pos.get('title', 'Неизвестна обява')
            p_comp = pos.get('company_name', '')
            time_str = item['time_str']
            
            # Използваме колони за всеки ред от графика
            with st.container(border=True):
                r1, r2, r3 = st.columns([1, 4, 1], vertical_alignment="center")
                with r1:
                    st.markdown(f"<span style='color: #00aaff; font-size: 1.3rem; font-weight: bold;'>{time_str}</span>", unsafe_allow_html=True)
                with r2:
                    st.markdown(f"**{c_name}**<br><span style='color: #aaaaaa; font-size: 0.9rem;'>{p_title} ({p_comp})</span>", unsafe_allow_html=True)
                with r3:
                    if st.button("📂 Отвори", key=f"cal_btn_{app['id']}", use_container_width=True):
                        candidate_card_modal(cand, app, pos)
