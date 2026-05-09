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
from datetime import datetime

# --- ПОМОЩНИ ФУНКЦИИ ---
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

# --- МОДАЛ: УПРАВЛЕНИЕ НА ИНТЕРВЮТА ---
@st.dialog("📅 Управление на интервюта", width="large")
def open_interview_dashboard(apps_data):
    interviews = []
    for app in apps_data:
        details = app.get("interview_details")
        if details and details.get("interviewer"):
            interviews.append({"interviewer": details["interviewer"], "date": details.get("date", ""), "time": details.get("time", ""), "candidate": app["hr_candidates"]["full_name"], "status": app["status"]})
    if not interviews: st.info("Няма насрочени интервюта в тази кампания."); return
        
    interviewers = sorted(list(set([i["interviewer"] for i in interviews])))
    col1, col2 = st.columns(2)
    with col1: selected_int = st.selectbox("👤 Избери Интервюиращ:", interviewers)
    with col2: filter_type = st.radio("Филтър по вид:", ["Всички", "Телефонни", "Живи (на място)"], horizontal=True)
    
    st.divider()
    filtered_ints = [i for i in interviews if i["interviewer"] == selected_int]
    if filter_type == "Телефонни": filtered_ints = [i for i in filtered_ints if "Телефонно" in i["status"]]
    elif filter_type == "Живи (на място)": filtered_ints = [i for i in filtered_ints if "Живо" in i["status"]]
        
    filtered_ints.sort(key=lambda x: (x["date"], x["time"]))
    if filtered_ints:
        for i in filtered_ints:
            icon = "📞" if "Телефонно" in i["status"] else "🤝"
            st.markdown(f"**{i['date']} | {i['time']} ч.** {icon} {i['candidate']} *(Статус: {i['status']})*")
    else: st.warning("Няма интервюта от този тип за избрания колега.")

# --- THE MODAL: ИНТЕРАКТИВНО ДОСИЕ ---
@st.dialog("📄 Картон на кандидата", width="large")
def open_candidate_card(app_id, candidate_id, candidate_name, status, raw_cv_data, photo_base64, manual_score, all_global_positions, current_pos_id, created_at, interview_details, sys_reject_reasons, sys_decline_reasons, score_categories):
    can_evaluate = check_permission("recruitment", "evaluate")
    current_user = st.session_state.get("username", "Y.Nikolov")
    
    comments_res = supabase.table("hr_comments").select("*").eq("application_id", app_id).order("created_at").execute()
    comments = comments_res.data or []
    is_ghost_record = (status == "Преместен")
    
    curr_rating = manual_score.get("rating_1_to_6", 0) if manual_score and "rating_1_to_6" in manual_score else 0
    curr_matrix = manual_score.get("profile_matrix", {}) if manual_score and "rating_1_to_6" in manual_score else (manual_score or {})
    matrix_details = [f"{k} ({v}%)" for k, v in curr_matrix.items() if int(v) > 0]
    
    col_img, col_info = st.columns([1, 4])
    with col_img:
        if photo_base64: st.markdown(f'<img src="data:image/png;base64,{photo_base64}" style="width:100%; border-radius:10px;">', unsafe_allow_html=True)
        else: st.info("Няма снимка")
    with col_info:
        st.subheader(f"👤 {candidate_name}")
        st.caption(f"Статус: **{status}** | Качен: {created_at[:10]}")
        if curr_rating > 0: st.success(f"🎯 **Текуща оценка: {curr_rating} / 6**")
        if sum(int(v) for v in curr_matrix.values()) == 100 and matrix_details: st.info(f"📊 **Профил:** {' | '.join(matrix_details)}")
        transfer_notes = [c for c in comments if "🔄 Преместен" in c["comment_text"] or "🔄 Копиран" in c["comment_text"]]
        if transfer_notes: st.info(f"ℹ️ {transfer_notes[-1]['comment_text']}")
        if interview_details: st.warning(f"⏰ **Интервю:** {interview_details.get('date')} - {interview_details.get('time')} с {interview_details.get('interviewer')}")

    st.divider()
    
    if is_ghost_record: st.error("🔒 **Този кандидат е преместен в друга кампания.** Този картон е запазен само за историческа справка.")
    elif can_evaluate:
        col1, col2, col3, col4 = st.columns(4)
        statuses = ["Нов", "Телефонно интервю", "Живо интервю", "Одобрен", "Отхвърлен", "Отказал", "Копирай / Премести"]
        c_status = "Копирай / Премести" if status == "Преместен" else status
        with col1: current_sel = st.selectbox("Смени статус", statuses, index=statuses.index(c_status) if c_status in statuses else 0, label_visibility="collapsed")
        
        target_pos_ids = []; reject_reason = None; btn_disabled = False; keep_active = False
        if current_sel == "Копирай / Премести":
            other_positions = [p for p in all_global_positions if p["id"] != current_pos_id]
            if other_positions:
                pos_options = {p['id']: f"{p['title']} ({p['company_name']})" for p in other_positions}
                target_pos_ids = st.multiselect("Целеви кампании:", options=list(pos_options.keys()), format_func=lambda x: pos_options[x])
                keep_active = st.checkbox("Запази кандидата активен и тук (Копиране)", value=False)
                if not target_pos_ids: btn_disabled = True
            else: st.warning("Няма други кампании."); btn_disabled = True
        elif current_sel == "Отхвърлен":
            reasons = ["--- Изберете причина ---"] + sys_reject_reasons
            reject_reason = st.selectbox("Уточнете причина:", reasons)
            if reject_reason == "--- Изберете причина ---": btn_disabled = True
        elif current_sel == "Отказал":
            reasons = ["--- Изберете причина ---"] + sys_decline_reasons
            reject_reason = st.selectbox("Уточнете причина:", reasons)
            if reject_reason == "--- Изберете причина ---": btn_disabled = True

        with col2: 
            if st.button("💾 Запиши промяна", type="primary", use_container_width=True, disabled=btn_disabled):
                curr_title = next(p["title"] for p in all_global_positions if p["id"] == current_pos_id)
                
                if current_sel == "Копирай / Премести" and target_pos_ids:
                    dest_names = [f"{all_global_positions[i]['title']} ({all_global_positions[i]['company_name']})" for i in range(len(all_global_positions)) if all_global_positions[i]['id'] in target_pos_ids]
                    dest_str = ", ".join(dest_names)
                    
                    if not keep_active:
                        supabase.table("hr_applications").update({"status": "Преместен", "resolution_reason": None}).eq("id", app_id).execute()
                        msg_old = f"🔄 Преместен в кампании: {dest_str} от {current_user}."
                        supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": msg_old}).execute()
                    else:
                        msg_old = f"🔄 Копиран към кампании: {dest_str} от {current_user}."
                        supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": msg_old}).execute()
                        
                    for t_id in target_pos_ids:
                        new_app = supabase.table("hr_applications").insert({"candidate_id": candidate_id, "position_id": t_id, "status": "Нов"}).execute()
                        if new_app.data:
                            msg_new = f"🔄 {'Копиран' if keep_active else 'Преместен'} тук от {current_user}. Източник: '{curr_title}'"
                            supabase.table("hr_comments").insert({"application_id": new_app.data[0]["id"], "author_name": "🤖 Система", "comment_text": msg_new}).execute()
                else:
                    update_data = {"status": current_sel, "resolution_reason": reject_reason if current_sel in ["Отхвърлен", "Отказал"] else None}
                    supabase.table("hr_applications").update(update_data).eq("id", app_id).execute()
                    if reject_reason:
                        supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": f"🛑 {current_sel} от {current_user}. Причина: {reject_reason}"}).execute()
                st.session_state.force_open_app_id = app_id; st.rerun()
                
        with col3: 
            with st.popover("✉️ Сподели", use_container_width=True):
                st.write("Маркирайте текста по-долу, копирайте и поставете във вашия имейл клиент:")
                curr_title = next(p["title"] for p in all_global_positions if p["id"] == current_pos_id)
                score_str = f"{curr_rating}/6" if curr_rating > 0 else "Без оценка"
                prof_str = " | ".join(matrix_details) if matrix_details else "Непопълнен"
                st.markdown(f"""<div style="font-family: Arial, sans-serif; padding: 15px; border: 1px solid #ddd; border-radius: 8px; background-color: #f9f9f9; color: #333;"><h3 style="margin-top: 0; color: #0056b3;">Кандидат: {candidate_name}</h3><p><strong>Позиция:</strong> {curr_title}</p><p><strong>Текущ статус:</strong> <span style="background-color: #e2e3e5; padding: 3px 8px; border-radius: 4px;">{status}</span></p><hr><p><strong>Оценка (1-6):</strong> {score_str}</p><p><strong>Профил:</strong> {prof_str}</p></div>""", unsafe_allow_html=True)
                
        with col4:
            if st.button("🗑️ Изтрий", use_container_width=True):
                other_apps = supabase.table("hr_applications").select("id").eq("candidate_id", candidate_id).neq("id", app_id).execute()
                if other_apps.data and len(other_apps.data) > 0: supabase.table("hr_applications").delete().eq("id", app_id).execute()
                else: supabase.table("hr_applications").delete().eq("id", app_id).execute(); supabase.table("hr_candidates").delete().eq("id", candidate_id).execute()
                st.rerun()
        
    st.divider()
    tabs = st.tabs(["📋 Въпросник", "📝 Бележки", "📄 CV", "📞 Интервюта", "📊 Оценка"])
    cv_dict = raw_cv_data if isinstance(raw_cv_data, dict) else {}
    
    with tabs[0]: 
        if can_evaluate and st.button("✏️ Редактирай Въпросник", key=f"edit_q_{app_id}"): 
            st.session_state[f"q_edit_{app_id}"] = not st.session_state.get(f"q_edit_{app_id}", False)
        if st.session_state.get(f"q_edit_{app_id}", False):
            new_q = st.text_area("Редакция", value=cv_dict.get("questionnaire", ""), height=300, key=f"txt_q_{app_id}")
            if st.button("💾 Запази", key=f"save_q_{app_id}"):
                cv_dict["questionnaire"] = new_q; supabase.table("hr_candidates").update({"raw_cv_data": cv_dict}).eq("id", candidate_id).execute()
                st.session_state[f"q_edit_{app_id}"] = False; st.session_state.force_open_app_id = app_id; st.rerun()
        else: st.markdown(cv_dict.get("questionnaire", "Няма данни"))
    
    with tabs[1]:
        st.write("### 💬 Вътрешни бележки и История")
        for comm in comments:
            is_sys = "🤖 Система" in comm['author_name']
            with st.chat_message("assistant" if is_sys else "user"):
                c1, c2 = st.columns([9,1])
                c1.write(f"**{comm['author_name']}** ({comm['created_at'][:16]})\n\n{comm['comment_text']}")
                # Одитна следа при триене - ползваме current_user
                if not is_sys and comm['author_name'] == current_user and "🗑️" not in comm['comment_text']:
                    if c2.button("🗑️", key=f"del_c_{comm['id']}", help="Изтрий бележката"):
                        supabase.table("hr_comments").update({"comment_text": f"🗑️ *Бележката е изтрита от {comm['author_name']} на {datetime.now().strftime('%Y-%m-%d %H:%M')}*"}).eq("id", comm['id']).execute()
                        st.session_state.force_open_app_id = app_id; st.rerun()
                        
        if not is_ghost_record and can_evaluate:
            with st.form("new_comment", clear_on_submit=True):
                comment_txt = st.text_area("Добави коментар:")
                if st.form_submit_button("Добави бележка") and comment_txt:
                    supabase.table("hr_comments").insert({"application_id": app_id, "author_name": current_user, "comment_text": comment_txt}).execute()
                    st.session_state.force_open_app_id = app_id; st.rerun()

    with tabs[2]: 
        if can_evaluate and st.button("✏️ Редактирай CV", key=f"edit_cv_{app_id}"): 
            st.session_state[f"cv_edit_{app_id}"] = not st.session_state.get(f"cv_edit_{app_id}", False)
        if st.session_state.get(f"cv_edit_{app_id}", False):
            new_cv = st.text_area("Редакция", value=cv_dict.get("cv_text", ""), height=400, key=f"txt_cv_{app_id}")
            if st.button("💾 Запази", key=f"save_cv_{app_id}"):
                cv_dict["cv_text"] = new_cv; supabase.table("hr_candidates").update({"raw_cv_data": cv_dict}).eq("id", candidate_id).execute()
                st.session_state[f"cv_edit_{app_id}"] = False; st.session_state.force_open_app_id = app_id; st.rerun()
        else: st.markdown(cv_dict.get("cv_text", "Няма данни"))
    
    with tabs[3]:
        st.write("### 📅 Планиране на интервю")
        if not is_ghost_record and can_evaluate:
            with st.form("interview_form"):
                col_d, col_t = st.columns(2)
                with col_d: i_date = st.date_input("Дата")
                with col_t: i_time = st.time_input("Час")
                i_person = st.text_input("Интервюиращ:")
                if st.form_submit_button("Насрочи и запази статус"):
                    final_status = "Телефонно интервю" if c_status == "Нов" else c_status
                    supabase.table("hr_applications").update({"interview_details": {"date": str(i_date), "time": str(i_time)[:5], "interviewer": i_person}, "status": final_status}).eq("id", app_id).execute()
                    supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": f"📅 Насрочено интервю за {i_date} от {str(i_time)[:5]} ч. с {i_person}. Статус: {final_status}"}).execute()
                    st.session_state.force_open_app_id = app_id; st.rerun()
        elif is_ghost_record: st.info("Интервютата трябва да се насрочват в активната обява.")
        else: st.info("Нямате права за насрочване.")

    with tabs[4]:
        st.write("### 📊 Оценка на кандидата")
        rating_notes = [c for c in comments if "📊 Оценяване:" in c["comment_text"]]
        if rating_notes: st.info(f"ℹ️ {rating_notes[-1]['comment_text']}")
        
        pos_info = next((p for p in all_global_positions if p["id"] == current_pos_id), None)
        eval_method = pos_info["evaluation_method"] if pos_info else ""
        
        new_rating = curr_rating
        if "Числова оценка" in eval_method: new_rating = st.slider("Оценка по шестобалната система (0 = без оценка)", 0, 6, int(curr_rating), disabled=(is_ghost_record or not can_evaluate))
        elif "AI Оценка" in eval_method: st.info("🤖 AI оценката ще бъде налична в следваща версия.")
            
        st.divider(); st.write("#### Профилна матрица (По желание)")
        st.caption("Ако разпределяте проценти, сборът им трябва да бъде точно 100%. Оставете всички на 0%, ако не желаете да я ползвате.")
        
        new_matrix = {}; total_score = 0
        for cat in score_categories:
            val = st.slider(cat, 0, 100, int(curr_matrix.get(cat, 0)), step=5, format="%d%%", disabled=(is_ghost_record or not can_evaluate))
            new_matrix[cat] = val; total_score += val
        
        if not is_ghost_record and can_evaluate:
            btn_disabled = (total_score > 0 and total_score != 100)
            if btn_disabled: st.error(f"🚨 Сума на профила: {total_score}% (Трябва да е точно 100% или 0%)")
            if st.button("💾 Запиши оценка", use_container_width=True, disabled=btn_disabled):
                supabase.table("hr_applications").update({"manual_score": {"rating_1_to_6": new_rating, "profile_matrix": new_matrix}}).eq("id", app_id).execute()
                msg_parts = []
                if "Числова оценка" in eval_method and new_rating > 0: msg_parts.append(f"Оценка: {new_rating}/6")
                if total_score == 100: msg_parts.append(f"Профил: {', '.join([f'{k}: {v}%' for k, v in new_matrix.items() if v > 0])}")
                if msg_parts: supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": f"📊 Оценяване: {' | '.join(msg_parts)} (въведена от {current_user})"}).execute()
                st.session_state.force_open_app_id = app_id; st.rerun()

# --- ОСНОВЕН РЕНДЕР ---
def render_recruitment_module():
    # ФИКС: Инициализацията на сесията е ВЪТРЕ във функцията!
    if "active_company" not in st.session_state: st.session_state.active_company = None
    if "active_campaign" not in st.session_state: st.session_state.active_campaign = None

    COMPANIES = ["REN", "CIM", "MAS", "BAU", "AST", "CMX", "RXS", "SNW", "RXB", "DXM"]
    settings_res = supabase.table("hr_settings").select("*").execute()
    settings_dict = {row["setting_key"]: row["setting_value"] for row in settings_res.data} if settings_res.data else {}
    sys_reject_reasons = settings_dict.get("reject_reasons", ["Неоправдани претенции", "Лошо впечатление", "Липса на опит", "Друго"])
    sys_decline_reasons = settings_dict.get("decline_reasons", ["Започнал друга работа", "Недоволен от условията", "Друго"])
    score_categories = settings_dict.get("score_categories", ["Търговски", "Складов", "Сервизен", "Маркетингов", "Бек-офис/Управленски"])

    st.header("📋 Модул Подбор (V4 Enterprise)")

    selected_nav = st.pills("Навигация", ["🌍 Дашборд"] + COMPANIES, default=st.session_state.active_company if st.session_state.active_company else "🌍 Дашборд")
    if selected_nav == "🌍 Дашборд":
        if st.session_state.active_company: st.session_state.active_company = None; st.session_state.active_campaign = None; st.rerun()
    elif selected_nav != st.session_state.active_company: st.session_state.active_company = selected_nav; st.session_state.active_campaign = None; st.rerun()

    all_pos_res = supabase.table("hr_positions").select("*").order("company_name").order("title").execute()
    all_global_positions = all_pos_res.data if all_pos_res.data else []

    if not st.session_state.active_company:
        st.write("### 🌍 Активни задачи (Глобален Дашборд)")
        pos_map = {p["id"]: p for p in all_global_positions}
        counts = {}
        for a in (supabase.table("hr_applications").select("position_id").eq("status", "Нов").execute().data or []): counts[a["position_id"]] = counts.get(a["position_id"], 0) + 1
            
        has_vis = False
        for pid, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:20]:
            if pid in pos_map and pos_map[pid]['company_name'] in COMPANIES:
                has_vis = True
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                    c1.markdown(f"**{pos_map[pid]['title']}**"); c2.caption(f"🏢 {pos_map[pid]['company_name']}"); c3.error(f"🔥 {count} Нови кандидати")
                    if c4.button("Отвори", key=f"op_{pid}", use_container_width=True): st.session_state.active_company = pos_map[pid]['company_name']; st.session_state.active_campaign = pos_map[pid]['title']; st.rerun()
        if not has_vis: st.info("В момента няма нови кандидати в нито една активна обява.")
            
        if check_permission("recruitment", "manage_positions"):
            st.divider()
            with st.expander("⚙️ Системни настройки (Суперадмин)"):
                with st.form("settings_form"):
                    nr = st.text_area("Причини за 'Отхвърлен':", value="\n".join(sys_reject_reasons))
                    nd = st.text_area("Причини за 'Отказал':", value="\n".join(sys_decline_reasons))
                    sc = st.text_area("Профили за Матрицата:", value="\n".join(score_categories))
                    if st.form_submit_button("💾 Запиши настройките"):
                        supabase.table("hr_settings").update({"setting_value": [x.strip() for x in nr.split("\n") if x.strip()]}).eq("setting_key", "reject_reasons").execute()
                        supabase.table("hr_settings").update({"setting_value": [x.strip() for x in nd.split("\n") if x.strip()]}).eq("setting_key", "decline_reasons").execute()
                        supabase.table("hr_settings").update({"setting_value": [x.strip() for x in sc.split("\n") if x.strip()]}).eq("setting_key", "score_categories").execute()
                        st.success("Обновено!"); st.rerun()
        return

    current_company_positions = [p for p in all_global_positions if p["company_name"] == st.session_state.active_company]
    if check_permission("recruitment", "manage_positions"):
        with st.expander("➕ Нова кампания"):
            with st.form("new_pos"):
                t = st.text_input("Име на позицията")
                pos_method = st.selectbox("Метод за оценка", ["Числова оценка (1-6) + Профилна матрица", "AI Оценка + Профилна матрица"])
                if st.form_submit_button("Регистрирай") and t: supabase.table("hr_positions").insert({"company_name": st.session_state.active_company, "title": t, "evaluation_method": pos_method}).execute(); st.rerun()

    if not current_company_positions: st.warning("Няма кампании."); return
    camp_options = [p["title"] for p in current_company_positions]
    selected_pos_title = st.selectbox("Кампания:", camp_options, index=camp_options.index(st.session_state.active_campaign) if st.session_state.active_campaign in camp_options else 0)
    if selected_pos_title != st.session_state.active_campaign: st.session_state.active_campaign = selected_pos_title
    target_pos_id = next(p["id"] for p in current_company_positions if p["title"] == st.session_state.active_campaign)

    if check_permission("recruitment", "manage_positions"):
        with st.expander("⚙️ Управление на обявата", expanded=False):
            if st.button("🚨 Изтрий ВСИЧКИ кандидати тук", type="primary"):
                for a in supabase.table("hr_applications").select("id, candidate_id").eq("position_id", target_pos_id).execute().data or []:
                    if len((supabase.table("hr_applications").select("id").eq("candidate_id", a["candidate_id"]).neq("position_id", target_pos_id).execute()).data or []) > 0: supabase.table("hr_applications").delete().eq("id", a["id"]).execute()
                    else: supabase.table("hr_applications").delete().eq("id", a["id"]).execute(); supabase.table("hr_candidates").delete().eq("id", a["candidate_id"]).execute()
                st.success("Изтрити."); time.sleep(1); st.rerun()
            st.divider(); st.write("🗑️ **Изтриване на самата кампания**")
            if supabase.table("hr_applications").select("id", count="exact").eq("position_id", target_pos_id).execute().count == 0:
                if st.button("🗑️ Изтрий празната кампания"): supabase.table("hr_positions").delete().eq("id", target_pos_id).execute(); st.session_state.active_campaign = None; st.rerun()
            else: st.button("🗑️ Изтрий празната кампания", disabled=True)

    if check_permission("recruitment", "upload_candidates"):
        with st.expander(f"📥 Импорт към '{st.session_state.active_campaign}'"):
            if "up_key" not in st.session_state: st.session_state.up_key = 0
            files = st.file_uploader("ZIP архиви", type="zip", accept_multiple_files=True, key=f"up_{st.session_state.up_key}")
            c1, c2 = st.columns(2)
            with c1: start_import = st.button("▶️ Старт импорт", type="primary", use_container_width=True)
            with c2: 
                if files and st.button("🧹 Изчисти списъка", use_container_width=True): st.session_state.up_key += 1; st.rerun()
            if files and start_import:
                pb = st.progress(0); st_txt = st.empty(); sc = 0; ff = []
                for idx, f in enumerate(files):
                    st_txt.text(f"Обработка {idx+1}/{len(files)}...")
                    try:
                        n, d, p = parse_jobs_zip(f)
                        for k, v in d.items(): 
                            if isinstance(v, str): d[k] = v.replace('\x00', '')
                        c = supabase.table("hr_candidates").insert({"full_name": n, "raw_cv_data": d, "photo_thumbnail": None if p and len(p)>2500000 else p}).execute()
                        if c.data: supabase.table("hr_applications").insert({"candidate_id": c.data[0]["id"], "position_id": target_pos_id, "status": "Нов"}).execute(); sc += 1
                    except Exception as e: ff.append(f.name)
                    pb.progress(int(((idx + 1) / len(files)) * 100))
                st_txt.empty(); pb.empty()
                if ff:
                    st.error(f"⚠️ {sc} успешно качени. {len(ff)} неуспешни.")
                    for fname in ff: st.warning(f"❌ {fname}: Базата отказа запис.")
                    if st.button("🔄 Продължи"): st.session_state.up_key += 1; st.rerun()
                else: 
                    # ВЪРНАТО: Подробното съобщение за успех!
                    st.success(f"✅ Всички {sc} кандидати бяха качени успешно!")
                    time.sleep(1.5); st.session_state.up_key += 1; st.rerun()

    st.divider()
    c_f1, c_f2 = st.columns([3, 1])
    with c_f1: status_filter = st.pills("Филтър:", ["Всички", "Нов", "Телефонно интервю", "Живо интервю", "Одобрен", "Отхвърлен", "Отказал", "Преместен"], default="Всички")
    with c_f2:
        sort_order = st.selectbox("Сортиране:", ["Най-нови", "Най-висока оценка (1-6)"], label_visibility="collapsed")
        apps_raw = supabase.table("hr_applications").select("*, hr_candidates(*), hr_comments(count)").eq("position_id", target_pos_id).execute().data or []
        if st.button("📅 График Интервюта", use_container_width=True): open_interview_dashboard(apps_raw)
            
    if status_filter != "Всички": apps_raw = [a for a in apps_raw if a["status"] == status_filter]
    apps_raw.sort(key=lambda x: int(x.get("manual_score", {}).get("rating_1_to_6", 0)) if sort_order == "Най-висока оценка (1-6)" and isinstance(x.get("manual_score"), dict) else x["created_at"], reverse=True)
    
    if apps_raw:
        cols = st.columns(4)
        for i, app in enumerate(apps_raw):
            c = app["hr_candidates"]
            with cols[i % 4]:
                with st.container(border=True):
                    if app['status'] == "Преместен": st.markdown(f"<span style='opacity: 0.5;'>**{c['full_name']}** 🔒</span><br><span style='opacity: 0.5; font-size:0.8em;'>{app['status']}</span>", unsafe_allow_html=True)
                    else: st.markdown(f"**{c['full_name']}** {'📦' if app.get('hr_comments', [{}])[0].get('count', 0) > 0 else ''}<br><span style='font-size:0.8em;'>{app['status']}</span>", unsafe_allow_html=True)
                    if st.button("📄 Отвори", key=f"btn_{app['id']}", use_container_width=True):
                        open_candidate_card(app["id"], c["id"], c["full_name"], app["status"], c["raw_cv_data"], c["photo_thumbnail"], app["manual_score"], all_global_positions, target_pos_id, app["created_at"], app.get("interview_details", {}), sys_reject_reasons, sys_decline_reasons, score_categories)
    else: st.info("Няма кандидати в тази категория.")

    if "force_open_app_id" in st.session_state and st.session_state.force_open_app_id:
        f_app = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("id", st.session_state.force_open_app_id).execute().data
        if f_app: st.session_state.force_open_app_id = None; open_candidate_card(f_app[0]["id"], f_app[0]["hr_candidates"]["id"], f_app[0]["hr_candidates"]["full_name"], f_app[0]["status"], f_app[0]["hr_candidates"]["raw_cv_data"], f_app[0]["hr_candidates"]["photo_thumbnail"], f_app[0]["manual_score"], all_global_positions, target_pos_id, f_app[0]["created_at"], f_app[0].get("interview_details", {}), sys_reject_reasons, sys_decline_reasons, score_categories)

if __name__ == "__main__":
    render_recruitment_module()
