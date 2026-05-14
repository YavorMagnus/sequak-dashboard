import streamlit as st
import pandas as pd
from datetime import datetime
from utils import supabase, check_permission

# -----------------------------------------------------------------------------
# 1. МОДАЛ ЗА РЕДАКЦИЯ НА КАМПАНИЯ
# -----------------------------------------------------------------------------
@st.dialog("Редакция на кампания", width="large")
def edit_position_modal(pos_data):
    if not check_permission("recruitment", "manage_positions"):
        st.error("Нямате права за редакция на кампании. Обърнете се към администратор.")
        return

    st.markdown(f"### ⚙️ {pos_data.get('title', 'Неизвестна кампания')}")
    
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
            is_active = pos_data.get('is_active', True)
            status_index = 0 if is_active else 1
            new_status = st.selectbox("Статус на кампанията", status_options, index=status_index)

        st.divider()
        submit_btn = st.form_submit_button("💾 Запази промените", type="primary")
        
        if submit_btn:
            final_is_active = True if new_status == "Активна" else False
            
            update_data = {
                "title": new_title,
                "city": new_city,
                "base_location": new_base,
                "salary_min": new_salary_min,
                "salary_max": new_salary_max,
                "priority": new_priority,
                "is_active": final_is_active
            }
            
            response = supabase.table("hr_positions").update(update_data).eq("id", pos_data['id']).execute()
            
            if response.data:
                st.success("Промените са записани успешно! Презареждане...")
                st.rerun()
            else:
                st.error("Грешка при запис в базата данни.")

# -----------------------------------------------------------------------------
# 2. КАРТОН НА КАНДИДАТА И ОПЕРАЦИИ (Статуси, Оценки, Интервюта)
# -----------------------------------------------------------------------------
@st.dialog("Картон на кандидата", width="large")
def candidate_card_modal(candidate, app_data):
    st.markdown(f"## 👤 {candidate.get('first_name', '')} {candidate.get('last_name', '')}")
    st.caption(f"📧 Имейл: {candidate.get('email', 'Няма')} | 📱 Телефон: {candidate.get('phone', 'Няма')}")
    
    st.divider()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### Оценка и Въпросник")
        if check_permission("recruitment", "evaluate"):
            with st.form(key=f"form_eval_{candidate.get('id', 'new')}"):
                new_notes = st.text_area("Бележки от интервю / Резултати от въпросник", value=app_data.get('notes', ''), height=300)
                submit_eval = st.form_submit_button("💾 Запази бележките", type="primary")
                
                if submit_eval:
                    supabase.table("hr_applications").update({"notes": new_notes}).eq("id", app_data['id']).execute()
                    st.success("Бележките са запазени!")
                    st.rerun()
        else:
            st.info("Нямате права за редакция на оценки. Режим на четене.")
            st.write(app_data.get('notes', 'Няма въведени бележки или въпросник.'))

    with col2:
        st.markdown("### Операции")
        
        # ТОЧНИТЕ 9 СТАТУСА!
        current_status = app_data.get('status', 'Нов')
        status_options = [
            "Нов", "Установи контакт", "Възможно интервю", 
            "Избран за интервю", "Потвърдено интервю", 
            "Направено предложение", "Отхвърлен", "Отказал", "Преместен"
        ]
        
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
                
                exist_date = app_data.get('interview_date')
                exist_time = app_data.get('interview_time')
                exist_interviewer = app_data.get('interviewer_name', '')
                
                parsed_date = datetime.strptime(exist_date, "%Y-%m-%d").date() if exist_date else None
                parsed_time = datetime.strptime(exist_time, "%H:%M:%S").time() if exist_time else None

                int_date = st.date_input("Дата на интервю", value=parsed_date)
                int_time = st.time_input("Час", value=parsed_time)
                interviewer = st.text_input("Интервюиращ", value=exist_interviewer)
                
                submit_schedule = st.form_submit_button("Запази интервю", use_container_width=True)
                
                if submit_schedule:
                    schedule_data = {
                        "interview_date": int_date.strftime("%Y-%m-%d") if int_date else None,
                        "interview_time": int_time.strftime("%H:%M:%S") if int_time else None,
                        "interviewer_name": interviewer
                    }
                    supabase.table("hr_applications").update(schedule_data).eq("id", app_data['id']).execute()
                    st.success("Интервюто е насрочено успешно!")
                    st.rerun()

# -----------------------------------------------------------------------------
# 3. СЪЗДАВАНЕ НА НОВА КАМПАНИЯ
# -----------------------------------------------------------------------------
@st.dialog("Създаване на нова кампания", width="large")
def create_position_modal(company_name):
    if not check_permission("recruitment", "manage_positions"):
        st.error("Нямате права за създаване на кампании.")
        return

    st.markdown(f"### 🏢 Фирма: {company_name}")
    
    with st.form(key="form_create_pos"):
        new_title = st.text_input("Име на позицията *")
        
        st.markdown("👥 **Роли по кампанията (за Action Center)**")
        col_roles1, col_roles2 = st.columns(2)
        with col_roles1:
            owners = st.text_input("Собственици (Мениджъри) - разделени със запетая")
        with col_roles2:
            hr_contact = st.text_input("HR (Установяващ контакт)")
            
        eval_method = st.selectbox("Метод за оценка", ["Числова оценка 1-6 - обективна и субективна", "Само текстови бележки"])
        
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
        submit_btn = st.form_submit_button("➕ Създай кампания", type="primary")
        
        if submit_btn:
            if not new_title:
                st.error("Името на позицията е задължително!")
            else:
                insert_data = {
                    "company_name": company_name,
                    "title": new_title,
                    "city": new_city,
                    "base_location": new_base,
                    "salary_min": new_salary_min,
                    "salary_max": new_salary_max,
                    "priority": priority,
                    "is_active": True
                }
                
                response = supabase.table("hr_positions").insert(insert_data).execute()
                
                if response.data:
                    st.success("Новата кампания е създадена успешно! Презареждане...")
                    st.session_state.active_campaign_id = response.data[0]['id']
                    st.rerun()
                else:
                    st.error("Грешка при запис в базата данни.")
