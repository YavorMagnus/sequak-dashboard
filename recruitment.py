import streamlit as st
import pandas as pd
from utils import supabase, check_permission
import zipfile
import io
from bs4 import BeautifulSoup
import PyPDF2
import re
import html 
import docx

# ЗАБЕЛЕЖКА: Gemini API Key трябва да бъде добавен в st.secrets за сигурност
# import google.generativeai as genai

def render_recruitment_module():
    st.header("📋 Модул Рекрутмънт и Подбор (ATS)")

    if not check_permission("recruitment", "read"):
        st.error("Нямате достъп до този модул.")
        return

    tabs = st.tabs(["📊 Канбан", "👥 База Кандидати", "💼 Позиции", "📥 Внос (Jobs.bg)", "⚙️ Настройки"])

    # --- ИЗВЛИЧАНЕ НА ПОЗИЦИИТЕ ГЛОБАЛНО ---
    try:
        positions_df = supabase.table("hr_positions").select("*").limit(100000).execute()
        has_positions = bool(positions_df.data)
    except Exception as e:
        st.error(f"Грешка при връзка с таблица hr_positions: {e}")
        has_positions = False

    # --- ТАБ: ПОЗИЦИИ ---
    with tabs[2]:
        st.subheader("Управление на отворени позиции")
        
        if check_permission("recruitment", "manage_positions"):
            with st.form("add_position"):
                pos_name = st.text_input("Име на позицията (напр. Механик, Търговски представител)")
                pos_req = st.text_area("Изисквания (Матрица за AI оценка)")
                submit_pos = st.form_submit_button("Създай позиция")

                if submit_pos and pos_name:
                    try:
                        supabase.table("hr_positions").insert({"title": pos_name, "requirements": pos_req}).execute()
                        st.success("Позицията е създадена!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Грешка при запис в Supabase: {e}")
        else:
            st.info("Нямате права за създаване на нови позиции. Режим на четене.")

        if has_positions:
            df_p = pd.DataFrame(positions_df.data)
            cols_to_show = [c for c in ["title", "requirements", "created_at"] if c in df_p.columns]
            st.table(df_p[cols_to_show])
        else:
            st.info("Все още няма създадени отворени позиции.")

    # --- ТАБ: ВНОС ---
    with tabs[3]:
        st.subheader("Масово качване на кандидати от Jobs.bg (ZIP)")
        
        if check_permission("recruitment", "upload_candidates"):
            target_pos = st.selectbox(
                "Избери позиция за вноса", 
                [p["title"] for p in positions_df.data] if has_positions else ["Няма активни позиции"]
            )
            
            uploaded_files = st.file_uploader("Качи ZIP архив/и", type="zip", accept_multiple_files=True)

            if uploaded_files and st.button("Стартирай импорт"):
                if not has_positions:
                    st.warning("Моля, първо създайте позиция в таб 'Позиции'.")
                else:
                    count = 0
                    errors_log = [] 
                    
                    # ОПТИМИЗАЦИЯ 1: Взимаме ID-то на позицията предварително, за да не питаме базата 100 пъти
                    target_pos_id = None
                    for p in positions_df.data:
                        if p["title"] == target_pos:
                            target_pos_id = p["id"]
                            break
                    
                    with st.spinner("Интелигентен парсинг (Извличане на правилни имена)..."):
                        for uploaded_file in uploaded_files:
                            try:
                                candidate_text_parts = []
                                
                                raw_zip_name = uploaded_file.name.replace(".zip", "").replace(".ZIP", "")
                                clean_zip_name = re.sub(r'_[0-9\.\-]+$', '', raw_zip_name).replace('_', ' ').strip()
                                
                                candidate_name = clean_zip_name if clean_zip_name else "Неизвестен"
                                has_beautiful_name = bool(clean_zip_name)
                                
                                with zipfile.ZipFile(uploaded_file, "r") as z:
                                    for file_name in z.namelist():
                                        base_name_lower = file_name.split('/')[-1].lower()
                                        
                                        if base_name_lower in ["jobs.bg", "business.jobs.bg"] or base_name_lower.endswith(".url"):
                                            continue

                                        clean_text = ""

                                        # 1. HTML
                                        if base_name_lower.endswith((".html", ".htm")):
                                            with z.open(file_name) as f:
                                                html_content = f.read().decode("utf-8", errors="ignore")
                                                soup = BeautifulSoup(html_content, "html.parser")
                                                
                                                for br in soup.find_all("br"): br.replace_with("\n")
                                                for p in soup.find_all(["p", "div", "tr"]): p.append("\n")
                                                
                                                raw_text = soup.get_text(separator=' ')
                                                clean_text = html.unescape(raw_text).replace('\xa0', ' ')
                                                
                                                if not has_beautiful_name:
                                                    lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
                                                    if len(lines) >= 2 and "jobs.bg" in lines[0].lower():
                                                        candidate_name = lines[1] 
                                                        has_beautiful_name = True
                                                
                                        # 2. PDF
                                        elif base_name_lower.endswith(".pdf"):
                                            with z.open(file_name) as f:
                                                pdf_reader = PyPDF2.PdfReader(f)
                                                raw_text = ""
                                                for page in pdf_reader.pages:
                                                    extracted = page.extract_text()
                                                    if extracted: raw_text += extracted + "\n"
                                                clean_text = raw_text
                                                
                                        # 3. Word (.docx)
                                        elif base_name_lower.endswith(".docx"):
                                            with z.open(file_name) as f:
                                                file_stream = io.BytesIO(f.read())
                                                doc = docx.Document(file_stream)
                                                raw_text = "\n".join([para.text for para in doc.paragraphs])
                                                clean_text = raw_text
                                                
                                        # 4. Old Word (.doc)
                                        elif base_name_lower.endswith(".doc"):
                                            with z.open(file_name) as f:
                                                raw_bytes = f.read()
                                                decoded_text = raw_bytes.decode("utf-8", errors="ignore")
                                                
                                                if "<html" in decoded_text.lower() or "jobs.bg" in decoded_text.lower():
                                                    soup = BeautifulSoup(decoded_text, "html.parser")
                                                    for br in soup.find_all("br"): br.replace_with("\n")
                                                    clean_text = html.unescape(soup.get_text(separator=' ')).replace('\xa0', ' ')
                                                else:
                                                    text = raw_bytes.decode("windows-1251", errors="ignore")
                                                    clean_text = re.sub(r'[^\w\s\.,!?-]', ' ', text)
                                            
                                        # Чистене
                                        if clean_text:
                                            clean_text = clean_text.replace('\x00', '').replace('\u0000', '')
                                            clean_text = re.sub(r' +', ' ', clean_text)
                                            clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text).strip()
                                            
                                            if len(clean_text) > 10: 
                                                candidate_text_parts.append(clean_text)

                                if candidate_text_parts:
                                    final_cv_text = "\n\n--- ДОПЪЛНИТЕЛЕН ДОКУМЕНТ ---\n\n".join(candidate_text_parts)
                                    
                                    candidate_data = {
                                        "full_name": candidate_name,
                                        "cv_text": final_cv_text,
                                        "source": "Jobs.bg ZIP Archive"
                                    }
                                    
                                    res = supabase.table("hr_candidates").insert(candidate_data).execute()
                                    
                                    if res.data and target_pos_id:
                                        cand_id = res.data[0]["id"]
                                        supabase.table("hr_applications").insert({
                                            "candidate_id": cand_id,
                                            "position_id": target_pos_id,
                                            "status": "Нов"
                                        }).execute()
                                    count += 1
                                else:
                                    errors_log.append(f"⚠️ Архивът {uploaded_file.name} не съдържа четими CV формати.")

                            except Exception as zip_err:
                                errors_log.append(f"❌ Грешка при отваряне на архив {uploaded_file.name}: {zip_err}")

                    if count > 0:
                        st.success(f"🎉 Успешно създадени {count} пълни профили на кандидати!")
                    else:
                        st.warning("⚠️ Не бяха импортирани кандидати. Проверете детайлите по-долу.")
                        
                    if errors_log:
                        with st.expander("Виж детайли за отхвърлените файлове / грешките"):
                            for err in errors_log:
                                st.write(err)
        else:
            st.info("Нямате права за внос на кандидати.")

    # --- ТАБ: КАНБАН ---
    with tabs[0]:
        st.subheader("Процес по подбор")
        if has_positions:
            selected_kanban_pos = st.selectbox("Филтър по позиция", [p["title"] for p in positions_df.data], key="kanban_filter")
            
            # ОПТИМИЗАЦИЯ 2: Взимаме ID-то на позицията и филтрираме директно в базата данни!
            selected_pos_id = None
            for p in positions_df.data:
                if p["title"] == selected_kanban_pos:
                    selected_pos_id = p["id"]
                    break
                    
            if selected_pos_id:
                try:
                    # Теглим само тези апликации, които са за конкретната позиция. Базата работи бързо!
                    apps_query = supabase.table("hr_applications").select(
                        "*, hr_candidates(full_name, cv_text), hr_positions(title)"
                    ).eq("position_id", selected_pos_id).limit(100000).execute()
                    
                    if apps_query.data:
                        apps_df = pd.DataFrame(apps_query.data)
                        
                        if 'hr_positions' not in apps_df.columns or 'hr_candidates' not in apps_df.columns:
                            st.error("⚠️ Базата данни е празна или липсват Foreign Keys.")
                        else:
                            if "status" not in apps_df.columns:
                                apps_df["status"] = "Нов"
                            if "ai_score" not in apps_df.columns:
                                apps_df["ai_score"] = None

                            cols = st.columns(4)
                            statuses = ["Нов", "Интервю", "Одобрен", "Отхвърлен"]
                            
                            for i, status in enumerate(statuses):
                                with cols[i]:
                                    st.markdown(f"**{status}**")
                                    status_apps = apps_df[apps_df["status"] == status]
                                    for _, app in status_apps.iterrows():
                                        
                                        cand_name = app.get('hr_candidates', {}).get('full_name', 'Неизвестен') if isinstance(app.get('hr_candidates'), dict) else 'Неизвестен'
                                        cv_text = app.get('hr_candidates', {}).get('cv_text', 'Няма данни') if isinstance(app.get('hr_candidates'), dict) else 'Няма данни'
                                        
                                        formatted_cv = cv_text.replace('\n', '  \n')
                                        
                                        with st.expander(f"👤 {cand_name}"):
                                            if check_permission("recruitment", "evaluate"):
                                                current_status = app.get("status", "Нов")
                                                if current_status not in statuses:
                                                    current_status = "Нов"
                                                    
                                                new_status = st.selectbox("Статус", statuses, index=statuses.index(current_status), key=f"status_{app.get('id', i)}", label_visibility="collapsed")
                                                if new_status != current_status:
                                                    supabase.table("hr_applications").update({"status": new_status}).eq("id", app["id"]).execute()
                                                    st.rerun()
                                            
                                            with st.popover("📄 Прочети пълно досие (CV + Въпросници)", use_container_width=True):
                                                st.markdown(f"### Пълно досие на {cand_name}")
                                                st.markdown("---")
                                                st.markdown(formatted_cv)
                                            
                                            if check_permission("recruitment", "evaluate"):
                                                if st.button("✨ AI Анализ и БГ Превод", key=f"ai_{app.get('id', i)}", use_container_width=True):
                                                    st.info("Връзка с Gemini API... (Очакваме интеграция)")
                                                    mock_ai = f"**🤖 AI Резюме (на Български):**\nКандидатът има нужния опит, но му липсват специфични технически умения. Оценка: 7/10."
                                                    supabase.table("hr_applications").update({"ai_score": mock_ai}).eq("id", app["id"]).execute()
                                                    st.success("Анализът е готов!")
                                                    st.rerun()

                                            if app.get("ai_score"):
                                                st.success(app['ai_score'])

                    else:
                        st.info("Няма кандидати за тази позиция.")
                except Exception as e:
                     st.error(f"Грешка при зареждане на Канбан дъската: {e}")
            else:
                 st.warning("Изберете валидна позиция.")
        else:
            st.warning("Създайте позиция, за да заредите Канбан дъската.")

    # --- ТАБ: БАЗА КАНДИДАТИ ---
    with tabs[1]:
        st.subheader("Всички кандидати в системата")
        try:
            # Избягваме теглене на гигантските текстове на CV-тата за таблицата с общ преглед
            candidates_data = supabase.table("hr_candidates").select("id, full_name, source, created_at").limit(100000).execute()
            if candidates_data.data:
                df_c = pd.DataFrame(candidates_data.data)
                cols_to_show_c = [c for c in ["full_name", "source", "created_at"] if c in df_c.columns]
                st.dataframe(df_c[cols_to_show_c])
            else:
                st.info("Все още няма качени кандидати в базата.")
        except Exception as e:
            st.error(f"Грешка при зареждане на кандидати: {e}")
            
    # --- ОПАСНА ЗОНА (СУПЕР-АДМИН) ---
    with tabs[4]:
        st.subheader("Административни настройки")
        if st.session_state.get("user_role") == "Супер-админ":
            st.warning("Внимание: Всички записи ще бъдат изтрити безвъзвратно!")
            if st.button("Изчисти всички тестови кандидати (Hard Delete)"):
                with st.spinner("Изтриване на данни..."):
                    apps = supabase.table("hr_applications").select("id").limit(100000).execute()
                    if apps.data:
                        for a in apps.data:
                            supabase.table("hr_applications").delete().eq("id", a["id"]).execute()
                            
                    cands = supabase.table("hr_candidates").select("id").limit(100000).execute()
                    if cands.data:
                        for c in cands.data:
                            supabase.table("hr_candidates").delete().eq("id", c["id"]).execute()
                            
                st.success("Базата е напълно изчистена! Можете да внесете ZIP архива наново.")
                st.rerun()
        else:
            st.info("Само за Супер-админ")

if __name__ == "__main__":
    render_recruitment_module()
