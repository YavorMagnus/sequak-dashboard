import streamlit as st
import pandas as pd
from datetime import datetime
from utils import supabase, check_permission

# -----------------------------------------------------------------------------
# 1. МОДАЛ ЗА РЕДАКЦИЯ НА ОБЯВА
# -----------------------------------------------------------------------------
@st.dialog("Редакция на обява", width="large")
def edit_position_modal(pos_data):
    if not check_permission("recruitment", "manage_positions"):
        st.error("Нямате права за редакция на обяви. Обърнете се към администратор.")
        return

    st.markdown(f"### ⚙️ {pos_data.get('title', 'Неизвестна обява')}")
    
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
            current_priority = pos_data.get('priority', 'Нормален')
            prio_index = priority_options.index(current_priority) if current_priority in priority_options else 0
            new_priority = st.selectbox("Приоритет", priority_options, index=prio_index)
            
            status_options = ["Активна", "Архивирана (Изтекла)"]
            current_status = pos_data.get('status', 'Активна')
            status_index = status_options.index(current_status) if current_status in status_options else 0
            new_status = st.selectbox("Статус на обявата", status_options, index=status_index)

        st.divider()
        submit_btn = st.form_submit_button("💾 Запази промените", type="primary")
        
        if submit_btn:
            update_data = {
                "title": new_title,
                "city": new_city,
                "base_location": new_base,
                "salary_min": new_salary_min,
                "salary_max": new_salary_max,
                "priority": new_priority,
                "status": new_status
            }
            response = supabase.table("hr_positions").update(update_data).eq("id", pos_data['id']).execute()
            if response.data:
                st.success("Промените са записани успешно! Презареждане...")
                st.rerun()
            else:
                st.error("Грешка при запис в базата данни.")

# -----------------------------------------------------------------------------
# 2. КАРТОН НА КАНДИДАТА (Подготовка за Етап 2)
# -----------------------------------------------------------------------------
@st.dialog("Картон на кандидата", width="large")
def candidate_card_modal(candidate, app_data, pos_data=None):
    full_name = candidate.get('full_name', 'Неизвестен кандидат')
    cv_data = candidate.get('raw_cv_data') or {}
    int_details = app_data.get('interview_details') or {}
    
    # ГОРНА ЧАСТ
    st.markdown(f"## 👤 {full_name}")
    st.caption(f"📧 Имейл: {cv_data.get('email', 'Няма')} | 📱 Телефон: {cv_data.get('phone', 'Няма')}")
    st.divider()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### Оценка и Въпросник")
        if check_permission("recruitment", "evaluate"):
            with st.form(key=f"form_eval_{candidate.get('id', 'new')}"):
                new_notes = st.text_area("Бележки от интервю / Резултати от въпросник", value=int_details.get('notes', ''), height=200)
                submit_eval = st.form_submit_button("💾 Запази бележките", type="primary")
                if submit_eval:
                    int_details['notes'] = new_notes
                    supabase.table("hr_applications").update({"interview_details": int_details}).eq("id", app_data['id']).execute()
                    st.success("Бележките са запазени!")
                    st.rerun()
        else:
            st.info("Нямате права за редакция на оценки. Режим на четене.")
            st.write(int_details.get('notes', 'Няма въведени бележки или въпросник.'))

    with col2:
        st.markdown("### Операции")
        current_status = app_data.get('status', 'Нов')
        status_options = ["Нов", "Установи контакт", "Възможно интервю", "Избран за интервю", "Потвърдено интервю", "Направено предложение", "Отхвърлен", "Отказал", "Преместен"]
        prio_index = status_options.index(current_status) if current_status in status_options else 0
        new_status = st.selectbox("Текущ статус", status_options, index=prio_index)
        
        if new_status != current_status:
            if st.button(f"🔄 Потвърди нов статус", use_container_width=True):
                supabase.table("hr_applications").update({"status": new_status}).eq("id", app_data['id']).execute()
                st.success(f"Статусът е променен на {new_status}")
                st.rerun()

        st.divider()
        if check_permission("recruitment", "schedule"):
            st.markdown("#### 📅 Насрочване")
            with st.form(key=f"form_schedule_{candidate.get('id', 'new')}"):
                exist_date = int_details.get('interview_date')
                exist_time = int_details.get('interview_time')
                exist_interviewer = int_details.get('interviewer_name', '')
                
                parsed_date = datetime.strptime(exist_date, "%Y-%m-%d").date() if exist_date else None
                parsed_time = datetime.strptime(exist_time, "%H:%M:%S").time() if exist_time else None

                int_date = st.date_input("Дата на интервю", value=parsed_date)
                int_time = st.time_input("Час", value=parsed_time)
                interviewer = st.text_input("Интервюиращ", value=exist_interviewer)
                
                submit_schedule = st.form_submit_button("Запази интервю", use_container_width=True)
                if submit_schedule:
                    int_details['interview_date'] = int_date.strftime("%Y-%m-%d") if int_date else None
                    int_details['interview_time'] = int_time.strftime("%H:%M:%S") if int_time else None
                    int_details['interviewer_name'] = interviewer
                    supabase.table("hr_applications").update({"interview_details": int_details}).eq("id", app_data['id']).execute()
                    st.success("Интервюто е насрочено успешно!")
                    st.rerun()
                    
    # ДОЛНА ИНФО ЛЕНТА
    if pos_data:
        st.divider()
        st.info(f"📍 **Кандидатства за:** {pos_data.get('title', '')} | **Локация:** {pos_data.get('city', '')} ({pos_data.get('base_location', '-')}) | **Заплата:** EUR {pos_data.get('salary_min', '0')} - {pos_data.get('salary_max', '0')}")

# -----------------------------------------------------------------------------
# 3. СЪЗДАВАНЕ НА НОВА ОБЯВА
# -----------------------------------------------------------------------------
@st.dialog("Създаване на нова обява", width="large")
def create_position_modal(preselected_company):
    if not check_permission("recruitment", "manage_positions"):
        st.error("Нямате права за създаване на обяви.")
        return

    # Вземаме всички потребители за падащите менюта
    users_data = supabase.table("users").select("username").execute().data
    all_usernames = [u['username'] for u in users_data] if users_data else []

    with st.form(key="form_create_pos"):
        companies = ["REN", "CIM", "MAS", "BAU", "AST", "RXS", "RXB", "SNW", "DXM", "ICM"]
        comp_index = companies.index(preselected_company) if preselected_company in companies else 0
        
        col_hdr1, col_hdr2 = st.columns([1, 3])
        with col_hdr1:
            selected_comp = st.selectbox("Фирма *", companies, index=comp_index)
        with col_hdr2:
            new_title = st.text_input("Име на позицията *")
        
        st.markdown("👥 **Роли по обявата (за Action Center)**")
        col_roles1, col_roles2 = st.columns(2)
        with col_roles1:
            owners_list = st.multiselect("Собственици (Мениджъри)", options=all_usernames)
        with col_roles2:
            hr_contact = st.selectbox("HR (Установяващ контакт)", options=[""] + all_usernames)
            
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
        submit_btn = st.form_submit_button("➕ Създай обява", type="primary")
        
        if submit_btn:
            if not new_title:
                st.error("Името на позицията е задължително!")
            elif not owners_list:
                st.error("Трябва да изберете поне един Собственик (Мениджър)!")
            else:
                insert_data = {
                    "company_name": selected_comp,
                    "title": new_title,
                    "city": new_city,
                    "base_location": new_base,
                    "salary_min": new_salary_min,
                    "salary_max": new_salary_max,
                    "priority": priority,
                    "status": "Активна",
                    "is_deleted": False,
                    "owners": owners_list,
                    "hr_contact": hr_contact,
                    "work_type": work_type,
                    "evaluation_method": eval_method
                }
                response = supabase.table("hr_positions").insert(insert_data).execute()
                
                if response.data:
                    st.success("Новата обява е създадена успешно! Презареждане...")
                    st.session_state.active_campaign_id = response.data[0]['id']
                    st.session_state.active_company = selected_comp
                    st.rerun()
                else:
                    st.error("Грешка при запис в базата данни.")
