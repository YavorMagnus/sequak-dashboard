import streamlit as st
import pandas as pd
from utils import supabase, check_permission
import zipfile
import io
from bs4 import BeautifulSoup
import PyPDF2
import re

# ЗАБЕЛЕЖКА: Gemini API Key трябва да бъде добавен в st.secrets за сигурност
# import google.generativeai as genai

def render_recruitment_module():
    st.header("📋 Модул Рекрутмънт и Подбор (ATS)")

    # Проверка на правата
    if not check_permission("recruitment", "read"):
        st.error("Нямате достъп до този модул.")
        return

    tabs = st.tabs(["📊 Канбан", "👥 База Кандидати", "💼 Позиции", "📥 Внос (Jobs.bg)", "⚙️ Настройки"])

    # --- ИЗВЛИЧАНЕ НА ПОЗИЦИИТЕ ГЛОБАЛНО (Нужни са за Канбан и Внос) ---
    try:
        positions_df = supabase.table("hr_positions").select("*").limit(100000).execute()
        has_positions = bool(positions_df.data)
    except Exception as e:
        st.error(f"Грешка при връзка с таблица hr_positions: {e}")
        has_positions = False

    # --- ТАБ: ПОЗИЦИИ ---
    with tabs[2]:
        st.subheader("Управление на отворени позиции")
        
        # Визуализираме формата за създаване САМО ако потребителят има право "manage_positions"
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
                        st.error(f"Грешка при запис (Проверете дали имате колона 'requirements' в Supabase): {e}")
        else:
            st.info("Нямате права за създаване на нови позиции. Режим на четене.")

        if has_positions:
            df_p = pd.DataFrame(positions_df.data)
            # Защита: Показваме само колоните, които реално съществуват в DataFrame-а
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
            
            uploaded_file = st.file_uploader("Качи ZIP архив", type="zip")

            if uploaded_file and st.button("Стартирай импорт"):
                if not has_positions:
                    st.warning("Моля, първо създайте позиция в таб 'Позиции', към която да прикачите кандидатите.")
                else:
                    with zipfile.ZipFile(uploaded_file, "r") as z:
                        count = 0
                        for file_name in z.namelist():
                            # 1. Парсване на HTML файлове
                            if file_name.lower().endswith((".html", ".htm")):
                                with z.open(file_name) as f:
                                    html_content = f.read().decode("utf-8", errors="ignore")
                                    soup = BeautifulSoup(html_content, "html.parser")
                                    
                                    for br in soup.find_all("br"):
                                        br.replace_with("\n")
                                    for p in soup.find_all(["p", "div", "tr"]):
                                        p.append("\n")
                                    
                                    raw_text = soup.get_text(separator=' ')
                                    clean_text = re.sub(r' +', ' ', raw_text)
                                    clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text).strip()
                                    candidate_name = soup.title.string.replace("Jobs.bg - ", "") if soup.title else "Неизвестен"
                                    
                                    try:
                                        candidate_data = {
                                            "full_name": candidate_name,
                                            "cv_text": clean_text,
                                            "source": "Jobs.bg HTML"
                                        }
                                        res = supabase.table("hr_candidates").upsert(candidate_data, on_conflict="full_name").execute()
                                        
                                        if res.data:
                                            cand_id = res.data[0]["id"]
                                            pos_id_data = supabase.table("hr_positions").select("id").eq("title", target_pos).execute()
                                            if pos_id_data.data:
                                                supabase.table("hr_applications").insert({
                                                    "candidate_id": cand_id,
                                                    "position_id": pos_id_data.data[0]["id"],
                                                    "status": "Нов"
                                                }).execute()
                                        count += 1
                                    except Exception as e:
                                        continue
                            
                            # 2. Парсване на PDF файлове
                            elif file_name.lower().endswith(".pdf"):
                                with z.open(file_name) as f:
                                    try:
                                        pdf_reader = PyPDF2.PdfReader(f)
                                        raw_text = ""
                                        for page in pdf_reader.pages:
                                            extracted = page.extract_text()
                                            if extracted:
                                                raw_text += extracted + "\n"
                                        
                                        clean_text = re.sub(r' +', ' ', raw_text)
                                        clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text).strip()
                                        candidate_name = file_name.split('/')[-1].replace(".pdf", "").replace(".PDF", "")
                                        
                                        candidate_data = {
                                            "full_name": candidate_name,
                                            "cv_text": clean_text,
                                            "source": "Jobs.bg PDF"
                                        }
                                        res = supabase.table("hr_candidates").upsert(candidate_data, on_conflict="full_name").execute()
                                        
                                        if res.data:
                                            cand_id = res.data[0]["id"]
                                            pos_id_data = supabase.table("hr_positions").select("id").eq("title", target_pos).execute()
                                            if pos_id_data.data:
                                                supabase.table("hr_applications").insert({
                                                    "candidate_id": cand_id,
                                                    "position_id": pos_id_data.data[0]["id"],
                                                    "status": "Нов"
                                                }).execute()
                                        count += 1
                                    except Exception as e:
                                        continue

                        st.success(f"Успешно обработени {count} кандидати!")
        else:
            st.info("Нямате права за внос на кандидати.")

    # --- ТАБ: КАНБАН ---
    with tabs[0]:
        st.subheader("Процес по подбор")
        if has_positions:
            selected_kanban_pos = st.selectbox("Филтър по позиция", [p["title"] for p in positions_df.data], key="kanban_filter")
            
            try:
                apps_query = supabase.table("hr_applications").select("*, hr_candidates(full_name, cv_text), hr_positions(title)").limit(100000).execute()
                
                if apps_query.data:
                    apps_df = pd.DataFrame(apps_query.data)
                    
                    if 'hr_positions' not in apps_df.columns or 'hr_candidates' not in apps_df.columns:
                        st.error("⚠️ Базата данни е празна или липсват Foreign Keys (релации) между таблиците hr_applications, hr_positions и hr_candidates в Supabase.")
                    else:
                        # ДЕФАНЗИВНО ПРОГРАМИРАНЕ: Ако колоните липсват, ги създаваме виртуално
                        if "status" not in apps_df.columns:
                            apps_df["status"] = "Нов"
                        if "ai_score" not in apps_df.columns:
                            apps_df["ai_score"] = None

                        apps_df = apps_df[apps_df['hr_positions'].apply(lambda x: x.get('title') == selected_kanban_pos if isinstance(x, dict) else False)]
                        
                        cols = st.columns(4)
                        statuses = ["Нов", "Интервю", "Одобрен", "Отхвърлен"]
                        
                        for i, status in enumerate(statuses):
                            with cols[i]:
                                st.markdown(f"**{status}**")
                                status_apps = apps_df[apps_df["status"] == status]
                                for _, app in status_apps.iterrows():
                                    
                                    cand_name = app.get('hr_candidates', {}).get('full_name', 'Неизвестен') if isinstance(app.get('hr_candidates'), dict) else 'Неизвестен'
                                    cv_text = app.get('hr_candidates', {}).get('cv_text', 'Няма данни') if isinstance(app.get('hr_candidates'), dict) else 'Няма данни'
                                    
                                    with st.expander(f"👤 {cand_name}"):
                                        st.write(f"ID: {app.get('id', 'N/A')}")
                                        
                                        # Редакция на статус (изисква evaluate права, защото е местене по канбан)
                                        if check_permission("recruitment", "evaluate"):
                                            current_status = app.get("status", "Нов")
                                            # Защита: Ако статусът в базата не е в списъка, слагаме го на "Нов"
                                            if current_status not in statuses:
                                                current_status = "Нов"
                                                
                                            new_status = st.selectbox("Промени статус", statuses, index=statuses.index(current_status), key=f"status_{app.get('id', i)}")
                                            if new_status != current_status:
                                                supabase.table("hr_applications").update({"status": new_status}).eq("id", app["id"]).execute()
                                                st.rerun()
                                        
                                        # --- AI ОЦЕНКА ---
                                        if check_permission("recruitment", "evaluate"):
                                            if st.button("✨ Генерирай AI Оценка", key=f"ai_{app.get('id', i)}"):
                                                st.info("Връзка с Gemini API... (Подготвяме данните)")
                                                
                                                # Извличаме изискванията безопасно от вече заредените позиции
                                                req_text = "Няма въведени изисквания"
                                                for p in positions_df.data:
                                                    if p.get("title") == selected_kanban_pos:
                                                        req_text = p.get("requirements", "Няма въведени изисквания")
                                                        break
                                                
                                                # Тук ще подадем cv_text и req_text към Gemini API
                                                mock_ai = f"Оценка: 8/10. (Матрица: {req_text[:30]}...) Кандидатът изглежда добре."
                                                
                                                supabase.table("hr_applications").update({"ai_score": mock_ai}).eq("id", app["id"]).execute()
                                                st.success("Оценката е генерирана!")
                                                st.rerun()

                                        if app.get("ai_score"):
                                            st.info(f"AI Анализ: {app['ai_score']}")

                                        if st.checkbox("Виж извлечено CV", key=f"cv_{app.get('id', i)}"):
                                            st.text_area("Текст от CV (структуриран):", value=cv_text, height=300)
                else:
                    st.info("Няма кандидати за тази позиция.")
            except Exception as e:
                 st.error(f"Грешка при зареждане на Канбан дъската: {e}")
        else:
            st.warning("Създайте позиция, за да заредите Канбан дъската.")

    # --- ТАБ: БАЗА КАНДИДАТИ ---
    with tabs[1]:
        st.subheader("Всички кандидати в системата")
        try:
            candidates_data = supabase.table("hr_candidates").select("*").limit(100000).execute()
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
            st.warning("Внимание: Hard Delete зона")
            if st.button("Изчисти всички тестови кандидати"):
                st.error("Функцията е деактивирана за сигурност. Свържете се с CTO.")
        else:
            st.info("Само за Супер-админ")

# Стартиране на модула (ако се вика директно за тест)
if __name__ == "__main__":
    render_recruitment_module()
