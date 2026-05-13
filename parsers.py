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
    filename = uploaded_file.name.lower()
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        return []

    df = df.fillna("")
    candidates = []

    # Системни колони от FB, които не ни трябват във въпросника и пречат на имената
    ignore_cols = ["id", "ad_id", "ad_name", "adset_id", "adset_name", "campaign_id", "campaign_name", "form_id", "form_name", "is_organic", "platform", "created_time", "lead_status"]

    for index, row in df.iterrows():
        # 1. ПРОВЕРКА ЗА ТЕСТОВ ЛИЙД: Ако видим '<test lead', директно убиваме реда
        is_dummy = False
        for col in df.columns:
            if "<test lead" in str(row[col]).lower():
                is_dummy = True
                break
        if is_dummy:
            continue

        c_name, c_phone, c_email, fname, lname = "", "", "", "", ""
        questionnaire_lines = []
        
        for col in df.columns:
            val = str(row[col]).strip()
            # Прескачаме празни или "nan" стойности
            if not val or val.lower() == "nan":
                continue
                
            col_str = str(col).strip()
            col_lower = col_str.lower()
            
            if col_lower.startswith("unnamed"):
                col_str = "Допълнителна информация"

            # Извличане на данни (Търсим само ако колоната не е в игнорираните)
            if col_lower not in ignore_cols:
                if not c_email and ("mail" in col_lower or "поща" in col_lower):
                    c_email = val
                elif not c_phone and ("phone" in col_lower or "тел" in col_lower or "mobile" in col_lower):
                    c_phone = val
                elif "name" in col_lower or "име" in col_lower or "фамилия" in col_lower:
                    if "first" in col_lower or "първо" in col_lower:
                        fname = val
                    elif "last" in col_lower or "фамилия" in col_lower:
                        lname = val
                    elif not c_name:
                        c_name = val

            # Добавяне към въпросника (ако не е системен FB боклук)
            if col_lower not in ignore_cols:
                questionnaire_lines.append(f"**{col_str}:**\n{val}")
        
        # Сглобяване на името
        if not c_name:
            if fname or lname:
                c_name = f"{fname} {lname}".strip()
            else:
                c_name = f"Кандидат от {uploaded_file.name}"
                
        questionnaire_text = "\n\n".join(questionnaire_lines) if questionnaire_lines else "Няма попълнени данни."
        
        cv_data = {
            "questionnaire": questionnaire_text,
            "notes": "Кандидат от социални мрежи (Ексел импорт).",
            "cv_text": "🚨 **Няма класическо CV.**\n\nКандидатът е импортиран от социални мрежи. Моля, прегледайте данните в таб **Въпросник**.",
            "phone": c_phone,
            "email": c_email
        }
        candidates.append((c_name.title(), cv_data, None))
        
    return candidates
