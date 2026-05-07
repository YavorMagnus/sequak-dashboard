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

# --- УМНО ИЗЧИСТВАНЕ НА HTML (V3) ---
def clean_html_text(html_bytes):
    soup = BeautifulSoup(html_bytes.decode("utf-8", errors="ignore"), "html.parser")
    
    # Премахване на скриптове и стилове
    for tag in soup(["script", "style", "head", "noscript"]):
        tag.extract()
        
    # Смяна на <br> с нови редове
    for br in soup.find_all("br"):
        br.replace_with("\n")
        
    # Добавяне на нов ред след всеки блоков елемент и табличен ред
    for block in soup.find_all(["div", "p", "tr", "li", "h1", "h2", "h3"]):
        block.insert_after("\n")
        
    text = soup.get_text(separator=' ', strip=True)
    
    # Изчистване на излишни интервали и нови редове
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    return text.strip()

# --- УМНИЯТ ПАРСЪР V3 (С Bold Отговори) ---
def parse_jobs_zip(uploaded_file):
    # Изчистване на Франкенщайн името
    raw_name = uploaded_file.name.replace(".zip", "").replace(".ZIP", "")
    name_no_dates = re.sub(r'_[0-9]{2}\.[0-9]{2}\.[0-9]{4}.*', '', raw_name)
    clean_name = re.sub(r'^[0-9]+_', '', name_no_dates).replace('_', ' ').strip()
    if not clean_name: clean_name = raw_name 
    
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
                
            # Търсим самостоятелна картинка (За Любо)
            if lower_name.endswith((".jpg", ".jpeg", ".png")) and not photo_base64:
                with z.open(file_name) as f:
                    photo_base64 = base64.b64encode(f.read()).decode("utf-8")
            
            # Четене на HTML
            elif lower_name.endswith((".html", ".htm")):
                with z.open(file_name) as f:
                    text_content = clean_html_text(f.read())
                    
                    if "въпросник" in lower_name or "questionnaire" in lower_name:
                        idx = text_content.find("Въпросник")
                        if idx != -1: text_content = text_content[idx:]
                        
                        # V3 Магия (Твоята идея): 
                        # 1. Сваляме всеки въпрос на нов ред
                        text_content = re.sub(r'\s*(\d+\.\s)', r'\n\n\1', text_content)
                        # 2. Удебеляваме отговора (всичко след въпросителния знак до края на реда)
                        text_content = re.sub(r'(\?[\*]?)\s+(.*)', r'\1 **\2**', text_content)
                        
                        cv_data["questionnaire"] = text_content.replace('\n', '  \n')
                        
                    elif "notes" in lower_name or "бележки" in lower_name:
                        cv_data["notes"] = text_content.replace('\n', '  \n')
                        
                    else:
                        # V3 Магия: Форматиране на HTML профила (Резервното CV на Любо)
                        idx = text_content.find("Кандидатура в Jobs.bg")
                        if idx != -1: text_content = text_content[idx:]
                        
                        # Разкрасяване на ключовите секции с Markdown Headings
                        sections = ["Професионален опит", "Образование", "Езици", "Умения", "Допълнителна информация", "Контакти"]
                        for sec in sections:
                            text_content = text_content.replace(f"{sec}", f"\n\n### {sec}\n")
                        
                        html_profile_text = text_content.replace('\n', '  \n')

            # Четене на PDF
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

# --- THE MODAL: ГОЛЕМИЯТ КАРТОН ---
@st.dialog("📄 Картон на кандидата", width="large")
def open_candidate_card(candidate_id, candidate_name, status, raw_cv_data, photo_base64):
    col_img, col_info = st.columns([1, 4])
    with col_img:
        if photo_base64:
            st.markdown(f'<img src="data:image/png;base64,{photo_base64}" style="width:100%; border-radius:10px; box-shadow: 0 4px 8px rgba(0,0,0,0.
