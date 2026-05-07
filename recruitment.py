import streamlit as st
import pandas as pd
from utils import supabase, check_permission
import zipfile
import io
import base64
import fitz  # PyMuPDF
from bs4 import BeautifulSoup
import re
import docx

# --- КОНФИГУРАЦИЯ ---
COMPANIES = ["Фирма 1 (Строителство)", "Фирма 2 (Логистика)", "Фирма 3 (Търговия)", "Холдинг Център"]
SCORE_CATEGORIES = ["Търговски", "Складов", "Сервизен", "Маркетингов", "Бек-офис/Управленски"]

# --- ПОМОЩНИ ФУНКЦИИ ---
def clean_html_text(html_bytes):
    soup = BeautifulSoup(html_bytes.decode("utf-8", errors="ignore"), "html.parser")
    for tag in soup(["script", "style", "head", "noscript", "title"]): tag.extract()
    for label in soup.find_all("label"):
        label.insert_before("**"); label.insert_after("**"); label.unwrap()
    for h5 in soup.find_all("h5"):
        h5.insert_before("\n\n### "); h5.insert_after("\n\n"); h5.unwrap()
    for h6 in soup.find_all("h6"):
        h6.insert_before("\n\n**"); h6.insert_after("**\n"); h6.unwrap()
    for overline in soup.find_all(class_="overline"):
        overline.insert_before("\n*"); overline.insert_after("*\n"); overline.unwrap()
    for item in soup.find_all(class_="item"):
        item.insert_before("\n- "); item.insert_after("\n"); item.unwrap()
    for br in soup.find_all("br"): br.replace_with("\n")
    for block in soup.find_all(["div", "p", "tr", "li", "h1", "h2", "h3", "h4"]): block.insert_after("\n")
    text = soup.get_text(separator=' ')
    text = re.sub(r'[ \t]+', ' ', text)
    text = text.replace('\n', '  \n')
    return text.strip()

# --- ХАКЕРСКИ ПАРСЪР ---
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
            if lower_name.endswith(".url") or lower_name in ["jobs.bg", "business.jobs.bg"]: 
                continue
                
            with z.open(file_name) as f:
                file_bytes = f.read()
                
            is_pdf = file_bytes.startswith(b"%PDF") or lower_name.endswith(".pdf")
            is_docx = lower_name.endswith(".docx")
            is_doc = lower_name.endswith(".doc")
            is_html = lower_name.endswith((".html", ".htm")) or b"<html" in file_bytes[:500].lower()
            is_img = lower_name.endswith((".jpg", ".jpeg", ".png")) or file_bytes.startswith(b"\xFF\xD8\xFF") or file_bytes.startswith(b"\x89PNG")
            
            if is_doc:
                has_legacy_doc = True  
                
            if is_img and not photo_base64:
                photo_base64 = base64.b64encode(file_bytes).decode("utf-8")
                
            elif is_html:
                html_str = file_bytes.decode("utf-8", errors="ignore")
                if "Въпросник" in html_str or "Questionnaire" in html_str or "questionnaire" in lower_name:
                    text_content = clean_html_text(file_bytes)
                    idx = text_content.find("Въпросник") if text_content.find("Въпросник") != -1 else text_content.find("Questionnaire")
                    if idx != -1: text_content = text_content[idx:]
                    text_content = re.sub(r'\s*(\d+\.\s)', r'\n\n\1', text_content)
                    text_content = re.sub(r'(\?[*]?)\s+(.*)', r'\1 **\2**', text_content)
                    cv_data["questionnaire"] = text_content.replace('\n', '  \n')
                elif "Бележки" in html_str or "Notes" in html_str or "notes" in lower_name: 
                    cv_data["notes"] = clean_html_text(file_bytes)
                elif "cv-preview" in html_str and "Кандидатура в Jobs.bg" not in html_str and "Application in Jobs.bg" not in html_str:
                    html_profile_text = clean_html_text(file_bytes)
                    
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
                    if len(cleaned_pdf_text) > 50:
                        cv_data["cv_text"] = cleaned_pdf_text
                        has_document_cv = True
                except: pass
                
            elif is_docx:
                try:
                    doc = docx.Document(io.BytesIO(file_bytes))
                    docx_text = "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()]).strip()
                    if len(docx_text) > 50:
                        cv_data["cv_text"] = docx_text
                        has_document_cv = True
                except: pass

    if not has_document_cv:
        if html_profile_text: 
            cv_data["cv_text"] = html_profile_text
        elif has_legacy_doc:
            cv_data["cv_text"] = "🚨 **Внимание: Неподдържан формат (.doc)**\n\nТози кандидат е прикачил автобиография в стар формат на Word (1997-2003), който не се поддържа за автоматично четене.\n\n**Какво да направите:**\n1. Отворете изтегления ZIP архив на вашия компютър.\n2. Отворете файла на кандидата и изберете *Save As... (Запази като)* във формат **.docx** или **.pdf**.\n3. Заместете стария файл в архива и качете кандидата отново в системата."
        
    return clean_name.title(), cv_data, photo_base64

# --- THE MODAL: ИНТЕРАКТИВНО ДОСИЕ ---
@st.dialog("📄 Картон на кандидата", width="large")
def open_candidate_card(app_id, candidate_id, candidate_name, status, raw_cv_data, photo_base64, manual_score, all_global_positions, current_pos_id):
    col_img, col_info = st.columns([1, 4])
    with col_img:
        if photo_base64: st.markdown(f'<img src="data:image/png;base64,{photo_base64}" style="width:100%; border-radius:10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">', unsafe_allow_html=True)
        else: st.info("Няма снимка")
    with col_info:
        st.subheader(f"👤 {candidate_name}")
        st.caption(f"Текущ статус: **{status}**")
    
    st.divider()
    
    # --- УМНА ЕКШЪН ЛОГИКА ---
    col1, col2, col3, col4 = st.columns(4)
    statuses = ["Нов", "Телефонно интервю", "Живо интервю", "Одобрен", "Отхвърлен", "Отказал", "Преместен"]
    
    with col1: 
        new_status = st.selectbox("Статус", statuses, index=statuses.index(status) if status in statuses else 0, label_visibility="collapsed")
    
    reject_reason = None
    candidate_reason = None
    move_to_pos_id = None
    
    # Динамично разтваряне на интерфейса за допълнителна информация
    if new_status in ["Отхвърлен", "Отказал", "Преместен"]:
        st.markdown("<div style='padding: 10px; border-left: 3px solid #ff4b4b; background-color: rgba(255, 75, 75, 0.1); margin-bottom: 15px;'>", unsafe_allow_html=True)
        
        if new_status == "Отхвърлен":
            reject_reason = st.selectbox("Уточнете причина за отказа:", ["Неоправдани претенции", "Лошо впечатление", "Друго"])
        elif new_status == "Отказал":
            candidate_reason = st.selectbox("Уточнете причината на кандидата:", ["Започнал друга работа", "Недоволен от условията", "Друго"])
        elif new_status == "Преместен":
            # Филтрираме всички позиции, които не са текущата
            other_positions = [p for p in all_global_positions if p["id"] != current_pos_id]
            if other_positions:
                # Създаваме красив списък за избор: Име на позиция (Име на Фирма)
                pos_options = [f"{p['title']} ({p['company_name']})" for p in other_positions]
                target_pos_formatted = st.selectbox("Изберете целева кампания (в целия холдинг):", pos_options)
                
                # Намираме ID-то на избраната позиция
                for p in other_positions:
                    if f"{p['title']} ({p['company_name']})" == target_pos_formatted:
                        move_to_pos_id = p["id"]
                        break
            else:
                st.warning("Няма други отворени кампании в целия холдинг.")
                
        st.markdown("</div>", unsafe_allow_html=True)

    with col2: 
        if st.button("💾 Запиши промяна", use_container_width=True):
            if new_status == "Преместен" and move_to_pos_id:
                # Преместване на кандидата (може да е в друга фирма)
                supabase.table("hr_applications").update({"position_id": move_to_pos_id, "status": "Нов"}).eq("id", app_id).execute()
                curr_title = next(p["title"] for p in all_global_positions if p["id"] == current_pos_id)
                curr_company = next(p["company_name"] for p in all_global_positions if p["id"] == current_pos_id)
                supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": f"🔄 Кандидатът е преместен тук от кампания '{curr_title}' ({curr_company})"}).execute()
            else:
                # Нормална смяна на статус
                supabase.table("hr_applications").update({"status": new_status}).eq("id", app_id).execute()
                
                # Записване на Системна бележка с причината
                reason_text = ""
                if new_status == "Отхвърлен" and reject_reason:
                    reason_text = f"🛑 Отхвърлен от нас. Причина: {reject_reason}"
                elif new_status == "Отказал" and candidate_reason:
                    reason_text = f"🚶 Отказал се. Причина: {candidate_reason}"
                
                if reason_text:
                    supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": reason_text}).execute()
            
            st.rerun()
            
    with col3: st.button("✉️ Сподели", use_container_width=True)
    with col4:
        if st.button("🗑️ Изтрий", type="primary", use_container_width=True):
            supabase.table("hr_candidates").delete().eq("id", candidate_id).execute()
            st.rerun()
        
    st.divider()
    tabs = st.tabs(["📋 Въпросник", "📝 Бележки", "📄 CV", "📊 Скор-карта"])
    cv_dict = raw_cv_data if isinstance(raw_cv_data, dict) else {}
    
    with tabs[0]: st.markdown(cv_dict.get("questionnaire", "Няма данни"))
    
    with tabs[1]:
        st.write("### 💬 Вътрешни бележки")
        comments_res = supabase.table("hr_comments").select("*").eq("application_id", app_id).order("created_at").execute()
        for comm in (comments_res.data or []):
            with st.chat_message("user" if comm['author_name'] != "🤖 Система" else "assistant"):
                st.write(f"**{comm['author_name']}** ({comm['created_at'][:16]})")
                st.write(comm['comment_text'])
        
        with st.form("new_comment", clear_on_submit=True):
            comment_txt = st.text_area("Добави коментар / указание:")
            if st.form_submit_button("Добави бележка"):
                if comment_txt:
                    supabase.table("hr_comments").insert({"application_id": app_id, "author_name": st.session_state.get("user_name", "Y.Nikolov"), "comment_text": comment_txt}).execute()
                    st.rerun()

    with tabs[2]: st.markdown(cv_dict.get("cv_text", "Няма данни"))
    
    with tabs[3]:
        st.write("### 📊 Оценка на профила (Сбор: 100%)")
        current_scores = manual_score if manual_score else {cat: 0 for cat in SCORE_CATEGORIES}
        new_scores = {}
        total_score = 0
        
        for cat in SCORE_CATEGORIES:
            val = st.slider(cat, 0, 100, int(current_scores.get(cat, 0)), step=5, format="%d%%")
            new_scores[cat] = val
            total_score += val
            
        st.divider()
        if total_score != 100:
            st.error(f"🚨 **Внимание:** Текущата сума е **{total_score}%**. Моля, разпределете точно 100%, за да запазите.")
            btn_disabled = True
        else:
            st.success("✅ **Перфектно!** Сумата е точно 100%. Можете да запишете оценката.")
            btn_disabled = False
            
        if st.button("💾 Запиши оценка", disabled=btn_disabled, use_container_width=True):
            supabase.table("hr_applications").update({"manual_score": new_scores}).eq("id", app_id).execute()
            st.rerun()

# --- ОСНОВЕН РЕНДЕР ---
def render_recruitment_module():
    st.header("📋 Модул Подбор (V4 Enterprise)")
    if not check_permission("recruitment", "read"):
        st.error("Нямате достъп."); return

    selected_company = st.pills("Изберете компания", COMPANIES, default=None)
    if not selected_company:
        st.info("👈 Изберете фирма, за да заредите кампаниите."); return

    st.divider()
    
    # ИЗВЛИЧАМЕ ВСИЧКИ ПОЗИЦИИ ОТ ЦЕЛИЯ ХОЛДИНГ (За опцията "Преместен")
    all_pos_res = supabase.table("hr_positions").select("*").order("company_name").order("title").execute()
    all_global_positions = all_pos_res.data if all_pos_res.data else []

    # Филтрираме позициите само за текущо избраната фирма (За изгледа на екрана)
    current_company_positions = [p for p in all_global_positions if p["company_name"] == selected_company]

    st.write(f"### 💼 Кампании за {selected_company}")
    
    if check_permission("recruitment", "manage_positions"):
        with st.expander("➕ Нова кампания"):
            with st.form("new_pos"):
                t = st.text_input("Име на позицията")
                pos_method = st.selectbox("Метод за оценка", ["Процентна матрица", "Обща оценка 1-10", "Свободен текст (за AI)"])
                if st.form_submit_button("Регистрирай"):
                    if t: supabase.table("hr_positions").insert({"company_name": selected_company, "title": t, "evaluation_method": pos_method}).execute(); st.rerun()

    if not current_company_positions: 
        st.warning("Няма кампании за тази фирма."); return

    selected_pos_title = st.selectbox("Разгледай кампания:", [p["title"] for p in current_company_positions])
    target_pos_id = next(p["id"] for p in current_company_positions if p["title"] == selected_pos_title)

    if check_permission("recruitment", "upload_candidates"):
        with st.expander(f"📥 Импорт към '{selected_pos_title}'"):
            files = st.file_uploader("ZIP архиви", type="zip", accept_multiple_files=True)
            if files and st.button("Старт"):
                with st.spinner("Парсване..."):
                    for f in files:
                        name, data, photo = parse_jobs_zip(f)
                        c = supabase.table("hr_candidates").insert({"full_name": name, "raw_cv_data": data, "photo_thumbnail": photo}).execute()
                        if c.data: supabase.table("hr_applications").insert({"candidate_id": c.data[0]["id"], "position_id": target_pos_id}).execute()
                    st.rerun()

    st.write("### 👥 Кандидати")
    status_filter = st.pills("Филтър:", ["Всички", "Нов", "Телефонно интервю", "Живо интервю", "Одобрен", "Отхвърлен", "Отказал"], default="Всички")
    
    apps = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("position_id", target_pos_id).order("created_at", desc=True).execute().data or []
    if status_filter != "Всички": apps = [a for a in apps if a["status"] == status_filter]
    
    if apps:
        cols = st.columns(4)
        for i, app in enumerate(apps):
            cand = app["hr_candidates"]
            with cols[i % 4]:
                st.markdown(f"**{cand['full_name']}**", help=f"Дата на качване: {app['created_at'][:10]}")
                st.caption(app['status'])
                if st.button("📄 Отвори", key=f"btn_{app['id']}", use_container_width=True):
                    # Подаваме ГЛОБАЛНИТЕ позиции към картона, за да може да местим из целия холдинг!
                    open_candidate_card(app["id"], cand["id"], cand["full_name"], app["status"], cand["raw_cv_data"], cand["photo_thumbnail"], app["manual_score"], all_global_positions, target_pos_id)
    else: st.info("Няма кандидати.")

if __name__ == "__main__":
    render_recruitment_module()
