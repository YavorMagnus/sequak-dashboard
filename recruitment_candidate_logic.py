import streamlit as st
import pandas as pd
from datetime import datetime
from utils import supabase

# Помощна функция за генериране на часове през 15 минути за падащите менюта
def generate_time_options():
    time_list = []
    for hour in range(8, 19):  # От 08:00 до 18:00
        for minute in [0, 15, 30, 45]:
            time_list.append(f"{hour:02d}:{minute:02d}")
    return time_list

def render_interviews_tab(app_data, interview_info):
    time_slots = generate_time_options()
    
    # Изтегляме списъка с потребители за всички акордеони
    users_resp = supabase.table("users").select("username").execute()
    user_list = [u['username'] for u in users_resp.data] if users_resp.data else []
    
    # 1. ТЕЛЕФОННО ИНТЕРВЮ (ОБНОВЕНО С ИНТЕРВЮИРАЩ)
    with st.expander("📞 1. Телефонно интервю (HR Скрининг)", expanded=False):
        # Логика за HR по подразбиране
        default_hr = "C.Foteva"
        curr_ph_int = interview_info.get('ph_interviewer')
        if not curr_ph_int:
            if default_hr in user_list:
                curr_ph_int = default_hr
            elif st.session_state.get('username') in user_list:
                curr_ph_int = st.session_state.username
            else:
                curr_ph_int = user_list[0] if user_list else ""

        sel_ph_int = st.selectbox("Провеждащ скрининга", user_list, index=user_list.index(curr_ph_int) if curr_ph_int in user_list else 0, key=f"ph_int_{app_data['id']}")

        col_date1, col_time1 = st.columns(2)
        with col_date1:
            ph_d_val = datetime.strptime(interview_info['ph_date'], "%Y-%m-%d").date() if interview_info.get('ph_date') else datetime.now()
            phone_date = st.date_input("Дата на обаждане", value=ph_d_val, key=f"phone_date_{app_data['id']}")
        with col_time1:
            ph_t_val = interview_info.get('ph_time', '10:00')
            phone_time = st.selectbox("Час", time_slots, index=time_slots.index(ph_t_val) if ph_t_val in time_slots else 0, key=f"phone_time_{app_data['id']}")
        
        if st.button("📞 Запази график", type="primary", use_container_width=True):
            interview_info.update({
                'ph_date': phone_date.strftime("%Y-%m-%d"), 
                'ph_time': phone_time,
                'ph_interviewer': sel_ph_int
            })
            supabase.table("hr_applications").update({"interview_details": interview_info}).eq("id", app_data['id']).execute()
            st.toast("✅ Графикът за телефонно интервю е запазен!")

    # 2. ПОКАНА ОТ МЕНИДЖЪР
    with st.expander("💡 2. Покана от мениджър (Предложение за дати)", expanded=False):
        st.info("Мениджърът предлага варианти за среща:")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            m1_val = datetime.strptime(interview_info['mgr_date1'], "%Y-%m-%d").date() if interview_info.get('mgr_date1') else datetime.now()
            m_date1 = st.date_input("Вариант 1: Дата", value=m1_val, key=f"mgr_d1_{app_data['id']}")
            m_range1 = st.text_input("Вариант 1: Диапазон", value=interview_info.get('mgr_range1', ''), placeholder="напр. 10:00 - 12:00", key=f"mgr_r1_{app_data['id']}")
        with col_m2:
            m2_val = datetime.strptime(interview_info['mgr_date2'], "%Y-%m-%d").date() if interview_info.get('mgr_date2') else datetime.now()
            m_date2 = st.date_input("Вариант 2: Дата", value=m2_val, key=f"mgr_d2_{app_data['id']}")
            m_range2 = st.text_input("Вариант 2: Диапазон", value=interview_info.get('mgr_range2', ''), placeholder="напр. след 15:30", key=f"mgr_r2_{app_data['id']}")
        
        if st.button("💡 Предложи интервю", type="primary", use_container_width=True):
            interview_info.update({
                'mgr_date1': m_date1.strftime("%Y-%m-%d"), 'mgr_range1': m_range1,
                'mgr_date2': m_date2.strftime("%Y-%m-%d"), 'mgr_range2': m_range2
            })
            supabase.table("hr_applications").update({
                "interview_details": interview_info, 
                "status": "Избран за интервю"
            }).eq("id", app_data['id']).execute()
            st.rerun()

    # 3. НАСРОЧВАНЕ НА ОФИЦИАЛНО ИНТЕРВЮ
    with st.expander("🏢 3. Насрочване на интервю с мениджър", expanded=False):
        curr_int = interview_info.get('interviewer_name', st.session_state.username)
        selected_interviewer = st.selectbox("Интервюиращ", user_list, index=user_list.index(curr_int) if curr_int in user_list else 0, key=f"sel_interv_{app_data['id']}")
        
        col_f_date, col_f_time = st.columns(2)
        with col_f_date:
            f_val = datetime.strptime(interview_info['interview_date'], "%Y-%m-%d").date() if interview_info.get('interview_date') else datetime.now()
            final_date = st.date_input("Финална Дата", value=f_val, key=f"final_date_{app_data['id']}")
        with col_f_time:
            f_t_val = interview_info.get('interview_time', '10:00')
            final_time = st.selectbox("Финален Час", time_slots, index=time_slots.index(f_t_val) if f_t_val in time_slots else 0, key=f"final_time_{app_data['id']}")
        
        if st.button("🏢 Потвърди интервю", type="primary", use_container_width=True):
            interview_info.update({
                'interviewer_name': selected_interviewer, 
                'interview_date': final_date.strftime("%Y-%m-%d"), 
                'interview_time': final_time
            })
            supabase.table("hr_applications").update({
                "interview_details": interview_info, 
                "status": "Потвърдено интервю"
            }).eq("id", app_data['id']).execute()
            st.rerun()

@st.fragment
def render_status_tab(candidate, app_data, pos_data, interview_info):
    st.markdown("### ⚙️ Смяна на статус")
    all_statuses = ["Нов", "Установи контакт", "Възможно интервю", "Избран за интервю", "Потвърдено интервю", "Направено предложение", "Отхвърлен", "Отказал", "Преместен"]
    current_status_name = app_data.get('status', 'Нов')
    new_status_selection = st.selectbox("Изберете нов статус", all_statuses, index=all_statuses.index(current_status_name) if current_status_name in all_statuses else 0)
    
    # 1. Логика за "Отхвърлен"
    if new_status_selection == "Отхвърлен":
        reject_data = supabase.table("hr_settings").select("setting_value").eq("setting_key", "reject_reasons").execute()
        reject_reasons = reject_data.data[0].get("setting_value", ["Друго"]) if reject_data.data else ["Друго"]
        curr_r = app_data.get('rejection_reason')
        is_res = app_data.get('is_backup', False)
        st.selectbox("Причина за отхвърляне", reject_reasons, index=reject_reasons.index(curr_r) if curr_r in reject_reasons else 0, key=f"reject_reason_sel_{app_data['id']}")
        st.checkbox("Запази в резерва?", value=is_res, key=f"is_reserve_check_{app_data['id']}")

    # 2. Логика за "Отказал"
    if new_status_selection == "Отказал":
        decline_data = supabase.table("hr_settings").select("setting_value").eq("setting_key", "decline_reasons").execute()
        decline_reasons = decline_data.data[0].get("setting_value", ["Друго"]) if decline_data.data else ["Друго"]
        curr_res = app_data.get('resolution_reason')
        st.selectbox("Причина за отказ (от страна на кандидата)", decline_reasons, index=decline_reasons.index(curr_res) if curr_res in decline_reasons else 0, key=f"decline_reason_sel_{app_data['id']}")

    # 3. Логика за "Направено предложение"
    if new_status_selection == "Направено предложение":
        curr_offer = interview_info.get('offer_value', '')
        is_offer_closed = interview_info.get('offer_closed', False)
        # ДОРАБОТКА 2: Текстово поле за офертата
        st.text_input("Параметри на предложението (Възнаграждение/Придобивки)", value=curr_offer, placeholder="напр. 1600 EUR нето + бонус", key=f"offer_val_{app_data['id']}")
        st.checkbox("Офертата е приета / Процесът е финализиран", value=is_offer_closed, key=f"offer_closed_{app_data['id']}")

    # 4. Логика за "Преместен / Копиран"
    if new_status_selection == "Преместен":
        pos_resp = supabase.table("hr_positions").select("id, title, company_name").eq("status", "Активна").eq("is_deleted", False).execute()
        target_positions = {p['id']: f"{p['title']} ({p['company_name']})" for p in pos_resp.data if p['id'] != pos_data['id']}
        
        if target_positions:
            target_id = st.selectbox("Премести в обява:", options=list(target_positions.keys()), format_func=lambda x: target_positions[x])
            keep_current = st.checkbox("Запази копие и в текущата обява?", value=False)
            
            if not keep_current:
                st.warning("🚨 ВНИМАНИЕ: Кандидатът ще бъде прехвърлен в група 'Преместени'. Сигурни ли сте?")
                confirm_btn_label = "⚠️ Потвърди окончателно преместване"
            else:
                confirm_btn_label = "🔄 Премести (с копие)"
                
            if st.button(confirm_btn_label, type="primary"):
                target_pos_name = target_positions[target_id]
                old_pos_name = f"{pos_data.get('title', '')} ({pos_data.get('company_name', '')})" if pos_data else "Неизвестна обява"
                
                if keep_current:
                    action_verb_old = "копиран в"
                    action_verb_new = "копиран от"
                else:
                    action_verb_old = "преместен в"
                    action_verb_new = "преместен от"

                new_app_res = supabase.table("hr_applications").insert({
                    "candidate_id": candidate['id'], 
                    "position_id": target_id, 
                    "status": "Нов"
                }).execute()
                
                if new_app_res.data:
                    new_app_id = new_app_res.data[0]['id']
                    current_user = st.session_state.get('username', 'Система')
                    
                    supabase.table("hr_comments").insert({
                        "application_id": new_app_id,
                        "author_name": current_user,
                        "comment_text": f"Автоматично съобщение: Кандидатът е {action_verb_new} обява {old_pos_name}.",
                        "comment_type": "Системна"
                    }).execute()
                    
                    supabase.table("hr_comments").insert({
                        "application_id": app_data['id'],
                        "author_name": current_user,
                        "comment_text": f"Автоматично съобщение: Кандидатът беше {action_verb_old} обява {target_pos_name}.",
                        "comment_type": "Системна"
                    }).execute()
                    
                if not keep_current:
                    supabase.table("hr_applications").update({
                        "status": "Преместен"
                    }).eq("id", app_data['id']).execute()
                    
                st.rerun()

    # Бутон за запазване на standard статуси
    if new_status_selection != "Преместен":
        if st.button("🔄 Запази новия статус", type="primary", use_container_width=True):
            update_payload = {
                "status": new_status_selection,
                "interview_details": interview_info
            }
            
            status_changed = (new_status_selection != current_status_name)
            system_note_text = None
            
            # --- Управление на полетата за Отхвърлен ---
            if new_status_selection == "Отхвърлен":
                if f"reject_reason_sel_{app_data['id']}" in st.session_state:
                    selected_reason = st.session_state[f"reject_reason_sel_{app_data['id']}"]
                    update_payload['rejection_reason'] = selected_reason
                    # ДОРАБОТКА 1: Подготовка на системна бележка
                    if status_changed:
                        system_note_text = f"Автоматично съобщение: Статусът е променен на 'Отхвърлен'. Причина: {selected_reason}"
                        
                if f"is_reserve_check_{app_data['id']}" in st.session_state:
                    update_payload['is_backup'] = st.session_state[f"is_reserve_check_{app_data['id']}"]
            else:
                update_payload['rejection_reason'] = None
                update_payload['is_backup'] = False

            # --- Управление на полетата за Отказал ---
            if new_status_selection == "Отказал":
                if f"decline_reason_sel_{app_data['id']}" in st.session_state:
                    selected_decline = st.session_state[f"decline_reason_sel_{app_data['id']}"]
                    update_payload['resolution_reason'] = selected_decline
                    # ДОРАБОТКА 1: Подготовка на системна бележка
                    if status_changed:
                        system_note_text = f"Автоматично съобщение: Статусът е променен на 'Отказал'. Причина: {selected_decline}"
            else:
                update_payload['resolution_reason'] = None

            # --- Управление на полетата за Направено предложение ---
            if new_status_selection == "Направено предложение":
                if f"offer_val_{app_data['id']}" in st.session_state:
                    update_payload['interview_details']['offer_value'] = st.session_state[f"offer_val_{app_data['id']}"]
                if f"offer_closed_{app_data['id']}" in st.session_state:
                    update_payload['interview_details']['offer_closed'] = st.session_state[f"offer_closed_{app_data['id']}"]
            else:
                update_payload['interview_details']['offer_closed'] = False
            
            # ДОРАБОТКА 1: Запис на системната бележка (ако има такава)
            if system_note_text:
                current_user = st.session_state.get('username', 'Система')
                supabase.table("hr_comments").insert({
                    "application_id": app_data['id'],
                    "author_name": current_user,
                    "comment_text": system_note_text,
                    "comment_type": "Системна"
                }).execute()

            supabase.table("hr_applications").update(update_payload).eq("id", app_data['id']).execute()
            st.rerun()
