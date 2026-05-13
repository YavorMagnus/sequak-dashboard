import zipfile
import io
import base64
import fitz  # PyMuPDF
from bs4 import BeautifulSoup
import re
import docx
import pandas as pd

def clean_html_text(html_bytes):
    soup = BeautifulSoup(html_bytes.decode("utf-8", errors="ignore"), "html.parser")
    for tag in soup(["script", "style", "head", "noscript", "title"]): tag.extract()
    for label in soup.find_all("label"): label.insert_before("**"); label.insert_after("**"); label.unwrap()
    for h5 in soup.find_all("h5"): h5.insert_before("\n\n### "); h5.insert_after("\n\n"); h5.unwrap()
    for h6 in soup.find_all("h6"): h6.insert_before("\n\n**"); h6.insert_after("**\n"); h6.unwrap()
    for overline in soup.find_all(class_="overline"): overline.insert_before("\n*"); overline.insert_after("*\n"); overline.unwrap()
    for item in soup.find_all(class_="item"): item.insert_before("\n- "); item.insert_after("\n"); item.unwrap()
    for br in soup.find_all("br"): br.replace_with("\n")
    for block in soup.find_all(["div", "p", "tr", "li", "h1", "h2", "h3", "h4"]): block.insert_after("\n")
    text = soup.get_text(separator=' ')
    text = re.sub(r'[ \t]+', ' ', text)
    return text.replace('\n', '  \n').strip()

def parse_jobs_zip(uploaded_file):
    raw_name = uploaded_file.name.replace(".zip", "").replace(".ZIP", "")
    name_no_dates = re.sub(r'_[0-9]{2}\.[0-9]{2}\.[0-9]{4}.*', '', raw_name)
    clean_name = re.sub(r'^[0-9]+_', '', name_no_dates).replace('_', ' ').strip()
    if not clean_name: clean_name = raw_name 
    cv_data = {"questionnaire": "Няма прикачен въпросник.", "notes": "Няма намерени бележки.", "cv_text": "Няма намерен текст на CV."}
    photo_base64, has_document_cv, has_legacy_doc, html_profile_text = None, False, False, ""
    
    with zipfile.ZipFile(uploaded_file, "r") as z:
        for file_name in z.namelist():
            lower_name = file_name.split('/')[-1].lower()
            if lower_name.endswith(".url") or lower_name in ["jobs.bg", "business.jobs.bg"]: continue
            with z.open(file_name) as f: file_bytes = f.read()
            is_pdf = file_bytes.startswith(b"%PDF") or lower_name.endswith(".pdf")
            is_docx = lower_name.endswith(".docx")
            is_doc = lower_name.endswith(".doc")
            is_html = lower_name.endswith((".html", ".htm")) or b"<html" in file_bytes[:500].lower()
            is_img = lower_name.endswith((".jpg", ".jpeg", ".png")) or file_bytes.startswith(b"\xFF\xD8\xFF") or file_bytes.startswith(b"\x89PNG")
            if is_doc: has_legacy_doc = True  
            if is_img and not photo_base64: photo_base64 = base64.b64encode(file_bytes).decode("utf-8")
            elif is_html:
                html_str = file_bytes.decode("utf-8", errors="ignore")
                if 'id="catForm"' in html_str or 'name="id"' in html_str: continue 
                if 'class="cv-preview"' in html_str: html_profile_text = clean_html_text(file_bytes)
                elif "Въпросник" in html_str or "Questionnaire" in html_str or "questionnaire" in lower_name:
                    text_content = clean_html_text(file_bytes)
                    idx = text_content.find("Въпросник") if text_content.find("Въпросник") != -1 else text_content.find("Questionnaire")
                    if idx != -1: text_content = text_content[idx:]
                    text_content = re.sub(r'\s*(\d+\.\s)', r'\n\n\1', text_content)
                    cv_data["questionnaire"] = re.sub(r'(\?[*]?)\s+(.*)', r'\1 **\2**', text_content).replace('\n', '  \n')
            elif is_pdf:
                try:
                    doc = fitz.open(stream=file_bytes, filetype="pdf")
                    pdf_text = ""
                    for page in doc:
                        pdf_text += page.get_text().replace('\n', '  \n') + "\n\n"
                        if not photo_base64:
                            imgs = page.get_images(full=True)
                            if imgs: photo_base64 = base64.b64encode(doc.extract_image(imgs[0][0])["image"]).decode("utf-8")
                    cleaned_pdf_text = pdf_text.strip()
                    if len(cleaned_pdf_text) > 50: cv_data["cv_text"] = cleaned_pdf_text; has_document_cv = True
                except: pass
            elif is_docx:
                try:
                    doc = docx.Document(io.BytesIO(file_bytes))
                    docx_text = "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()]).strip()
                    if len(docx_text) > 50: cv_data["cv_text"] = docx_text; has_document_cv = True
                except: pass
    if not has_document_cv:
        if html_profile_text: cv_data["cv_text"] = html_profile_text
        elif has_legacy_doc: cv_data["cv_text"] = "🚨 **Внимание: Неподдържан формат (.doc)**\n\nТози кандидат е прикачил автобиография в стар формат на Word (1997-2003)..."
    return clean_name.title(), cv_data, photo_base64

def parse_spreadsheet(uploaded_file):
    """
    Универсален парсър за Excel (.xls, .xlsx) и CSV файлове от Facebook/Social Media.
    Не разчита на твърди имена на колони.
    Връща списък от кортежи: [(Име, cv_data_dict, photo_base64), ...]
    """
    filename = uploaded_file.name.lower()
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        return []

    # Почистване на празни стойности
    df = df.fillna("")
    candidates = []

    # Ключови думи за евристично разпознаване
    name_kw = ['име', 'name', 'full name', 'първо име', 'фамилия', 'last name', 'first name']
    phone_kw = ['тел', 'phone', 'mobile']
    email_kw = ['mail', 'мейл', 'поща', 'e-mail']

    for index, row in df.iterrows():
        c_name = ""
        c_phone = ""
        c_email = ""
        fname = ""
        lname = ""
        
        questionnaire_lines = []
        
        for col in df.columns:
            val = str(row[col]).strip()
            if not val:
                continue
                
            col_lower = str(col).lower()
            
            # Търсене на основни данни
            if not c_phone and any(k in col_lower for k in phone_kw):
                c_phone = val
            elif not c_email and any(k in col_lower for k in email_kw):
                c_email = val
            elif any(k in col_lower for k in name_kw):
                if 'first' in col_lower or 'първо' in col_lower:
                    fname = val
                elif 'last' in col_lower or 'фамилия' in col_lower:
                    lname = val
                elif not c_name:
                    c_name = val
                    
            # Добавяне на всичко към въпросника
            questionnaire_lines.append(f"**{col}:**\n{val}")
        
        # Сглобяване на името
        if not c_name:
            if fname or lname:
                c_name = f"{fname} {lname}".strip()
            else:
                c_name = f"Кандидат от {uploaded_file.name}"
                
        questionnaire_text = "\n\n".join(questionnaire_lines)
        
        cv_data = {
            "questionnaire": questionnaire_text,
            "notes": "Кандидат от социални мрежи (Ексел импорт).",
            "cv_text": "🚨 **Няма класическо CV.**\n\nТози кандидат е импортиран от таблица/социални мрежи. Моля, прегледайте данните в таб **Въпросник**.",
            "phone": c_phone,
            "email": c_email
        }
        
        # Връщаме същия формат като ZIP парсъра: (Name, Data, Photo)
        candidates.append((c_name.title(), cv_data, None))
        
    return candidates
