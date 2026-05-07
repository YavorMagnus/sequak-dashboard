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

    if not check_permission("recruitment_view"):
        st.error("Нямате достъп до този модул.")
        return

    tabs = st.tabs(["📊 Канбан", "👥 База Кандидати", "💼 Позиции", "📥 Внос (Jobs.bg)", "⚙️ Настройки"])

    # --- ТАБ: ПОЗИЦИИ ---
    with tabs[2]:
        st.subheader("Управление на отворени позиции")
        with st.form("add_position"):
            pos_name = st.text_input("Име на позицията (напр. Механик, Търговски представител)")
            pos_req = st.text_area("Изисквания (Матрица за AI оценка)")
            submit_pos = st.form_submit_button("Създай позиция")

            if submit_pos and pos_name:
                supabase.table("hr_positions").insert({"title": pos_name, "requirements": pos_req}).execute()
                st.success("Позицията е създадена!")
                st.rerun()

        positions_df = supabase.table("hr_positions").select("*").limit(100000).execute()
        if positions_df.data:
            df_p = pd.DataFrame(positions_df.data)
            st.table(df_p[["title", "requirements", "created_at"]])

    # --- ТАБ: ВНОС ---
    with tabs[3]:
        st.subheader("Масово качване на кандидати от Jobs.bg (ZIP)")
        target_pos = st.selectbox("Избери позиция за вноса", [p["title"] for p in positions_df.data] if positions_df.data else ["Няма активни позиции"])
        uploaded_file = st.file_uploader("Качи ZIP архив", type="zip")

        if uploaded_file and st.button("Стартирай импорт"):
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
                                # При PDF нямаме лесен <title>, затова ползваме името на файла
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

    # --- ТАБ: КАНБАН ---
    with tabs[0]:
        st.subheader("Процес по подбор")
        if positions_df.data:
            selected_kanban_pos = st.selectbox("Филтър по позиция", [p["title"] for p in positions_df.data], key="kanban_filter")
            
            apps_query = supabase.table("hr_applications").select("*, hr_candidates(full_name, cv_text), hr_positions(title, requirements)").limit(100000).execute()
            
            if apps_query.data:
                apps_df = pd.DataFrame(apps_query.data)
                apps_df = apps_df[apps_df['hr_positions'].apply(lambda x: x['title'] == selected_kanban_pos if isinstance(x, dict) else False)]
                
                cols = st.columns(4)
                statuses = ["Нов", "Интервю", "Одобрен", "Отхвърлен"]
                
                for i, status in enumerate(statuses):
                    with cols[i]:
                        st.markdown(f"**{status}**")
                        status_apps = apps_df[apps_df["status"] == status]
                        for _, app in status_apps.iterrows():
                            with st.expander(f"👤 {app['hr_candidates']['full_name']}"):
                                st.write(f"ID: {app['id']}")
                                
                                new_status = st.selectbox("Промени статус", statuses, index=statuses.index(status), key=f"status_{app['id']}")
                                if new_status != status:
                                    supabase.table("hr_applications").update({"status": new_status}).eq("id", app["id"]).execute()
                                    st.rerun()

                                # --- AI ОЦЕНКА ---
                                if st.button("✨ Генерирай AI Оценка", key=f"ai_{app['id']}"):
                                    st.info("Връзка с Gemini API... (Тук се изпраща CV + Изисквания)")
                                    
                                    # За момента симулираме запис:
                                    mock_ai = "Оценка: 8/10. Кандидатът има отличен опит с машини, но липсва опит в онлайн ритейла."
                                    supabase.table("hr_applications").update({"ai_score": mock_ai}).eq("id", app["id"]).execute()
                                    st.success("Оценката е генерирана!")
                                    st.rerun()

                                if app.get("ai_score"):
                                    st.info(f"AI Анализ: {app['ai_score']}")

                                if st.checkbox("Виж извлечено CV", key=f"cv_{app['id']}"):
                                    st.text_area("Текст от CV (структуриран):", value=app['hr_candidates']['cv_text'], height=300)

    # --- ТАБ: БАЗА КАНДИДАТИ ---
    with tabs[1]:
        st.subheader("Всички кандидати в системата")
        candidates_data = supabase.table("hr_candidates").select("*").limit(100000).execute()
        if candidates_data.data:
            df_c = pd.DataFrame(candidates_data.data)
            st.dataframe(df_c[["full_name", "source", "created_at"]])
            
    # --- ОПАСНА ЗОНА (СУПЕР-АДМИН) ---
    with tabs[4]:
        st.subheader("Административни настройки")
        if check_permission("super_admin"):  # Ползваме твоята логика от utils
            st.warning("Внимание: Hard Delete зона")
            if st.button("Изчисти всички тестови кандидати"):
                st.error("Функцията е деактивирана за сигурност. Свържете се с CTO.")
        else:
            st.info("Само за Супер-админ")

# Стартиране на модула (ако се вика директно за тест)
if __name__ == "__main__":
    render_recruitment_module()
