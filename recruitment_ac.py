import streamlit as st
from utils import supabase

def render_action_center():
    st.markdown("### 🔔 Action Center")
    
    curr_user = st.session_state.get('username')
    if not curr_user:
        st.info("Моля, влезте в системата.")
        return

    # Извличане на всички активни обяви и кандидатури
    pos_res = supabase.table("hr_positions").select("*").eq("is_deleted", False).eq("status", "Активна").execute()
    positions = {p['id']: p for p in pos_res.data} if pos_res.data else {}

    app_res = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("is_deleted", False).execute()
    applications = app_res.data if app_res.data else []

    # Речник за групиране на задачите по обява
    # Формат: { pos_id: {'title': str, 'company': str, 'tasks': {task_type: count}} }
    user_tasks = {}

    for app in applications:
        pos_id = app.get('position_id')
        if pos_id not in positions:
            continue # Обявата е изтрита или архивирана
            
        pos = positions[pos_id]
        status = app.get('status')
        int_details = app.get('interview_details') or {}
        
        owners = pos.get('owners') or []
        hr_contact = pos.get('hr_contact')
        
        is_owner = curr_user in owners
        is_hr = curr_user == hr_contact
        
        # Инициализация на броячите за тази обява
        if pos_id not in user_tasks:
            user_tasks[pos_id] = {
                'title': pos.get('title', 'Неизвестна'),
                'company': pos.get('company_name', ''),
                'tasks': {
                    'new': 0,
                    'contact': 0,
                    'possible_int': 0,
                    'schedule_int': 0,
                    'conduct_int': 0,
                    'offer': 0
                }
            }
            
        # ТРИГЕР 1: Нов (До Мениджъри и HR)
        if status == "Нов" and (is_owner or is_hr):
            user_tasks[pos_id]['tasks']['new'] += 1
            
        # ТРИГЕР 2: Установи контакт (До HR)
        elif status == "Установи контакт" and is_hr:
            user_tasks[pos_id]['tasks']['contact'] += 1
            
        # ТРИГЕР 3: Възможно интервю (До Мениджъри)
        elif status == "Възможно интервю" and is_owner:
            user_tasks[pos_id]['tasks']['possible_int'] += 1
            
        # ТРИГЕР 4: Избран за интервю (До HR)
        elif status == "Избран за интервю" and is_hr:
            user_tasks[pos_id]['tasks']['schedule_int'] += 1
            
        # ТРИГЕР 5: Потвърдено интервю (До Интервюиращ или Мениджъри)
        elif status == "Потвърдено интервю":
            interviewer = int_details.get('interviewer_name')
            if interviewer == curr_user or (not interviewer and is_owner):
                user_tasks[pos_id]['tasks']['conduct_int'] += 1
                
        # ТРИГЕР 6: Направено предложение (До HR, ако не е затворена офертата)
        elif status == "Направено предложение" and is_hr:
            if not int_details.get('offer_closed', False):
                user_tasks[pos_id]['tasks']['offer'] += 1

    # Филтриране на обявите, в които реално има задачи за текущия потребител
    active_tasks_count = 0
    
    st.markdown("""
    <style>
    .action-btn { margin-bottom: 5px !important; text-align: left !important; }
    </style>
    """, unsafe_allow_html=True)

    for pos_id, data in user_tasks.items():
        tasks = data['tasks']
        total_pos_tasks = sum(tasks.values())
        
        if total_pos_tasks > 0:
            active_tasks_count += total_pos_tasks
            st.markdown(f"**🎯 {data['title']} ({data['company']})**")
            
            # Helper функция за чертане на бутони (Deep Links)
            def draw_task_btn(label, count, icon, target_status):
                if count > 0:
                    if st.button(f"{icon} {count} {label}", key=f"act_{pos_id}_{icon}", use_container_width=True):
                        st.session_state.active_campaign_id = pos_id
                        st.session_state.active_company = data['company']
                        st.session_state.target_gallery_status = target_status # ТУК Е КУКИЧКАТА!
                        st.rerun()

            draw_task_btn("Нови кандидати", tasks['new'], "🔴", "Нов")
            draw_task_btn("За телефонен контакт", tasks['contact'], "📞", "Установи контакт")
            draw_task_btn("За преглед от мениджър", tasks['possible_int'], "💡", "Възможно интервю")
            draw_task_btn("За насрочване на интервю", tasks['schedule_int'], "📅", "Избран за интервю")
            draw_task_btn("Предстоящи интервюта", tasks['conduct_int'], "🏢", "Потвърдено интервю")
            draw_task_btn("Отворени предложения", tasks['offer'], "📝", "Направено предложение")
            
            st.divider()

    if active_tasks_count == 0:
        st.success("🎉 Нямате чакащи задачи в момента.")
