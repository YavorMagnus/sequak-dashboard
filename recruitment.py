import streamlit as st
import pandas as pd
from utils import supabase, check_permission
import zipfile
import io
import base64
import fitz  # PyMuPDF
from bs4 import BeautifulSoup
import re

# --- ТВОИТЕ ФИРМИ ---
COMPANIES = [
    "Фирма 1 (Строителство)", 
    "Фирма 2 (Логистика)", 
    "Фирма 3 (Търговия)", 
    "Холдинг Център"
]

# --- УМНО ИЗЧИСТВАНЕ НА HTML (V6 - Без убиеца на нови редове) ---
def clean_html_text(html_bytes):
    soup = BeautifulSoup(html_bytes.decode("utf-8", errors="ignore"), "html.parser")
    
    for tag in soup(["script", "style", "head", "noscript", "title"]):
        tag.extract()
        
    for label in soup.find_all("label"):
        label.insert_before("**")
        label.insert_after("**")
        label.unwrap()

    for h5 in soup.find_all("h5"):
        h5.insert_before("\n\n### ")
        h5.insert_after("\n\n")
        h5.unwrap()

    for h6 in soup.find_all("h6"):
        h6.insert_before("\n\n**")
        h6.insert_after("**\n")
        h6.unwrap()

    for overline in soup.find_all(class_="overline"):
        overline.insert_before("\n*")
        overline.insert_after("*\n")
        overline.unwrap()

    for item in soup.find_all(class_="item"):
        item.insert_before("\n- ")
        item.insert_after("\n")
        item.unwrap()
        
    for br in soup.find_all("br"):
        br.replace_with("\n")
        
    for block in soup.find_all(["div", "p", "tr", "li", "h1", "h2", "h3", "h4"]):
        block.insert_after("\n")
        
    text = soup.get_text(separator=' ')
    
    text = re.sub(r'[ \t]+', ' ', text)         
    text = re.sub(r'\*\* +', '**', text)        
    text = re.sub(r' +\*\*', '**', text)        
    text = re.sub(r'\* +', '*', text)           
    text = re.sub(r' +\*', '*', text)           
    text = text.replace('** :', '**: ')         
    text = re.sub(r' \n', '\n', text)           
    text = re.sub(r'\n ', '\n', text)           
    text = re.sub(r'\n{3,}', '\n\n', text)      
    
    text = text.replace('\n', '  \n')
    
    return text.strip()

# --- УМНИЯТ ПАРСЪР ---
def parse_jobs_zip(uploaded_file):
    raw_name = uploaded_file.name.replace(".zip", "").replace(".ZIP", "")
    name_no_dates = re.sub(r'_[0-9]{2}\.[0-9]{2}\.[0-9]{4}.*', '', raw_name)
    clean_name = re.sub(r'^[0-9]+_', '', name_no_dates).replace('_', ' ').strip()
    if not clean_name: 
        clean_name = raw_name 
    
    cv_data = {
        "questionnaire": "Няма прикачен въпросник.",
        "notes": "Няма намерени бележки.",
        "cv_text": "Няма намерен текст на CV.",
    }
    photo_base64 = None
    has_pdf_cv = False
    html_profile_text = ""

    with zipfile.ZipFile(uploaded_file, "r") as z:
        for file_name in z.namelist():
            lower_name = file_name.split('/')[-1].lower()
            if lower_name.endswith(".url") or lower_name in ["jobs.bg", "business.jobs.bg"]: 
                continue
                
            if lower_name.endswith((".jpg", ".jpeg", ".png")) and not photo_base64:
                with z.open(file_name) as f:
                    photo_base64 = base64.b64encode(f.read()).decode("utf-8")
            
            elif lower_name.endswith((".html", ".htm")):
                with z.open(file_name) as f:
                    text_content = clean_html_text(f.read())
                    
                    if "въпросник" in lower_name or "questionnaire" in lower_name:
                        idx = text_content.find("Въпросник")
                        if idx == -1:
                            idx = text_content.find("Questionnaire")
                            
                        if idx != -1: 
                            text_content = text_content[idx:]
                        
                        text_content = re.sub(r'\s*(\d+\.\s)', r'\n\n\1', text_content)
                        text_content = re.sub(r'(\?[*]?)\s+(.*)', r'\1 **\2**', text_content)
                        cv_data["questionnaire"] = text_content.replace('\n', '  \n')
                        
                    elif "notes" in lower_name or "бележки" in lower_name:
                        cv_data["notes"] = text_content.replace('\n', '  \n')
                        
                    elif "профил" in lower_name or "profile" in lower_name:
                        html_profile_text = text_content

            elif lower_name.endswith(".pdf"):
                with z.open(file_name) as f:
                    pdf_bytes = f.read()
                    try:
                        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                        pdf_text = ""
                        for page in doc:
                            pdf_text += page.get_text().replace('\n', '  \n') + "\n\n"
                            
                            if not photo_base64:
                                images = page.get_images(full=True)
                                if images:
                                    xref = images[0][0]
                                    base_image = doc.extract_image(xref)
                                    photo_base64 = base64.b64encode(base_image["image"]).decode("utf-8")
                                    
                        cv_data["cv_text"] = pdf_text.strip()
                        has_pdf_cv = True
                    except Exception as e:
                        pass 

    if not has_pdf_cv and html_profile_text:
        cv_data["cv_text"] = html_profile_text
        
    return clean_name.title(), cv_data, photo_base64

# --- THE MODAL: ГОЛЕМИЯТ КАРТОН С ЕКШЪН ЛОГИКА ---
@st.dialog("📄 Картон на кандидата", width="large")
def open_candidate_card(app_id, candidate_id, candidate_name, status, raw_cv_data, photo_base64):
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
    
    # --- ЕКШЪН ПАНЕЛ ---
    col1, col2, col3, col4 = st.columns(4)
    statuses_list = ["Нов", "Телефонно интервю", "Живо интервю", "Одобрен", "Отхвърлен", "Преместен"]
    current_idx = statuses_list.index(status) if status in statuses_list else 0
    
    with col1: 
        new_status = st.selectbox("Промени статус", statuses_list, index=current_idx, label_visibility="collapsed")
    with col2: 
        if st.button("💾 Запиши", use_container_width=True):
            supabase.table("hr_applications").update({"status": new_status}).eq("id", app_id).execute()
            st.rerun()
    with col3: 
        st.button("✉️ Сподели", use_container_width=True)
    with col4: 
        if st.button("🗑️ Изтрий", type="primary", use_container_width=True):
            # Изтриваме записа от базата данни
            supabase.table("hr_candidates").delete().eq("id", candidate_id).execute()
            st.rerun()
        
    st.markdown("---")
    
    tabs = st.tabs(["📋 Въпросник", "📝 Бележки", "📄 CV", "📞 Интервюта", "📊 Скор-карта"])
    
    cv_dict = raw_cv_data if isinstance(raw_cv_data, dict) else {}
    
    with tabs[0]: 
        st.markdown(cv_dict.get("questionnaire", "Няма данни"))
    with tabs[1]: 
        st.markdown(cv_dict.get("notes", "Няма данни"))
    with tabs[2]: 
        st.markdown(cv_dict.get("cv_text", "Няма данни"))
    with tabs[3]: 
        st.write("Историята на интервютата ще се появи тук.")
    with tabs[4]: 
        st.write("Слайдерите за оценка ще се появят тук.")

# --- ОСНОВЕН РЕНДЕР ---
def render_recruitment_module():
    st.header("📋 Модул Подбор (V4 Enterprise)")

    if not check_permission("recruitment", "read"):
        st.error("Нямате достъп до този модул.")
        return

    st.write("### 🏢 Работен плот по дружества")
    selected_company = st.pills("Изберете компания", COMPANIES, default=None)

    if not selected_company:
        st.info("👈 Моля, изберете фирма от холдинга, за да заредите кампаниите.")
        return

    st.divider()
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

    if check_permission("recruitment", "upload_candidates"):
        with st.expander(f"📥 Импорт на ZIP към '{selected_pos_title}'"):
            uploaded_files = st.file_uploader("Качи ZIP архиви от Jobs.bg", type="zip", accept_multiple_files=True)
            if uploaded_files and st.button("Стартирай интелигентен внос"):
                with st.spinner("Парсване и извличане на снимки..."):
                    count = 0
                    for uf in uploaded_files:
                        cand_name, cv_data, photo = parse_jobs_zip(uf)
                        cand_res = supabase.table("hr_candidates").insert({
                            "full_name": cand_name, 
                            "source": "Jobs.bg ZIP", 
                            "raw_cv_data": cv_data,
                            "photo_thumbnail": photo
                        }).execute()
                        
                        if cand_res.data:
                            supabase.table("hr_applications").insert({
                                "candidate_id": cand_res.data[0]["id"],
                                "position_id": target_pos_id,
                                "status": "Нов"
                            }).execute()
                            count += 1
                st.success(f"Успешно импортирани {count} досиета!")
                st.rerun()

    st.write("### 👥 Кандидати")
    status_filter = st.pills("Филтър по статус:", ["Всички", "Нов", "Телефонно интервю", "Живо интервю", "Одобрен", "Отхвърлен"], default="Всички")
    
    apps_res = supabase.table("hr_applications").select("*, hr_candidates(*)").order("created_at", desc=True).eq("position_id", target_pos_id).execute()
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
                    # Подаваме app_id и candidate_id към картона
                    open_candidate_card(
                        app["id"],
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
