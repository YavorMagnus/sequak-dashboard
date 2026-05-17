import streamlit as st
import pandas as pd
from datetime import datetime
from utils import supabase
from recruitment_candidate_logic import render_interviews_tab, render_status_tab

# -----------------------------------------------------------------------------
# 2. ИНТЕЛИГЕНТЕН КАРТОН НА КАНДИДАТА
# -----------------------------------------------------------------------------
@st.dialog("Картон на кандидата", width="large")
def candidate_card_modal(candidate, app_data, pos_data=None):
    # Данни
    cv_info = candidate.get('raw_cv_data') or {}
    interview_info = app_data.get('interview_details') or {}
    scores = app_data.get('manual_score') or {}
    
    # Обективни категории
    categories = ["Търговска", "Сервизна", "Строителна/архитектурна", "Юридическа", "IT", "Складова", "Счетоводно-административна", "Управленска"]
    
    # Изчисляване на точките
    obj_total = sum(scores.get(cat, 0) for cat in categories)
    subj_total = scores.get("Субективна", 0)
    
    # --- ХЕДЪР ---
    col_photo, col_name, col_upcoming, col_status = st.columns([1, 1.5, 2, 1])
    
    with col_photo:
        if candidate.get('photo_thumbnail'):
            st.image(f"data:image/png;base64,{candidate['photo_thumbnail']}", use_container_width=True)
        else:
            st.write("<div style='font-size: 60px; text-align: center; color: gray;'>👤</div>", unsafe_allow_html=True)
            
    with col_name:
        st.subheader(candidate.get('full_name', 'Неизвестен'))
        
    with col_upcoming:
        st.markdown("**📅 Предстоящи стъпки:**")
        ph_d = interview_info.get('ph_date')
        if ph_d:
            st.markdown(f"📞 Телефонно: **{ph_d}** в **{interview_info.get('ph_time', '')}**")
            
        mgr_d1 = interview_info.get('mgr_date1')
        if mgr_d1:
            mgr_r1 = interview_info.get('mgr_range1', '')
            mgr_d2 = interview_info.get('mgr_date2', '')
            mgr_r2 = interview_info.get('mgr_range2', '')
            
            opt1_text = f"{mgr_d1} ({mgr_r1})" if mgr_r1 else f"{mgr_d1}"
            opt2_text = f"{mgr_d2} ({mgr_r2})" if mgr_r2 else f"{mgr_d2}"
            
            st.markdown(f"💡 Предложени: **{opt1_text}** / **{opt2_text}**")
            
        off_d = interview_info.get('interview_date')
        if off_d:
            st.markdown(f"🏢 **Потвърдено:** {off_d} в {interview_info.get('interview_time', '')}")
            
        if not ph_d and not mgr_d1 and not off_d:
            st.caption("Няма насрочени стъпки.")
        
    with col_status:
        st.info(f"**Статус:** {app_data.get('status', 'Нов')}")
        st.markdown(f"**Обективна:** {obj_total}/48<br>**Субективна:** {subj_total}/6", unsafe_allow_html=True)

    st.divider()

    # --- ЗАРЕЖДАНЕ НА БЕЛЕЖКИТЕ ---
    comments_query = supabase.table("hr_comments").select("*").eq("application_id", app_data['id']).order("created_at", desc=True).execute()
    all_comments = comments_query.data if comments_query.data else []

    # --- ШИРОКИ БАНЕРИ НАД ТАБОВЕТЕ ---
    if pos_data:
        p_title = pos_data.get('title', 'Неизвестна')
        p_city = pos_data.get('city', 'Няма')
        s_min = pos_data.get('salary_min', '0')
        s_max = pos_data.get('salary_max', '0')
        
        # ДОРАБОТКА 3: Показване на параметрите на офертата в синия банер
        banner_text = f"🎯 **Обява:** {p_title} ({p_city}) | **Възнаграждение:** EUR {s_min} - {s_max}"
        if app_data.get('status') == "Направено предложение":
            offer_val = interview_info.get('offer_value', '')
            if offer_val:
                banner_text += f" | 💶 **Оферта:** {offer_val}"
                
        st.info(banner_text)

    if all_comments:
        latest_note = all_comments[0]
        dt_str = pd.to_datetime(latest_note['created_at']).strftime('%d.%m.%Y %H:%M')
        full_text = latest_note.get('comment_text', '')
        display_text = full_text if len(full_text) <= 500 else full_text[:500] + "..."
        st.warning(f"💬 **Последна бележка ({latest_note.get('author_name', 'Система')} - {dt_str}):** {display_text}")

    # ПАЧ 1: Бутон "Сподели кандидат" с извличане на base_url от базата (БРОНИРАН ПРОТИВ КРАШОВЕ)
    col_share_empty, col_share_btn = st.columns([4, 1])
    with col_share_btn:
        if st.button("🔗 Сподели кандидат", use_container_width=True):
            base_url = ""
            try:
                url_res = supabase.table("hr_settings").select("setting_value").eq("setting_key", "base_url").execute()
                if url_res.data:
                    base_url = url_res.data[0].get("setting_value", "")
            except Exception:
                pass # Защита от червен екран - ако базата прекъсне, ще върне относителна навигация
            
            # Сглобяване на абсолютен линк
            if base_url:
                share_url = f"{base_url.strip('/')}/?app_id={app_data['id']}"
            else:
                share_url = f"/?app_id={app_data['id']}"
                
            st.info(f"Линк (Ctrl+C): `{share_url}`")

    st.write("<br>", unsafe_allow_html=True)

    # --- ТАБОВЕ ---
    tab_list = st.tabs(["📝 Въпросник", "📄 CV", "📊 Оценка", "💬 Бележки", "📅 Интервюта", "⚙️ Статус"])

    # ТАБ 1: ВЪПРОСНИК
    with tab_list[0]:
        if st.toggle("✏️ Редакция на текста", key=f"edit_toggle_q_{app_data['id']}"):
            updated_q = st.text_area("Въпросник (Редакция)", value=cv_info.get('questionnaire', ''), height=250)
            if st.button("💾 Запази Въпросник"):
                cv_info['questionnaire'] = updated_q
                supabase.table("hr_candidates").update({"raw_cv_data": cv_info}).eq("id", candidate['id']).execute()
                st.toast("✅ Въпросникът е запазен успешно!")
        else:
            st.markdown(cv_info.get('questionnaire', 'Няма въпросник.'))

    # ТАБ 2: CV
    with tab_list[1]:
        if st.toggle("✏️ Редакция на текста", key=f"edit_toggle_cv_{app_data['id']}"):
            updated_cv = st.text_area("CV Текст (Редакция)", value=cv_info.get('cv_text', ''), height=350)
            if st.button("💾 Запази CV"):
                cv_info['cv_text'] = updated_cv
                supabase.table("hr_candidates").update({"raw_cv_data": cv_info}).eq("id", candidate['id']).execute()
                st.toast("✅ CV-то е запазено успешно!")
        else:
            st.markdown(cv_info.get('cv_text', 'Няма зареден текст на CV.'))

    # ТАБ 3: ОЦЕНКА
    with tab_list[2]:
        st.markdown("### 📊 Оценка по компетенции")
        with st.form(key=f"form_evaluation_{app_data['id']}"):
            new_manual_scores = {}
            score_cols = st.columns(2)
            for index, category in enumerate(categories):
                with score_cols[index % 2]:
                    current_val = scores.get(category, 1)
                    new_manual_scores[category] = st.slider(category, 1, 6, current_val)
            st.divider()
            st.markdown("### 🎭 Субективна оценка (Цялостно впечатление)")
            new_manual_scores["Субективна"] = st.slider("Обща субективна оценка", 1, 6, scores.get("Субективна", 1))
            
            if st.form_submit_button("💾 Запази всички оценки", type="primary"):
                supabase.table("hr_applications").update({"manual_score": new_manual_scores}).eq("id", app_data['id']).execute()
                st.toast("✅ Оценките са обновени!")

    # ТАБ 4: БЕЛЕЖКИ (ИСТОРИЯ И ДОБАВЯНЕ)
    with tab_list[3]:
        st.markdown("### 💬 Добави нова бележка")
        note_to_add = st.text_area("Въведете коментар тук:", height=100, key=f"input_note_{app_data['id']}")
        if st.button("➕ Добави бележка", type="primary"):
            if note_to_add.strip():
                new_note_entry = {
                    "application_id": app_data['id'],
                    "author_name": st.session_state.username,
                    "comment_text": note_to_add.strip(),
                    "comment_type": "Бележка"
                }
                res = supabase.table("hr_comments").insert(new_note_entry).execute()
                if res.data:
                    all_comments.insert(0, res.data[0]) 
                st.toast("✅ Бележката е добавена успешно!")
                
        st.divider()
        st.markdown("### 📜 История")
        for comment in all_comments:
            with st.container(border=True):
                st.markdown(f"**{comment.get('author_name')}** | {pd.to_datetime(comment.get('created_at', datetime.now())).strftime('%d.%m.%Y %H:%M')}")
                st.write(comment.get('comment_text'))

    # ТАБ 5: ИНТЕРВЮТА (ИЗНЕСЕНО В LOGIC)
    with tab_list[4]:
        render_interviews_tab(app_data, interview_info)

    # ТАБ 6: СТАТУС (ИЗНЕСЕНО В LOGIC)
    with tab_list[5]:
        render_status_tab(candidate, app_data, pos_data, interview_info)

    # --- ОПАСНА ЗОНА (ИЗТРИВАНЕ НА КАНДИДАТ) ---
    st.markdown("---")
    with st.expander("🗑️ Управление на записа (Изтриване)", expanded=False):
        c_del1, c_del2 = st.columns(2)
        with c_del1:
            if st.button("🗑️ Премести в кошчето", key=f"soft_del_cand_{app_data['id']}", use_container_width=True):
                supabase.table("hr_applications").update({"is_deleted": True}).eq("id", app_data['id']).execute()
                st.rerun()
        with c_del2:
            if st.button("☢️ Окончателно изтриване", type="primary", key=f"hard_del_cand_{app_data['id']}", use_container_width=True):
                supabase.table("hr_comments").delete().eq("application_id", app_data['id']).execute()
                supabase.table("hr_applications").delete().eq("id", app_data['id']).execute()
                supabase.table("hr_candidates").delete().eq("id", candidate['id']).execute()
                st.rerun()
