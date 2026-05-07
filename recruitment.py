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
import google.generativeai as genai

def render_recruitment_module():
    st.header("📋 Модул Рекрутмънт и Подбор (ATS)")

    if not check_permission("recruitment", "read"):
        st.error("Нямате достъп до този модул.")
        return

    tabs = st.tabs(["📊 Канбан", "👥 База Кандидати", "💼 Позиции", "📥 Внос (Jobs.bg)", "⚙️ Настройки"])

    # --- КОНФИГУРАЦИЯ НА AI ---
    api_key = st.secrets.get("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        ai_ready = True
    else:
        ai_ready = False

    # --- ИЗВЛИЧАНЕ НА ПОЗИЦИИТЕ ---
    try:
        positions_df = supabase.table("hr_positions").select("*").limit(1000).execute()
        has_positions = bool(positions_df.data)
    except Exception as e:
        st.error(f"Грешка при връзка с базата: {e}")
        has_positions = False

    # --- ТАБ: ПОЗИЦИИ ---
    with tabs[2]:
        st.subheader("Управление на отворени позиции")
        if check_permission("recruitment", "manage_positions"):
            with st.form("add_position"):
                pos_name = st.text_input("Име на позицията")
                pos_req = st.text_area("Изисквания (за AI оценка)")
                if st.form_submit_button("Създай позиция") and pos_name:
                    supabase.table("hr_positions").insert({"title": pos_name, "requirements": pos_req}).execute()
                    st.success("Позицията е създадена!")
                    st.rerun()
        
        if has_positions:
            st.table(pd.DataFrame(positions_df.data)[["title", "requirements", "created_at"]])

    # --- ТАБ: ВНОС (1 ZIP = 1 Кандидат) ---
    with tabs[3]:
        st.subheader("Внос от Jobs.bg")
        if check_permission("recruitment", "upload_candidates"):
            target_pos = st.selectbox("Позиция за вноса", [p["title"] for p in positions_df.data] if has_positions else ["Няма позиции"])
            uploaded_files = st.file_uploader("Качи ZIP архиви", type="zip", accept_multiple_files=True)

            if uploaded_files and st.button("Стартирай импорт"):
                target_pos_id = next((p["id"] for p in positions_df.data if p["title"] == target_pos), None)
                count = 0
                with st.spinner("Сглобяване на досиета..."):
                    for uploaded_file in uploaded_files:
                        text_parts = []
                        # Име от ZIP
                        raw_name = uploaded_file.name.replace(".zip", "").replace(".ZIP", "")
                        candidate_name = re.sub(r'_[0-9\.\-]+$', '', raw_name).replace('_', ' ').strip()
                        has_name = bool(candidate_name)

                        try:
                            with zipfile.ZipFile(uploaded_file, "r") as z:
                                for file_name in z.namelist():
                                    b_low = file_name.split('/')[-1].lower()
                                    if b_low in ["jobs.bg", "business.jobs.bg"] or b_low.endswith(".url"): continue
                                    
                                    t = ""
                                    if b_low.endswith((".html", ".htm")):
                                        with z.open(file_name) as f:
                                            soup = BeautifulSoup(f.read().decode("utf-8", errors="ignore"), "html.parser")
                                            for br in soup.find_all("br"): br.replace_with("\n")
                                            t = html.unescape(soup.get_text(separator=' ')).replace('\xa0', ' ')
                                            if not has_name:
                                                ext = soup.title.string.replace("Jobs.bg - ", "").strip() if soup.title else ""
                                                if ext and ext.lower() not in ["jobs.bg", "business.jobs.bg"]:
                                                    candidate_name = ext
                                                    has_name = True
                                    elif b_low.endswith(".pdf"):
                                        with z.open(file_name) as f:
                                            pdf = PyPDF2.PdfReader(f)
                                            t = "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
                                    elif b_low.endswith(".docx"):
                                        with z.open(file_name) as f:
                                            doc = docx.Document(io.BytesIO(f.read()))
                                            t = "\n".join([p.text for p in doc.paragraphs])
                                    elif b_low.endswith(".doc"):
                                        with z.open(file_name) as f:
                                            raw_b = f.read()
                                            dec = raw_b.decode("utf-8", errors="ignore")
                                            if "<html" in dec.lower(): t = html.unescape(BeautifulSoup(dec, "html.parser").get_text(separator=' '))
                                            else: t = re.sub(r'[^\w\s\.,!?-]', ' ', raw_b.decode("windows-1251", errors="ignore"))

                                    if t:
                                        t = t.replace('\x00', '').replace('\u0000', '')
                                        text_parts.append(re.sub(r' +', ' ', t).strip())

                            if text_parts:
                                final_cv = "\n\n--- НОВ ДОКУМЕНТ ---\n\n".join(text_parts)
                                res = supabase.table("hr_candidates").insert({"full_name": candidate_name, "cv_text": final_cv, "source": "Jobs.bg ZIP"}).execute()
                                if res.data and target_pos_id:
                                    supabase.table("hr_applications").insert({"candidate_id": res.data[0]["id"], "position_id": target_pos_id, "status": "Нов"}).execute()
                                count += 1
                        except Exception as e: st.error(f"Грешка при {uploaded_file.name}: {e}")
                st.success(f"Импортирани {count} кандидати!")
                st.rerun()

    # --- ТАБ: КАНБАН ---
    with tabs[0]:
        st.subheader("Процес по подбор")
        if has_positions:
            selected_pos = st.selectbox("Филтър по позиция", [p["title"] for p in positions_df.data])
            pos_data = next((p for p in positions_df.data if p["title"] == selected_pos), None)
            
            if pos_data:
                apps = supabase.table("hr_applications").select("*, hr_candidates(full_name, cv_text)").eq("position_id", pos_data["id"]).execute()
                if apps.data:
                    df = pd.DataFrame(apps.data)
                    cols = st.columns(4)
                    statuses = ["Нов", "Интервю", "Одобрен", "Отхвърлен"]
                    
                    for i, stat in enumerate(statuses):
                        with cols[i]:
                            st.markdown(f"**{stat}**")
                            stat_df = df[df["status"] == stat] if "status" in df.columns else pd.DataFrame()
                            for _, app in stat_df.iterrows():
                                cand = app["hr_candidates"]
                                with st.expander(f"👤 {cand['full_name']}"):
                                    if check_permission("recruitment", "evaluate"):
                                        new_stat = st.selectbox("Статус", statuses, index=statuses.index(stat), key=f"st_{app['id']}", label_visibility="collapsed")
                                        if new_stat != stat:
                                            supabase.table("hr_applications").update({"status": new_stat}).eq("id", app["id"]).execute()
                                            st.rerun()
                                    
                                    with st.popover("📄 Пълно Досие", use_container_width=True):
                                        st.markdown(cand["cv_text"].replace('\n', '  \n'))
                                    
                                    if check_permission("recruitment", "evaluate"):
                                        if st.button("✨ AI Анализ (БГ)", key=f"ai_{app['id']}", use_container_width=True):
                                            if not ai_ready: st.error("Липсва API Key!")
                                            else:
                                                with st.spinner("AI анализира..."):
                                                    prompt = f"Ти си опитен HR. СРАВНИ CV: {cand['cv_text']} С ИЗИСКВАНИЯ: {pos_data['requirements']}. ДАЙ НА БЪЛГАРСКИ: Резюме, Силни страни, Рискове и Оценка 1-10."
                                                    response = model.generate_content(prompt)
                                                    supabase.table("hr_applications").update({"ai_score": response.text}).eq("id", app["id"]).execute()
                                                    st.rerun()

                                    if app.get("ai_score"):
                                        st.success(app["ai_score"])
