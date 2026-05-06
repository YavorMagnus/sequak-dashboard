import streamlit as st
import pandas as pd
import zipfile
import io
import re
import datetime
from utils import supabase, COMPANY_MAP, COMPANY_LIST, check_permission

# Опит за импорт на PyPDF2 за четене на PDF-и (ако е инсталиран)
try:
    import PyPDF2
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

def extract_text_from_html(html_content):
    """Изчиства HTML тагове и оставя само чистия текст"""
    text = re.sub(r'<style.*?>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    return ' '.join(text.split())

def extract_text_from_pdf(pdf_bytes):
    """Извлича текст от PDF файл"""
    if not HAS_PYPDF: return "PDF съдържание (нужна е PyPDF2 библиотека)."
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return ' '.join(text.split())
    except Exception:
        return "Грешка при четене на PDF."

def process_candidate_zip(zip_bytes, filename, position_id):
    """Разопакова ZIP, извлича CV текста и създава записите в базите"""
    cv_text_full = ""
    candidate_name = filename.replace('.zip', '').replace('_', ' ').split(' 0')[0].title() # Грубо извличане на име от файла
    
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for file_info in z.infolist():
                if file_info.filename.endswith('.html'):
                    html_content = z.read(file_info.filename).decode('utf-8', errors='ignore')
                    cv_text_full += extract_text_from_html(html_content) + "\n\n"
                elif file_info.filename.endswith('.pdf'):
                    pdf_bytes = z.read(file_info.filename)
                    cv_text_full += extract_text_from_pdf(pdf_bytes) + "\n\n"
    except Exception as e:
        return False, f"Грешка при четене на ZIP: {e}"

    if not cv_text_full.strip():
        return False, "Не бе намерен четим текст (HTML/PDF) в архива."

    # Извличане на Имейл и Телефон чрез Regex
    email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', cv_text_full)
    phone_match = re.search(r'(\+359|0)[0-9\s-]{8,12}', cv_text_full)
    
    email = email_match.group(0) if email_match else f"unknown_{datetime.datetime.now().timestamp()}@noemail.com"
    phone = phone_match.group(0).strip() if phone_match else "Не е намерен"

    # ДЕДУБЛИКАЦИЯ: Проверка дали кандидатът съществува
    cand_res = supabase.table("hr_candidates").select("id").eq("email", email).execute()
    
    if cand_res.data:
        # Кандидатът съществува - Обновяваме му CV-то (за да е най-актуалното)
        cand_id = cand_res.data[0]['id']
        supabase.table("hr_candidates").update({"cv_text": cv_text_full, "phone": phone}).eq("id", cand_id).execute()
    else:
        # Нов кандидат - Създаваме го
        new_cand = supabase.table("hr_candidates").insert({
            "full_name": candidate_name,
            "email": email,
            "phone": phone,
            "cv_text": cv_text_full
        }).execute()
        cand_id = new_cand.data[0]['id']

    # Проверка дали вече е кандидатствал за ТАЗИ позиция
    app_res = supabase.table("hr_applications").select("id").eq("candidate_id", cand_id).eq("position_id", position_id).execute()
    if app_res.data:
        return False, f"{candidate_name} вече е кандидатствал за тази позиция."

    # Създаваме "Лепилото" - Кандидатурата
    supabase.table("hr_applications").insert({
        "candidate_id": cand_id,
        "position_id": position_id,
        "kanban_status": "Ново CV"
    }).execute()

    return True, f"Успешно добавен: {candidate_name} ({email})"

def render_recruitment_module():
    st.title("🎯 Рекрутмънт и Подбор")
    st.markdown("Модул за централизирано управление на позиции, кандидати и интервюта.")
    
    tab_board, tab_import, tab_db = st.tabs(["📋 Позиции и Канбан", "📥 Внос на Кандидати", "🗄️ База Кандидати"])

    # Изтегляне на активните позиции
    try:
        pos_res = supabase.table("hr_positions").select("*, companies(code)").eq("status", "Активна").execute()
        df_positions = pd.DataFrame(pos_res.data)
        if not df_positions.empty:
            df_positions['company_code'] = df_positions['companies'].apply(lambda x: x.get('code', '') if isinstance(x, dict) else '')
    except Exception as e:
        st.error(f"Грешка при връзка с базата: {e}")
        df_positions = pd.DataFrame()

    # --- ТАБ 1: ПОЗИЦИИ И КАНБАН ---
    with tab_board:
        if check_permission("recruitment", "manage_positions"):
            with st.expander("➕ Създаване на нова отворена позиция"):
                with st.form("new_position_form", clear_on_submit=True):
                    p_col1, p_col2 = st.columns(2)
                    with p_col1:
                        p_title = st.text_input("Име на позицията *")
                        p_comp = st.selectbox("За фирма *", COMPANY_LIST)
                    with p_col2:
                        p_priority = st.selectbox("Приоритет", ["Пожар", "Спешно", "Нормално", "Просто се оглеждаме"], index=2)
                        p_assignee = st.text_input("Отговорник (Reassign)", value=st.session_state.username)
                    
                    p_reqs = st.text_area("Матрица с изисквания (Скрито за кандидати, чете се от AI) *", height=100)
                    
                    if st.form_submit_button("Създай Позиция", type="primary"):
                        if not p_title or not p_reqs: st.error("Попълнете задължителните полета!")
                        else:
                            c_id = COMPANY_MAP.get(p_comp)
                            supabase.table("hr_positions").insert({
                                "title": p_title, "company_id": c_id, "priority": p_priority,
                                "requirements_matrix": p_reqs, "assignee": p_assignee
                            }).execute()
                            st.success("✅ Позицията е отворена!")
                            st.rerun()
            st.markdown("---")

        if df_positions.empty:
            st.info("Няма активни позиции в момента.")
        else:
            st.subheader("Активни позиции (Канбан)")
            
            # Избор на позиция за разглеждане
            pos_dict = {f"[{r['company_code']}] {r['title']} ({r['priority']})": r['id'] for _, r in df_positions.iterrows()}
            selected_pos_name = st.selectbox("Изберете позиция за разглеждане:", list(pos_dict.keys()))
            selected_pos_id = pos_dict[selected_pos_name]

            # Изтегляне на кандидатурите за избраната позиция
            app_res = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("position_id", selected_pos_id).execute()
            df_apps = pd.DataFrame(app_res.data)

            if df_apps.empty:
                st.info("Все още няма кандидати за тази позиция.")
            else:
                st.markdown("<br>", unsafe_allow_html=True)
                col_new, col_approved, col_interview = st.columns(3)
                
                def render_candidate_card(app, col):
                    cand = app.get('hr_candidates', {})
                    name = cand.get('full_name', 'Неизвестен')
                    email = cand.get('email', '')
                    phone = cand.get('phone', '')
                    
                    card_html = f"""
                    <div style="background-color: #2a2a2a; border-left: 4px solid #00aaff; padding: 12px; margin-bottom: 10px; border-radius: 5px;">
                        <strong style="color: #FFD700; font-size: 1.1em;">{name}</strong><br>
                        <span style="color: #ccc; font-size: 0.85em;">📞 {phone} | ✉️ {email}</span>
                    </div>
                    """
                    with col:
                        st.markdown(card_html, unsafe_allow_html=True)
                        if st.button("Отвори Картон", key=f"btn_app_{app['id']}", use_container_width=True):
                            st.session_state.active_candidate_app = app
                            st.rerun()

                # Разпределение по колони
                apps_new = df_apps[df_apps['kanban_status'] == 'Ново CV']
                apps_ai = df_apps[df_apps['kanban_status'] == 'Одобрен']
                apps_int = df_apps[df_apps['kanban_status'] == 'Интервю']

                with col_new:
                    st.markdown(f"<h4 style='text-align:center;'>Нови ({len(apps_new)})</h4>", unsafe_allow_html=True)
                    for _, row in apps_new.iterrows(): render_candidate_card(row.to_dict(), col_new)
                with col_approved:
                    st.markdown(f"<h4 style='text-align:center;'>Одобрени ({len(apps_ai)})</h4>", unsafe_allow_html=True)
                    for _, row in apps_ai.iterrows(): render_candidate_card(row.to_dict(), col_approved)
                with col_interview:
                    st.markdown(f"<h4 style='text-align:center;'>За Интервю ({len(apps_int)})</h4>", unsafe_allow_html=True)
                    for _, row in apps_int.iterrows(): render_candidate_card(row.to_dict(), col_interview)

            # HARD DELETE ЗОНА ЗА ПОЗИЦИЯТА (САМО ЗА СУПЕР-АДМИН)
            if st.session_state.user_role == "Супер-админ":
                st.markdown("<br><br>", unsafe_allow_html=True)
                with st.expander("☢️ Опасна зона: Hard Delete на Позицията"):
                    st.error("Внимание! Изтриването на позицията ще изтрие и всички нейни Канбан-картончета (кандидатури). Самите хора ще останат в базата (Архив).")
                    if st.button("❌ ИЗТРИЙ ТАЗИ ПОЗИЦИЯ НАПЪЛНО", key=f"del_pos_{selected_pos_id}", type="primary"):
                        try:
                            supabase.table("hr_positions").delete().eq("id", selected_pos_id).execute()
                            st.success("✅ Позицията беше изтрита успешно!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Грешка при изтриване: {e}")

    # --- КАРТОН НА КАНДИДАТА (ДИАЛОГ) ---
    if 'active_candidate_app' in st.session_state:
        @st.dialog("Картон на Кандидата", width="large")
        def show_candidate_dialog():
            app = st.session_state.active_candidate_app
            cand = app.get('hr_candidates', {})
            
            st.markdown(f"<h2 style='color:#FFD700; margin-bottom:0;'>{cand.get('full_name')}</h2>", unsafe_allow_html=True)
            st.caption(f"📞 {cand.get('phone')} | ✉️ {cand.get('email')}")
            st.markdown("---")
            
            t_cv, t_notes = st.tabs(["📄 Извлечено CV", "✍️ Бележки и Решения"])
            
            with t_cv:
                st.markdown("<div style='background-color:#1e1e1e; padding:15px; border-radius:5px; max-height: 400px; overflow-y: auto;'>", unsafe_allow_html=True)
                st.write(cand.get('cv_text', 'Няма текст'))
                st.markdown("</div>", unsafe_allow_html=True)
                
            with t_notes:
                new_status = st.selectbox("Смени Канбан Статус", ["Ново CV", "Одобрен", "Интервю", "Отхвърлен"], index=["Ново CV", "Одобрен", "Интервю", "Отхвърлен"].index(app.get('kanban_status', 'Ново CV')))
                
                st.markdown("**AI Оценка:**")
                st.info(app.get('ai_evaluation') or "Все още няма AI оценка.")
                if check_permission("recruitment", "evaluate"):
                    if st.button("✨ Генерирай AI Оценка (Очаква Gemini API)"):
                        st.warning("Интеграцията с Gemini API предстои. Засега полето е ръчно.")
                
                st.markdown("<br>", unsafe_allow_html=True)
                r_notes = st.text_area("Бележки на Рекрутъра", value=app.get('recruiter_notes') or "")
                
                # Червеният телефон
                if check_permission("ro_registry", "export"): # Условна проверка за висш мениджмънт
                    c_notes = st.text_area("Поверителни бележки (Червен телефон)", value=app.get('confidential_notes') or "")
                else:
                    c_notes = app.get('confidential_notes')

                if st.button("💾 Запази промените по картона", type="primary"):
                    supabase.table("hr_applications").update({
                        "kanban_status": new_status,
                        "recruiter_notes": r_notes,
                        "confidential_notes": c_notes
                    }).eq("id", app['id']).execute()
                    del st.session_state.active_candidate_app
                    st.rerun()
                    
            if st.button("✖ Затвори"):
                del st.session_state.active_candidate_app
                st.rerun()
                
            # HARD DELETE ЗОНА ЗА КАНДИДАТА (САМО ЗА СУПЕР-АДМИН)
            if st.session_state.user_role == "Супер-админ":
                st.markdown("---")
                with st.expander("☢️ Опасна зона: Hard Delete на Кандидата"):
                    st.error("Внимание! Това ще изтрие този човек от ЦЯЛАТА система завинаги, включително историята му от други позиции.")
                    if st.button("❌ ИЗТРИЙ ТОЗИ КАНДИДАТ НАПЪЛНО", key=f"del_cand_{cand['id']}", type="primary"):
                        try:
                            supabase.table("hr_candidates").delete().eq("id", cand['id']).execute()
                            del st.session_state.active_candidate_app
                            st.success("✅ Кандидатът беше изтрит успешно!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Грешка при изтриване: {e}")

        show_candidate_dialog()

    # --- ТАБ 2: ВНОС НА КАНДИДАТИ ---
    with tab_import:
        if check_permission("recruitment", "upload_candidates"):
            st.subheader("📥 Внос на кандидати от jobs.bg")
            if df_positions.empty:
                st.warning("Първо трябва да създадете активна позиция, към която да закачите кандидатите.")
            else:
                pos_dict_import = {f"[{r['company_code']}] {r['title']}": r['id'] for _, r in df_positions.iterrows()}
                target_pos = st.selectbox("Към коя позиция да се закачат кандидатите?", list(pos_dict_import.keys()))
                target_pos_id = pos_dict_import[target_pos]

                uploaded_files = st.file_uploader("Маркирайте и пуснете ZIP файловете тук", type="zip", accept_multiple_files=True)
                
                if uploaded_files:
                    if st.button("🚀 Обработи и Качи в Базата", type="primary"):
                        successes = 0
                        progress_bar = st.progress(0)
                        
                        for i, file in enumerate(uploaded_files):
                            success, msg = process_candidate_zip(file.getvalue(), file.name, target_pos_id)
                            if success: successes += 1
                            else: st.error(msg)
                            progress_bar.progress((i + 1) / len(uploaded_files))
                            
                        st.success(f"✅ Готово! Успешно качени {successes} от {len(uploaded_files)} кандидати.")
        else:
            st.info("Нямате права за внос на кандидати.")

    # --- ТАБ 3: БАЗА КАНДИДАТИ ---
    with tab_db:
        st.subheader("🗄️ Търсачка в Архива (Всички кандидати)")
        search_q = st.text_input("Търсене по ключова дума в CV-тата (напр. 'строителна техника', 'Английски', 'Перник')")
        
        if search_q:
            # Търсене в текста на CV-то
            try:
                res_search = supabase.table("hr_candidates").select("*").ilike("cv_text", f"%{search_q}%").execute()
                df_search = pd.DataFrame(res_search.data)
                
                if df_search.empty:
                    st.write("Няма намерени кандидати с тази ключова дума.")
                else:
                    st.write(f"Намерени **{len(df_search)}** съвпадения:")
                    for _, cand in df_search.iterrows():
                        with st.expander(f"👤 {cand['full_name']} | 📞 {cand['phone']}"):
                            st.write(cand['cv_text'][:500] + "... [вижте повече в Канбана]")
            except Exception as e:
                st.error("Грешка при търсене.")
