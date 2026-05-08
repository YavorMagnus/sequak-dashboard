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
import time

# --- КОНФИГУРАЦИЯ ---
COMPANIES = ["REN", "CIM", "MAS", "BAU", "AST", "CMX", "RXS", "SNW", "RXB", "DXM"]
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

# --- ХАКЕРСКИ ПАРСЪР (V15 - ЗАМРАЗЕН И УСЪВЪРШЕНСТВАН ЗА БЕЛЕЖКИ) ---
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
                elif any(keyword in html_str for keyword in ["Бележки", "Notes", "Коментари", "Remarks"]) or any(keyword in lower_name for keyword in ["notes", "бележки", "comments"]): 
                    cv_data["notes"] = clean_html_text(file_bytes)
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
def open_schedule_export(apps_data):
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

# --- THE MODAL: ИНТЕРАКТИВНО ДОСИЕ ---
@st.dialog("📄 Картон на кандидата", width="large")
def open_candidate_card(app_id, candidate_id, candidate_name, status, raw_cv_data, photo_base64, manual_score, all_global_positions, current_pos_id, created_at, interview_details):
    comments_res = supabase.table("hr_comments").select("*").eq("application_id", app_id).order("created_at").execute()
    comments = comments_res.data or []
    is_ghost_record = (status == "Преместен")
    
    # ИЗВЛИЧАНЕ НА ОЦЕНКИ С ОБРАТНА СЪВМЕСТИМОСТ
    curr_rating = 0
    curr_matrix = {}
    if manual_score:
        if "rating_1_to_6" in manual_score:
            curr_rating = manual_score.get("rating_1_to_6", 0)
            curr_matrix = manual_score.get("profile_matrix", {})
        else:
            # Fallback ако имаме стари данни от предни версии
            curr_matrix = manual_score

    # Подготовка на текста за споделяне и Hero Section
    matrix_details = [f"{k} ({v}%)" for k, v in curr_matrix.items() if int(v) > 0]
    
    col_img, col_info = st.columns([1, 4])
    with col_img:
        if photo_base64: st.markdown(f'<img src="data:image/png;base64,{photo_base64}" style="width:100%; border-radius:10px;">', unsafe_allow_html=True)
        else: st.info("Няма снимка")
    with col_info:
        st.subheader(f"👤 {candidate_name}")
        st.caption(f"Статус: **{status}** | Качен: {created_at[:10]}")
        
        # ВИЗУАЛИЗАЦИЯ НА ОЦЕНКИТЕ В HERO SECTION
        if curr_rating > 0:
            st.success(f"🎯 **Текуща оценка: {curr_rating} / 6**")
        if sum(int(v) for v in curr_matrix.values()) == 100 and matrix_details:
            st.info(f"📊 **Профил:** {' | '.join(matrix_details)}")
            
        transfer_notes = [c for c in comments if "🔄 Преместен" in c["comment_text"]]
        if transfer_notes: st.info(f"ℹ️ {transfer_notes[-1]['comment_text']}")
        if interview_details: st.warning(f"⏰ **Интервю:** {interview_details.get('date')} - {interview_details.get('time')} с {interview_details.get('interviewer')}")

    st.divider()
    
    if is_ghost_record:
        st.error("🔒 **Този кандидат е преместен в друга кампания.** Този картон е запазен само за историческа справка и не може да бъде редактиран тук.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        statuses = ["Нов", "Телефонно интервю", "Живо интервю", "Одобрен", "Отхвърлен", "Отказал", "Преместен"]
        with col1: 
            current_sel = st.selectbox("Смени статус", statuses, index=statuses.index(status) if status in statuses else 0, label_visibility="collapsed")
        
        move_to_pos_id = None
        reject_reason = None
        btn_disabled = False

        if current_sel == "Преместен":
            other_positions = [p for p in all_global_positions if p["id"] != current_pos_id]
            if other_positions:
                pos_options = ["--- Изберете обява ---"] + [f"{p['title']} ({p['company_name']})" for p in other_positions]
                target_pos_f = st.selectbox("Изберете целева кампания (Задължително):", pos_options)
                if target_pos_f == "--- Изберете обява ---":
                    btn_disabled = True
                else:
                    move_to_pos_id = next(p["id"] for p in other_positions if f"{p['title']} ({p['company_name']})" == target_pos_f)
            else:
                st.warning("Няма други кампании.")
                btn_disabled = True
        elif current_sel in ["Отхвърлен", "Отказал"]:
            reasons = ["--- Изберете причина ---", "Неоправдани претенции", "Лошо впечатление", "Липса на опит", "Друго"]
            reject_reason = st.selectbox("Уточнете причина:", reasons)
            if reject_reason == "--- Изберете причина ---":
                btn_disabled = True

        with col2: 
            if st.button("💾 Запиши промяна", type="primary", use_container_width=True, disabled=btn_disabled):
                user_name = st.session_state.get("user_name", "Y.Nikolov")
                
                if current_sel == "Преместен" and move_to_pos_id:
                    curr_title = next(p["title"] for p in all_global_positions if p["id"] == current_pos_id)
                    curr_company = next(p["company_name"] for p in all_global_positions if p["id"] == current_pos_id)
                    
                    supabase.table("hr_applications").update({"status": "Преместен"}).eq("id", app_id).execute()
                    msg_old = f"🔄 Преместен към друга кампания от {user_name}."
                    supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": msg_old}).execute()
                    
                    new_app = supabase.table("hr_applications").insert({"candidate_id": candidate_id, "position_id": move_to_pos_id, "status": "Нов"}).execute()
                    if new_app.data:
                        new_app_id = new_app.data[0]["id"]
                        msg_new = f"🔄 Преместен тук от {user_name}. Източник: '{curr_title}' ({curr_company})"
                        supabase.table("hr_comments").insert({"application_id": new_app_id, "author_name": "🤖 Система", "comment_text": msg_new}).execute()
                else:
                    supabase.table("hr_applications").update({"status": current_sel}).eq("id", app_id).execute()
                    if reject_reason:
                        msg = f"🛑 {current_sel} от {user_name}. Причина: {reject_reason}"
                        supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": msg}).execute()
                
                st.session_state.force_open_app_id = app_id
                st.rerun()
                
        with col3: 
            with st.popover("✉️ Сподели (Rich Text)", use_container_width=True):
                st.write("Маркирайте текста по-долу, копирайте (Ctrl+C) и поставете във вашия имейл клиент:")
                curr_title = next(p["title"] for p in all_global_positions if p["id"] == current_pos_id)
                score_str = f"{curr_rating}/6" if curr_rating > 0 else "Без оценка"
                prof_str = " | ".join(matrix_details) if matrix_details else "Непопълнен"
                
                rich_text = f"""
                <div style="font-family: Arial, sans-serif; padding: 15px; border: 1px solid #ddd; border-radius: 8px; background-color: #f9f9f9; color: #333;">
                    <h3 style="margin-top: 0; color: #0056b3;">Кандидат: {candidate_name}</h3>
                    <p><strong>Позиция:</strong> {curr_title}</p>
                    <p><strong>Текущ статус:</strong> <span style="background-color: #e2e3e5; padding: 3px 8px; border-radius: 4px;">{status}</span></p>
                    <hr>
                    <p><strong>Оценка (1-6):</strong> {score_str}</p>
                    <p><strong>Профил:</strong> {prof_str}</p>
                </div>
                """
                st.markdown(rich_text, unsafe_allow_html=True)
                
        with col4:
            if st.button("🗑️ Изтрий", use_container_width=True):
                supabase.table("hr_candidates").delete().eq("id", candidate_id).execute(); st.rerun()
        
    st.divider()
    tabs = st.tabs(["📋 Въпросник", "📝 Бележки", "📄 CV", "📞 Интервюта", "📊 Оценка"])
    cv_dict = raw_cv_data if isinstance(raw_cv_data, dict) else {}
    
    with tabs[0]: st.markdown(cv_dict.get("questionnaire", "Няма данни"))
    
    with tabs[1]:
        st.write("### 💬 Вътрешни бележки и История")
        for comm in comments:
            is_system = comm['author_name'] == "🤖 Система"
            with st.chat_message("user" if not is_system else "assistant"):
                st.write(f"**{comm['author_name']}** ({comm['created_at'][:16]})")
                st.write(comm['comment_text'])
        
        if not is_ghost_record:
            with st.form("new_comment", clear_on_submit=True):
                comment_txt = st.text_area("Добави коментар:")
                if st.form_submit_button("Добави бележка"):
                    if comment_txt:
                        supabase.table("hr_comments").insert({"application_id": app_id, "author_name": st.session_state.get("user_name", "Y.Nikolov"), "comment_text": comment_txt}).execute()
                        st.session_state.force_open_app_id = app_id
                        st.rerun()

    with tabs[2]: 
        st.markdown(cv_dict.get("cv_text", "Няма данни"))
        if cv_dict.get("notes") and cv_dict["notes"] != "Няма намерени бележки.":
            st.divider()
            st.write("### 📝 Бележки от Jobs.bg")
            st.info(cv_dict["notes"])
    
    with tabs[3]:
        st.write("### 📅 Планиране на интервю")
        if not is_ghost_record:
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
        else:
            st.info("Интервютата трябва да се насрочват в активната обява на кандидата.")

    with tabs[4]:
        st.write("### 📊 Оценка на кандидата")
        
        # Определяне на метода за оценка от обявата
        pos_info = next((p for p in all_global_positions if p["id"] == current_pos_id), None)
        eval_method = pos_info["evaluation_method"] if pos_info else ""
        
        new_rating = curr_rating
        if "Числова оценка" in eval_method:
            new_rating = st.slider("Оценка по шестобалната система (0 = без оценка)", 0, 6, int(curr_rating), disabled=is_ghost_record)
        elif "AI Оценка" in eval_method:
            st.info("🤖 AI оценката ще бъде налична в следваща версия. Засега можете да попълните профилната матрица.")
            
        st.divider()
        st.write("#### Профилна матрица (По желание)")
        st.caption("Ако разпределяте проценти, сборът им трябва да бъде точно 100%. Оставете всички на 0%, ако не желаете да я ползвате.")
        
        new_matrix = {}; total_score = 0
        for cat in SCORE_CATEGORIES:
            val = st.slider(cat, 0, 100, int(curr_matrix.get(cat, 0)), step=5, format="%d%%", disabled=is_ghost_record)
            new_matrix[cat] = val; total_score += val
        
        if not is_ghost_record:
            btn_disabled = False
            if total_score > 0 and total_score != 100:
                st.error(f"🚨 Сума на профила: {total_score}% (Трябва да е точно 100% или 0%)")
                btn_disabled = True
                
            if st.button("💾 Запиши оценка", use_container_width=True, disabled=btn_disabled):
                final_score_obj = {
                    "rating_1_to_6": new_rating,
                    "profile_matrix": new_matrix
                }
                supabase.table("hr_applications").update({"manual_score": final_score_obj}).eq("id", app_id).execute()
                
                # ИСТОРИЯ НА ОЦЕНКИТЕ
                user_name = st.session_state.get("user_name", "Y.Nikolov")
                msg_parts = []
                if "Числова оценка" in eval_method and new_rating > 0: msg_parts.append(f"Оценка: {new_rating}/6")
                if total_score == 100:
                    details = ", ".join([f"{k}: {v}%" for k, v in new_matrix.items() if v > 0])
                    msg_parts.append(f"Профил: {details}")
                
                if msg_parts:
                    score_msg = f"📊 Оценяване: {' | '.join(msg_parts)} (въведена от {user_name})"
                    supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": score_msg}).execute()
                
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

    if check_permission("recruitment", "manage_positions"):
        with st.expander("➕ Нова кампания"):
            with st.form("new_pos"):
                t = st.text_input("Име на позицията")
                pos_method = st.selectbox("Метод за оценка", ["Числова оценка (1-6) + Профилна матрица", "AI Оценка + Профилна матрица"])
                if st.form_submit_button("Регистрирай"):
                    if t: supabase.table("hr_positions").insert({"company_name": selected_company, "title": t, "evaluation_method": pos_method}).execute(); st.rerun()

    if not current_company_positions: st.warning("Няма кампании."); return
    selected_pos_title = st.selectbox("Кампания:", [p["title"] for p in current_company_positions])
    target_pos_id = next(p["id"] for p in current_company_positions if p["title"] == selected_pos_title)

    if check_permission("recruitment", "manage_positions"):
        with st.expander("⚙️ Управление на обявата", expanded=False):
            st.warning("Внимание: Действието по-долу ще изтрие безвъзвратно всички кандидати и историята им в тази обява!")
            if st.button("🚨 Изтрий ВСИЧКИ кандидати тук", type="primary"):
                apps_to_del = supabase.table("hr_applications").select("candidate_id").eq("position_id", target_pos_id).execute().data
                if apps_to_del:
                    for a in apps_to_del: supabase.table("hr_candidates").delete().eq("id", a["candidate_id"]).execute()
                    st.success("Всички кандидати са изтрити.")
                    time.sleep(1)
                    st.rerun()
                else: st.info("Обявата вече е празна.")

    if check_permission("recruitment", "upload_candidates"):
        with st.expander(f"📥 Импорт към '{selected_pos_title}'"):
            if "uploader_key" not in st.session_state: st.session_state.uploader_key = 0
            files = st.file_uploader("ZIP архиви", type="zip", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                start_import = st.button("▶️ Старт импорт", type="primary", use_container_width=True)
            with col_btn2:
                if files and st.button("🧹 Изчисти списъка", use_container_width=True):
                    st.session_state.uploader_key += 1
                    st.rerun()
            
            if files and start_import:
                total = len(files)
                progress_bar = st.progress(0)
                status_txt = st.empty()
                success_count = 0
                failed_files = []

                for idx, f in enumerate(files):
                    status_txt.text(f"Обработка на файл {idx+1} от {total}...")
                    try:
                        name, data, photo = parse_jobs_zip(f)
                        for k, v in data.items():
                            if isinstance(v, str): data[k] = v.replace('\x00', '')
                        if photo and len(photo) > 2500000: photo = None
                        c = supabase.table("hr_candidates").insert({"full_name": name, "raw_cv_data": data, "photo_thumbnail": photo}).execute()
                        if c.data:
                            supabase.table("hr_applications").insert({"candidate_id": c.data[0]["id"], "position_id": target_pos_id, "status": "Нов"}).execute()
                            success_count += 1
                    except Exception as e: failed_files.append((f.name, str(e)))
                    progress_bar.progress(int(((idx + 1) / total) * 100))
                
                status_txt.empty()
                progress_bar.empty()
                
                if failed_files:
                    st.error(f"⚠️ {success_count} успешно качени. {len(failed_files)} неуспешни.")
                    for fname, err in failed_files: st.warning(f"❌ {fname}: Базата отказа запис.")
                    if st.button("🔄 Продължи"): st.session_state.uploader_key += 1; st.rerun()
                else:
                    st.success(f"✅ Всички {success_count} кандидати бяха качени успешно!")
                    time.sleep(1.5)
                    st.session_state.uploader_key += 1
                    st.rerun()

    st.divider()
    col_f1, col_f2 = st.columns([3, 1])
    with col_f1:
        status_filter = st.pills("Филтър:", ["Всички", "Нов", "Телефонно интервю", "Живо интервю", "Одобрен", "Отхвърлен", "Отказал", "Преместен"], default="Всички")
    with col_f2:
        apps = supabase.table("hr_applications").select("*, hr_candidates(*), hr_comments(count)").eq("position_id", target_pos_id).order("created_at", desc=True).execute().data or []
        if st.button("📅 График Интервюта", use_container_width=True): open_schedule_export(apps)
            
    if status_filter != "Всички": apps = [a for a in apps if a["status"] == status_filter]
    
    if apps:
        cols = st.columns(4)
        for i, app in enumerate(apps):
            cand = app["hr_candidates"]
            with cols[i % 4]:
                has_history = app.get("hr_comments", [{}])[0].get("count", 0) > 0
                with st.container(border=True):
                    st.markdown(f"**{cand['full_name']}** {'📦' if has_history else ''}")
                    st.caption(f"{app['status']}")
                    if st.button("📄 Отвори", key=f"btn_{app['id']}", use_container_width=True):
                        open_candidate_card(app["id"], cand["id"], cand["full_name"], app["status"], cand["raw_cv_data"], cand["photo_thumbnail"], app["manual_score"], all_global_positions, target_pos_id, app["created_at"], app.get("interview_details", {}))
    else:
        st.info("Няма кандидати в тази категория.")

    if "force_open_app_id" in st.session_state and st.session_state.force_open_app_id:
        tid = st.session_state.force_open_app_id
        f_app = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("id", tid).execute().data
        if f_app:
            st.session_state.force_open_app_id = None
            open_candidate_card(f_app[0]["id"], f_app[0]["hr_candidates"]["id"], f_app[0]["hr_candidates"]["full_name"], f_app[0]["status"], f_app[0]["hr_candidates"]["raw_cv_data"], f_app[0]["hr_candidates"]["photo_thumbnail"], f_app[0]["manual_score"], all_global_positions, target_pos_id, f_app[0]["created_at"], f_app[0].get("interview_details", {}))

if __name__ == "__main__":
    render_recruitment_module()
