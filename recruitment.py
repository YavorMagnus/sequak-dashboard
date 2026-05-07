import streamlit as st
import pandas as pd
from utils import supabase, check_permission
import zipfile
import io
import json
import base64
import fitz  # PyMuPDF за четене на PDF и вадене на снимки
from bs4 import BeautifulSoup

# --- ТВОИТЕ ФИРМИ ---
COMPANIES = [
    "Фирма 1 (Строителство)", 
    "Фирма 2 (Логистика)", 
    "Фирма 3 (Търговия)", 
    "Холдинг Център"
]

# --- УМНИЯТ ПАРСЪР (Функция) ---
def parse_jobs_zip(uploaded_file):
    raw_name = uploaded_file.name.replace(".zip", "").replace(".ZIP", "")
    candidate_name = raw_name.replace('_', ' ').strip()
    
    cv_data = {
        "questionnaire": "Няма намерен въпросник.",
        "notes": "Няма намерени бележки.",
        "cv_text": "Няма намерен текст на CV.",
    }
    photo_base64 = None

    with zipfile.ZipFile(uploaded_file, "r") as z:
        for file_name in z.namelist():
            lower_name = file_name.split('/')[-1].lower()
            if lower_name.endswith(".url") or lower_name in ["jobs.bg", "business.jobs.bg"]: 
                continue
            
            # Четене на HTML (Въпросници и Бележки)
            if lower_name.endswith((".html", ".htm")):
                with z.open(file_name) as f:
                    html_content = f.read().decode("utf-8", errors="ignore")
                    soup = BeautifulSoup(html_content, "html.parser")
                    text_content = soup.get_text(separator='\n', strip=True)
                    
                    if "въпрос" in text_content.lower() or "question" in text_content.lower():
                        cv_data["questionnaire"] = text_content
                    else:
                        cv_data["notes"] = text_content

            # Четене на PDF (Текст и Снимки)
            elif lower_name.endswith(".pdf"):
                with z.open(file_name) as f:
                    pdf_bytes = f.read()
                    try:
                        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                        pdf_text = ""
                        for page in doc:
                            pdf_text += page.get_text() + "\n"
                            # Опит за вадене на първата снимка
                            if not photo_base64:
                                images = page.get_images(full=True)
                                if images:
                                    xref = images[0][0]
                                    base_image = doc.extract_image(xref)
                                    image_bytes = base_image["image"]
                                    photo_base64 = base64.b64encode(image_bytes).decode("utf-8")
                        cv_data["cv_text"] = pdf_text.strip()
                    except Exception as e:
                        cv_data["cv_text"] = f"Грешка при четене на PDF: {e}"

    return candidate_name, cv_data, photo_base64

# --- THE MODAL: ГОЛЕМИЯТ КАРТОН ---
@st.dialog("📄 Картон на кандидата", width="large")
def open_candidate_card(candidate_id, candidate_name, status, raw_cv_data, photo_base64):
    col_img, col_info = st.columns([1, 4])
    with col_img:
        if photo_base64:
            st.markdown(f'<img src="data:image/png;base64,{photo_base64}" style="width:100%; border-radius:10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">', unsafe_allow_html=True)
        else:
            st.info("Няма снимка")
            
    with col_info:
        st.subheader(f"👤 {candidate_name}")
        st.caption(f"Текущ статус: **{status}**")
    
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.selectbox("Промени статус", ["Нов", "Телефонно интервю", "Живо интервю", "Одобрен", "Отхвърлен", "Преместен"], label_visibility="collapsed")
    with col2: st.button("💾 Запиши", use_container_width=True)
    with col3: st.button("✉️ Сподели", use_container_width=True)
    with col4: st.button("🗑️ Изтрий", type="primary", use_container_width=True)
        
    st.markdown("---")
    
    tabs = st.tabs(["📋 Въпросник", "📝 Бележки", "📄 CV", "📞 Интервюта", "📊 Скор-карта"])
    
    cv_dict = raw_cv_data if isinstance(raw_cv_data, dict) else {}
    
    with tabs[0]: st.write(cv_dict.get("questionnaire", "Няма данни"))
    with tabs[1]: st.write(cv_dict.get("notes", "Няма данни"))
    with tabs[2]: st.write(cv_dict.get("cv_text", "Няма данни"))
    with tabs[3]: st.write("Историята на интервютата ще се появи тук.")
    with tabs[4]: st.write("Слайдерите за оценка ще се появят тук.")

# --- ОСНОВЕН РЕНДЕР ---
def render_recruitment_module():
    st.header("📋 Модул Подбор (V4 Enterprise)")

    if not check_permission("recruitment", "read"):
        st.error("Нямате достъп до този модул.")
        return

    # 1. HOLDING VIEW
    st.write("### 🏢 Работен плот по дружества")
    selected_company = st.pills("Изберете компания", COMPANIES, default=None)

    if not selected_company:
        st.info("👈 Моля, изберете фирма от холдинга, за да заредите кампаниите.")
        return

    st.divider()

    # 2. PROJECT VIEW
    st.write(f"### 💼 Кампании за {selected_company}")
    
    if check_permission("recruitment", "manage_positions"):
        with st.expander("➕ Създай нова обява / кампания"):
            with st.form("new_pos_form"):
                pos_title = st.text_input("Име на позицията")
                pos_method = st.selectbox("Метод за оценка", ["Процентна матрица", "Обща оценка 1-10", "Свободен текст (за AI)"])
                if st.form_submit_button("Регистрирай"):
                    if pos_title:
                        supabase.table("hr_positions").insert({"company_name": selected_company, "title": pos_title, "evaluation_method": pos_method}).execute()
                        st.success("Създадена!")
                        st.rerun()

    pos_res = supabase.table("hr_positions").select("*").eq("company_name", selected_company).order("created_at", desc=True).execute()
    positions = pos_res.data if pos_res.data else []

    if not positions:
        st.warning("Няма създадени обяви.")
        return

    st.divider()
    selected_pos_title = st.selectbox("Разгледай кампания:", [p["title"] for p in positions])
    target_pos_id = next(p["id"] for p in positions if p["title"] == selected_pos_title)

    # --- ИМПОРТ НА КАНДИДАТИ ---
    if check_permission("recruitment", "upload_candidates"):
        with st.expander(f"📥 Импорт на ZIP към '{selected_pos_title}'"):
            uploaded_files = st.file_uploader("Качи ZIP архиви от Jobs.bg", type="zip", accept_multiple_files=True)
            if uploaded_files and st.button("Стартирай интелигентен внос"):
                with st.spinner("Парсване и извличане на снимки..."):
                    count = 0
                    for uf in uploaded_files:
                        cand_name, cv_data, photo = parse_jobs_zip(uf)
                        # Запис в hr_candidates
                        cand_res = supabase.table("hr_candidates").insert({
                            "full_name": cand_name, 
                            "source": "Jobs.bg ZIP", 
                            "raw_cv_data": cv_data,
                            "photo_thumbnail": photo
                        }).execute()
                        
                        if cand_res.data:
                            # Запис в hr_applications
                            supabase.table("hr_applications").insert({
                                "candidate_id": cand_res.data[0]["id"],
                                "position_id": target_pos_id,
                                "status": "Нов"
                            }).execute()
                            count += 1
                st.success(f"Успешно импортирани {count} досиета!")
                st.rerun()

    # --- GRID VIEW (Кандидатите) ---
    st.write("### 👥 Кандидати")
    status_filter = st.pills("Филтър по статус:", ["Всички", "Нов", "Телефонно интервю", "Живо интервю", "Одобрен", "Отхвърлен"], default="Всички")
    
    # Извличане на кандидатите за тази позиция
    apps_res = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("position_id", target_pos_id).execute()
    apps = apps_res.data if apps_res.data else []
    
    if apps:
        if status_filter != "Всички":
            apps = [a for a in apps if a["status"] == status_filter]
            
        cols = st.columns(4)
        for i, app in enumerate(apps):
            cand = app["hr_candidates"]
            with cols[i % 4]:
                st.markdown(f"**{cand['full_name']}**")
                st.caption(app['status'])
                if st.button("📄 Отвори", key=f"btn_{app['id']}", use_container_width=True):
                    open_candidate_card(
                        cand["id"], 
                        cand["full_name"], 
                        app["status"], 
                        cand["raw_cv_data"], 
                        cand["photo_thumbnail"]
                    )
    else:
        st.info("Няма кандидати в тази кампания.")

if __name__ == "__main__":
    render_recruitment_module()
