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

# --- ХАКЕРСКИ ПАРСЪР (V15 - ЗАМРАЗЕН!) ---
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
                if "Кандидатура в Jobs.bg" in html_str or "Application in Jobs.bg" in html_str: continue
                if "cv-preview" in html_str: html_profile_text = clean_html_text(file_bytes)
                elif "Въпросник" in html_str or "Questionnaire" in html_str or "questionnaire" in lower_name:
                    text_content = clean_html_text(file_bytes)
                    idx = text_content.find("Въпросник") if text_content.find("Въпросник") != -1 else text_content.find("Questionnaire")
                    if idx != -1: text_content = text_content[idx:]
                    text_content = re.sub(r'\s*(\d+\.\s)', r'\n\n\1', text_content)
                    text_content = re.sub(r'(\?[*]?)\s+(.*)', r'\1 **\2**', text_content)
                    cv_data["questionnaire"] = text_content.replace('\n', '  \n')
                elif "Бележки" in html_str or "Notes" in html_str or "notes" in lower_name: cv_data["notes"] = clean_html_text(file_bytes)
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

# --- МОДАЛ: ГЕНЕРАТОР НА ГРАФИК ---
@st.dialog("📅 График с интервюта (Експорт)", width="large")
def open_schedule_export(target_pos_id, apps_data):
    st.write("Генериране на списък за деня:")
    selected_date = st.date_input("Дата:")
    schedule_lines = []
    for app in apps_data:
        int_details = app.get("interview_details")
        if int_details and int_details.get("date") == str(selected_date):
            cand_name = app["hr_candidates"]["full_name"]
            time_val = int_details.get("time", "??:??")
            interviewer = int_details.get("interviewer", "---")
            schedule_lines.append(f"• {time_val} ч. | {cand_name} | Интервюиращ: {interviewer}")
    if schedule_lines:
        schedule_lines.sort()
        st.code(f"График за {selected_date}:\n" + "\n".join(schedule_lines))
    else: st.info("Няма интервюта.")

# --- THE MODAL: ИНТЕРАКТИВНО ДОСИЕ (V18) ---
@st.dialog("📄 Картон на кандидата", width="large")
def open_candidate_card(app_id, candidate_id, candidate_name, status, raw_cv_data, photo_base64, manual_score, all_global_positions, current_pos_id, created_at, interview_details):
    comments_res = supabase.table("hr_comments").select("*").eq("application_id", app_id).order("created_at", desc=True).execute()
    comments = comments_res.data or []
    
    col_img, col_info = st.columns([1, 4])
    with col_img:
        if photo_base64: st.markdown(f'<img src="data:image/png;base64,{photo_base64}" style="width:100%; border-radius:10px;">', unsafe_allow_html=True)
        else: st.info("Няма снимка")
    with col_info:
        st.subheader(f"👤 {candidate_name}")
        st.caption(f"Статус: **{status}** | Качен: {created_at[:10]}")
        transfer_notes = [c for c in comments if "🔄 Преместен" in c["comment_text"]]
        if transfer_notes: st.info(f"ℹ️ {transfer_notes[0]['comment_text']}")
        if interview_details: st.warning(f"⏰ **Интервю:** {interview_details.get('date')} - {interview_details.get('time')} с {interview_details.get('interviewer')}")

    st.divider()
    
    # --- ACTION PANEL ---
    col1, col2, col3, col4 = st.columns(4)
    statuses = ["Нов", "Телефонно интервю", "Живо интервю", "Одобрен", "Отхвърлен", "Отказал", "Преместен"]
    with col1: 
        # Използваме сесията, за да хванем промяната "на живо"
        current_sel = st.selectbox("Смени статус", statuses, index=statuses.index(status) if status in statuses else 0, label_visibility="collapsed")
    
    # Реактивно показване на опциите за местене/отказ (БЕЗ НУЖДА ОТ ЗАПИС ПРЕДВАРИТЕЛНО)
    move_to_pos_id = None
    reject_reason = None
    if current_sel == "Преместен":
        other_positions = [p for p in all_global_positions if p["id"] != current_pos_id]
        pos_options = [f"{p['title']} ({p['company_name']})" for p in other_positions]
        target_pos_f = st.selectbox("Изберете целева кампания:", pos_options)
        move_to_pos_id = next(p["id"] for p in other_positions if f"{p['title']} ({p['company_name']})" == target_pos_f)
    elif current_sel in ["Отхвърлен", "Отказал"]:
        reasons = ["Неоправдани претенции", "Лошо впечатление", "Липса на опит", "Друго"]
        reject_reason = st.selectbox("Причина:", reasons)

    with col2: 
        if st.button("💾 Запиши промяна", use_container_width=True):
            user_name = st.session_state.get("user_name", "Y.Nikolov")
            # ЛОГИКА ЗА МЕСТЕНЕ
            if current_sel == "Преместен" and move_to_pos_id:
                curr_title = next(p["title"] for p in all_global_positions if p["id"] == current_pos_id)
                curr_company = next(p["company_name"] for p in all_global_positions if p["id"] == current_pos_id)
                supabase.table("hr_applications").update({"position_id": move_to_pos_id, "status": "Нов"}).eq("id", app_id).execute()
                msg = f"🔄 Преместен от {user_name}. Източник: '{curr_title}' ({curr_company})"
                supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": msg}).execute()
            else:
                # НОРМАЛЕН ЗАПИС
                supabase.table("hr_applications").update({"status": current_sel}).eq("id", app_id).execute()
                if reject_reason:
                    msg = f"🛑 {current_sel} от {user_name}. Причина: {reject_reason}"
                    supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": msg}).execute()
            
            # МАГИЯТА НА RO.PY: Пазим кой картон да отворим след рестарта
            st.session_state.force_open_app_id = app_id
            st.rerun()
            
    with col3: st.button("✉️ Сподели", use_container_width=True)
    with col4:
        if st.button("🗑️ Изтрий", type="primary", use_container_width=True):
            supabase.table("hr_candidates").delete().eq("id", candidate_id).execute(); st.rerun()
        
    st.divider()
    tabs = st.tabs(["📋 Въпросник", "📝 Бележки", "📄 CV", "📞 Интервюта", "📊 Скор-карта"])
    cv_dict = raw_cv_data if isinstance(raw_cv_data, dict) else {}
    
    with tabs[0]: st.markdown(cv_dict.get("questionnaire", "Няма данни"))
    with tabs[1]:
        st.write("### 💬 Вътрешни бележки")
        for comm in comments:
            is_system = comm['author_name'] == "🤖 Система"
            with st.chat_message("user" if not is_system else "assistant"):
                st.write(f"**{comm['author_name']}** ({comm['created_at'][:16]})")
                st.write(comm['comment_text'])
        with st.form("new_comment", clear_on_submit=True):
            comment_txt = st.text_area("Добави коментар:")
            if st.form_submit_button("Добави бележка"):
                if comment_txt:
                    supabase.table("hr_comments").insert({"application_id": app_id, "author_name": st.session_state.get("user_name", "Y.Nikolov"), "comment_text": comment_txt}).execute()
                    st.session_state.force_open_app_id = app_id # За да остане отворен!
                    st.rerun()

    with tabs[2]: st.markdown(cv_dict.get("cv_text", "Няма данни"))
    with tabs[3]:
        st.write("### 📅 Планиране на интервю")
        with st.form("interview_form"):
            col_d, col_t = st.columns(2)
            with col_d: i_date = st.date_input("Дата")
            with col_t: i_time = st.time_input("Час")
            i_person = st.text_input("Интервюиращ:")
            if st.form_submit_button("Насрочи и запази статус"):
                final_status = "Телефонно интервю" if current_sel == "Нов" else current_sel
                int_data = {"date": str(i_date), "time": str(i_time)[:5], "interviewer": i_person}
                supabase.table("hr_applications").update({"interview_details": int_data, "status": final_status}).eq("id", app_id).execute()
                msg = f"📅 Насрочено интервю за {i_date} от {str(i_time)[:5]} ч. с {i_person}. Статус: {final_status}"
                supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": msg}).execute()
                st.session_state.force_open_app_id = app_id
                st.rerun()

    with tabs[4]:
        st.write("### 📊 Оценка")
        current_scores = manual_score if manual_score else {cat: 0 for cat in SCORE_CATEGORIES}
        new_scores = {}; total_score = 0
        for cat in SCORE_CATEGORIES:
            val = st.slider(cat, 0, 100, int(current_scores.get(cat, 0)), step=5, format="%d%%")
            new_scores[cat] = val; total_score += val
        if total_score != 100: st.error(f"🚨 Сума: {total_score}%")
        elif st.button("💾 Запиши оценка", use_container_width=True):
            supabase.table("hr_applications").update({"manual_score": new_scores}).eq("id", app_id).execute()
            st.session_state.force_open_app_id = app_id
            st.rerun()

# --- ОСНОВЕН РЕНДЕР ---
def render_recruitment_module():
    st.header("📋 Модул Подбор (V4 Enterprise)")
    selected_company = st.pills("Изберете компания", COMPANIES, default=None)
    if not selected_company: st.info("👈 Изберете фирма."); return

    all_pos_res = supabase.table("hr_positions").select("*").order("company_name").order("title").execute()
    all_global_positions = all_pos_res.data if all_pos_res.data else []
    current_company_positions = [p for p in all_global_positions if p["company_name"] == selected_company]

    if not current_company_positions: st.warning("Няма кампании."); return
    selected_pos_title = st.selectbox("Кампания:", [p["title"] for p in current_company_positions])
    target_pos_id = next(p["id"] for p in current_company_positions if p["title"] == selected_pos_title)

    st.divider()
    col_f1, col_f2 = st.columns([3, 1])
    with col_f1:
        # ДОБАВЯМЕ "Преместен" ВЪВ ФИЛТЪРА, ЗА ДА НЕ ИЗЧЕЗВА Boris!
        status_filter = st.pills("Филтър:", ["Всички", "Нов", "Телефонно интервю", "Живо интервю", "Одобрен", "Отхвърлен", "Отказал", "Преместен"], default="Всички")
    with col_f2:
        apps = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("position_id", target_pos_id).order("created_at", desc=True).execute().data or []
        if st.button("📅 График Интервюта", use_container_width=True): open_schedule_export(target_pos_id, apps)
            
    if status_filter != "Всички": apps = [a for a in apps if a["status"] == status_filter]
    
    if apps:
        cols = st.columns(4)
        for i, app in enumerate(apps):
            cand = app["hr_candidates"]
            with cols[i % 4]:
                st.markdown(f"**{cand['full_name']}**")
                st.caption(app['status'])
                if st.button("📄 Отвори", key=f"btn_{app['id']}", use_container_width=True):
                    open_candidate_card(app["id"], cand["id"], cand["full_name"], app["status"], cand["raw_cv_data"], cand["photo_thumbnail"], app["manual_score"], all_global_positions, target_pos_id, app["created_at"], app.get("interview_details", {}))

    # МАГИЯТА ЗА ПРЕЗАРЕЖДАНЕ НА КАРТОНА (ro.py trick)
    if "force_open_app_id" in st.session_state and st.session_state.force_open_app_id:
        target_id = st.session_state.force_open_app_id
        # Намираме данните за този апп
        force_app = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("id", target_id).execute().data
        if force_app:
            app = force_app[0]
            cand = app["hr_candidates"]
            st.session_state.force_open_app_id = None # Чистим, за да не зацикли
            open_candidate_card(app["id"], cand["id"], cand["full_name"], app["status"], cand["raw_cv_data"], cand["photo_thumbnail"], app["manual_score"], all_global_positions, target_pos_id, app["created_at"], app.get("interview_details", {}))

if __name__ == "__main__":
    render_recruitment_module()
