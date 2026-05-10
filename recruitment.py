import streamlit as st
import pandas as pd
from utils import supabase, check_permission, SYSTEM_ROLES
import zipfile
import io
import base64
import fitz  # PyMuPDF
from bs4 import BeautifulSoup
import re
import docx
import time
from datetime import datetime

# --- ИНИЦИАЛИЗАЦИЯ НА СЕСИЯТА ---
if "active_company" not in st.session_state: st.session_state.active_company = None
if "active_campaign_id" not in st.session_state: st.session_state.active_campaign_id = None

# Карта на емоджитата за статус
EMOJI_MAP = {
    "Нов": "✨",
    "Установи контакт": "📞",
    "В процес на контакт": "⏳",
    "Възможно интервю": "➕",
    "Избран за интервю": "📅",
    "Потвърдено интервю": "✅",
    "Направено предложение": "🏆",
    "Отхвърлен": "❌",
    "Отказал": "🛑",
    "Преместен": "📦"
}

# --- ПОМОЩНИ ФУНКЦИИ (ЛОГИЧЕСКИ БЛОК) ---
def log_status_change(app_id, old_status, new_status):
    """Записва всяка промяна на статус в историческата таблица за статистики."""
    current_user = st.session_state.get("username", "Unknown")
    try:
        supabase.table("hr_status_history").insert({
            "application_id": app_id,
            "old_status": old_status,
            "new_status": new_status,
            "changed_by": current_user
        }).execute()
    except:
        pass # Не прекъсваме UX при грешка в логването

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

def get_traffic_light_6(val):
    if val <= 2: return "🔴"
    if val <= 4: return "🟡"
    return "🟢"

def get_traffic_light_perc(val):
    if val < 50: return "🔴"
    if val < 75: return "🟡"
    return "🟢"

def get_pos_display_name(p):
    base_str = f" ({p.get('base_location')})" if p.get('base_location') else ""
    city_str = f" | 📍 {p.get('city', 'Непосочен')}{base_str}"
    status_str = " 🗄️[АРХИВ]" if p.get('status') == 'Архивирана' else ""
    return f"{p['title']}{city_str}{status_str}"

# --- ПАРСЪР (БЪДЕЩ МОДУЛ PARSERS.PY) ---
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

# --- МОДАЛИ ---
@st.dialog("➕ Създаване на нова кампания", width="large")
def open_new_campaign_modal(company_name):
    st.write(f"🏢 Фирма: **{company_name}**")
    with st.form("new_pos_form", clear_on_submit=True):
        t = st.text_input("Име на позицията *")
        pos_method = st.selectbox("Метод за оценка", ["Числова оценка 1-6 - обективна и субективна", "AI Оценка + Профилна матрица"])
        cc1, cc2 = st.columns(2)
        with cc1: s_min = st.text_input("Мин. възнаграждение (EUR)")
        with cc1: s_max = st.text_input("Макс. възнаграждение (EUR)")
        with cc2: city = st.text_input("Град")
        with cc2: base_loc = st.text_input("База (незадължително)")
        
        w_type = st.selectbox("Тип работа", ["Присъствено", "Хибрид", "Remote"])
        priority = st.selectbox("Приоритет", ["Оглеждаме се", "Нормално", "Спешно", "🔥 ПОЖАР"], index=1)
        
        if st.form_submit_button("💾 Регистрирай кампанията", type="primary"):
            if not t.strip():
                st.error("⚠️ Моля, въведете име на позицията!")
            else:
                supabase.table("hr_positions").insert({"company_name": company_name, "title": t, "evaluation_method": pos_method, "salary_min": s_min, "salary_max": s_max, "city": city, "base_location": base_loc, "work_type": w_type, "priority": priority, "status": "Активна"}).execute()
                st.success("✅ Кампанията е създадена успешно!")
                time.sleep(1)
                st.rerun()

@st.dialog("📅 Глобален График Интервюта", width="large")
def open_interview_dashboard(apps_data, global_pos_map=None):
    show_archived = st.checkbox("Покажи архив (приключени събития)", value=False)
    
    interviews = []
    for app in apps_data:
        details = app.get("interview_details")
        if details and details.get("interviewer"):
            comp_title = global_pos_map[app['position_id']]['company_name'] if global_pos_map and app['position_id'] in global_pos_map else ""
            i_type = details.get("type", "В процес на контакт")
            is_active = (app["status"] == i_type)
            if show_archived or is_active:
                interviews.append({
                    "app_id": app["id"], "pos_id": app["position_id"], "company": comp_title,
                    "interviewer": details["interviewer"], "date": details.get("date", ""), 
                    "time": details.get("time", ""), "candidate": app["hr_candidates"]["full_name"], 
                    "status": app["status"], "type": i_type, "is_active": is_active
                })
            
    if not interviews: st.info("Няма интервюта, отговарящи на критериите."); return
        
    interviewers = sorted(list(set([i["interviewer"] for i in interviews])))
    col1, col2 = st.columns(2)
    with col1: selected_int = st.selectbox("👤 Избери Интервюиращ:", interviewers)
    with col2: filter_type = st.radio("Филтър по вид:", ["Всички", "В процес на контакт", "Потвърдено интервю"], horizontal=True)
    
    st.divider()
    filtered_ints = [i for i in interviews if i["interviewer"] == selected_int]
    if filter_type != "Всички": filtered_ints = [i for i in filtered_ints if i["type"] == filter_type]
        
    filtered_ints.sort(key=lambda x: (x["date"], x["time"]))
    if filtered_ints:
        for i in filtered_ints:
            icon = "📞" if i["type"] == "В процес на контакт" else "🤝"
            status_badge = "" if i["is_active"] else f" *(Статус: {i['status']})*"
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"**{i['date']} | {i['time']} ч.** {icon} **{i['candidate']}** *(Фирма: {i['company']})*{status_badge}")
            if c2.button("Отвори", key=f"btn_route_{i['app_id']}"):
                if global_pos_map and i['pos_id'] in global_pos_map:
                    st.session_state.active_company = global_pos_map[i['pos_id']]['company_name']
                    st.session_state.active_campaign_id = i['pos_id']
                    st.session_state.force_open_app_id = i['app_id']
                    st.rerun()
    else: st.warning("Няма интервюта от този тип за избрания колега.")

@st.dialog("📄 Картон на кандидата", width="large")
def open_candidate_card(app_id, candidate_id, candidate_name, status, raw_cv_data, photo_base64, manual_score, all_global_positions, current_pos_id, created_at, interview_details, sys_reject_reasons, sys_decline_reasons, score_categories, sys_users, is_backup):
    can_evaluate = check_permission("recruitment", "evaluate")
    current_user = st.session_state.get("username", "Y.Nikolov")
    
    comments_res = supabase.table("hr_comments").select("*").eq("application_id", app_id).order("created_at").execute()
    comments = comments_res.data or []
    is_ghost_record = (status == "Преместен")
    
    curr_sub_rating = manual_score.get("subjective_rating", 0) if manual_score else 0
    curr_sub_motive = manual_score.get("subjective_motive", "") if manual_score else ""
    curr_sc_active = manual_score.get("scorecard_active", False) if manual_score else False
    curr_matrix = manual_score.get("profile_matrix", {}) if manual_score else {}
    curr_sc_perc = manual_score.get("scorecard_percentage", 0) if manual_score else 0
    
    col_img, col_info = st.columns([1, 4])
    with col_img:
        if photo_base64: st.markdown(f'<img src="data:image/png;base64,{photo_base64}" style="width:100%; border-radius:10px;">', unsafe_allow_html=True)
        else: st.info("Няма снимка")
    with col_info:
        st.subheader(f"👤 {candidate_name}")
        st.caption(f"Статус: **{status}** | Качен: {created_at[:10]}")
        
        if can_evaluate:
            new_backup = st.checkbox("❓ Маркирай като 'Резерва / За обмисляне'", value=is_backup)
            if new_backup != is_backup:
                supabase.table("hr_applications").update({"is_backup": new_backup}).eq("id", app_id).execute()
                st.session_state.force_open_app_id = app_id; st.rerun()

        if curr_sub_rating > 0: 
            tl = get_traffic_light_6(curr_sub_rating)
            m_text = f" *(Мотив: {curr_sub_motive})*" if curr_sub_motive.strip() else ""
            st.info(f"**🎯 Заключителна оценка:** {curr_sub_rating} / 6 {tl} {m_text}")
        
        if curr_sc_active:
            tl_p = get_traffic_light_perc(curr_sc_perc)
            st.info(f"**📊 Област на компетентност:** {curr_sc_perc}% {tl_p}")
            matrix_details = [f"{k}: {v} {get_traffic_light_6(v)}" for k, v in curr_matrix.items()]
            if matrix_details: st.caption(f"Профил: {' | '.join(matrix_details)}")
            
        transfer_notes = [c for c in comments if "🔄 Преместен" in c["comment_text"] or "🔄 Копиран" in c["comment_text"]]
        if transfer_notes: st.info(f"ℹ️ {transfer_notes[-1]['comment_text']}")
        if interview_details: st.warning(f"⏰ **Интервю:** {interview_details.get('type', 'В процес на контакт')} | {interview_details.get('date')} - {interview_details.get('time')} с {interview_details.get('interviewer')}")

    st.divider()
    
    if is_ghost_record: st.error("🔒 **Този кандидат е преместен в друга кампания.** Този картон е запазен само за историческа справка.")
    elif can_evaluate:
        pos_info = next((p for p in all_global_positions if p["id"] == current_pos_id), {})
        base_str = f" (База: {pos_info.get('base_location')})" if pos_info.get('base_location') else ""
        st.markdown(f"""<div style="background-color: #2e2e2e; padding: 8px 15px; border-radius: 5px; margin-bottom: 15px; font-size: 0.9em; border-left: 3px solid #00aaff;">📌 <b>Обява:</b> {pos_info.get('title')} | 📍 {pos_info.get('city', '-')}{base_str} | 💰 {pos_info.get('salary_min','-')}-{pos_info.get('salary_max','-')} EUR | 🏢 {pos_info.get('work_type', '-')}</div>""", unsafe_allow_html=True)

        col1, col2, col3, col4 = st.columns(4)
        statuses = ["Нов", "Установи контакт", "В процес на контакт", "Възможно интервю", "Избран за интервю", "Потвърдено интервю", "Направено предложение", "Отхвърлен", "Отказал", "Преместен"]
        c_status = "Копирай / Премести" if status == "Преместен" else status
        
        all_options = statuses + ["Копирай / Премести"]
        with col1: current_sel = st.selectbox("Смени статус", all_options, index=all_options.index(c_status) if c_status in all_options else 0, label_visibility="collapsed")
        
        target_pos_ids = []; reject_reason = None; btn_disabled = False; keep_active = False
        if current_sel == "Копирай / Премести":
            other_positions = [p for p in all_global_positions if p["id"] != current_pos_id]
            if other_positions:
                pos_options = {p['id']: get_pos_display_name(p) for p in other_positions}
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
                    dest_names = [get_pos_display_name(p) for p in all_global_positions if p['id'] in target_pos_ids]
                    dest_str = ", ".join(dest_names)
                    if not keep_active:
                        supabase.table("hr_applications").update({"status": "Преместен", "resolution_reason": None}).eq("id", app_id).execute()
                        supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": f"🔄 Преместен в кампании: {dest_str} от {current_user}."}).execute()
                        log_status_change(app_id, status, "Преместен")
                    else:
                        supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": f"🔄 Копиран към кампании: {dest_str} от {current_user}."}).execute()
                    
                    for t_id in target_pos_ids:
                        new_app = supabase.table("hr_applications").insert({"candidate_id": candidate_id, "position_id": t_id, "status": "Нов"}).execute()
                        if new_app.data:
                            supabase.table("hr_comments").insert({"application_id": new_app.data[0]["id"], "author_name": "🤖 Система", "comment_text": f"🔄 {'Копиран' if keep_active else 'Преместен'} тук от {current_user}. Източник: '{curr_title}'"}).execute()
                            log_status_change(new_app.data[0]["id"], "None (New)", "Нов")
                else:
                    update_data = {"status": current_sel, "resolution_reason": reject_reason if current_sel in ["Отхвърлен", "Отказал"] else None}
                    supabase.table("hr_applications").update(update_data).eq("id", app_id).execute()
                    if reject_reason: supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": f"🛑 {current_sel} от {current_user}. Причина: {reject_reason}"}).execute()
                    log_status_change(app_id, status, current_sel)
                
                st.session_state.force_open_app_id = app_id; st.rerun()
                
        with col3: 
            with st.popover("✉️ Сподели", use_container_width=True):
                st.write("Маркирайте текста по-долу, копирайте и поставете във вашия имейл клиент:")
                curr_title = next(p["title"] for p in all_global_positions if p["id"] == current_pos_id)
                st.markdown(f"""<div style="font-family: Arial, sans-serif; padding: 15px; border: 1px solid #ddd; border-radius: 8px; background-color: #f9f9f9; color: #333;"><h3 style="margin-top: 0; color: #0056b3;">Кандидат: {candidate_name}</h3><p><strong>Позиция:</strong> {curr_title}</p><p><strong>Текущ статус:</strong> <span style="background-color: #e2e3e5; padding: 3px 8px; border-radius: 4px;">{status}</span></p></div>""", unsafe_allow_html=True)
                
        with col4:
            if check_permission("recruitment", "soft_delete"):
                if st.button("🗑️ Изтрий", use_container_width=True):
                    user_role = st.session_state.get('user_role', '')
                    if user_role in ["Супер-админ", "Администратор"]:
                        other_apps = supabase.table("hr_applications").select("id").eq("candidate_id", candidate_id).neq("id", app_id).execute()
                        if other_apps.data and len(other_apps.data) > 0: supabase.table("hr_applications").delete().eq("id", app_id).execute()
                        else: supabase.table("hr_applications").delete().eq("id", app_id).execute(); supabase.table("hr_candidates").delete().eq("id", candidate_id).execute()
                        st.success("Напълно изтрит!")
                    else:
                        supabase.table("hr_applications").update({"is_deleted": True}).eq("id", app_id).execute()
                        st.success("Преместен в Кошчето!")
                    time.sleep(1); st.rerun()
        
    st.divider()
    tabs = st.tabs(["📋 Въпросник", "📝 Бележки", "📄 CV", "📅 Интервюта", "📊 Оценка"])
    cv_dict = raw_cv_data if isinstance(raw_cv_data, dict) else {}
    
    with tabs[0]: 
        if can_evaluate and st.button("✏️ Редактирай Въпросник", key=f"edit_q_{app_id}"): st.session_state[f"q_edit_{app_id}"] = not st.session_state.get(f"q_edit_{app_id}", False)
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
        if can_evaluate and st.button("✏️ Редактирай CV", key=f"edit_cv_{app_id}"): st.session_state[f"cv_edit_{app_id}"] = not st.session_state.get(f"cv_edit_{app_id}", False)
        if st.session_state.get(f"cv_edit_{app_id}", False):
            new_cv = st.text_area("Редакция", value=cv_dict.get("cv_text", ""), height=400, key=f"txt_cv_{app_id}")
            if st.button("💾 Запази", key=f"save_cv_{app_id}"):
                cv_dict["cv_text"] = new_cv; supabase.table("hr_candidates").update({"raw_cv_data": cv_dict}).eq("id", candidate_id).execute()
                st.session_state[f"cv_edit_{app_id}"] = False; st.session_state.force_open_app_id = app_id; st.rerun()
        else: st.markdown(cv_dict.get("cv_text", "Няма данни"))
    
    with tabs[3]:
        st.write("### 📅 Управление на интервюта")
        if not is_ghost_record and check_permission("recruitment", "schedule"):
            st.markdown("#### 🎯 1. Заявка за интервю (Към HR)")
            with st.form("propose_dates"):
                c_pd1, c_pd2 = st.columns(2)
                with c_pd1: 
                    d1 = st.date_input("Предпочитана дата 1")
                    t1 = st.text_input("Диапазон/Бележка 1 (напр. 'Следобед')")
                with c_pd2: 
                    d2 = st.date_input("Алтернативна дата 2")
                    t2 = st.text_input("Диапазон/Бележка 2")
                
                if st.form_submit_button("🎯 Заяви 'Избран за интервю'"):
                    supabase.table("hr_applications").update({"status": "Избран за интервю"}).eq("id", app_id).execute()
                    log_status_change(app_id, status, "Избран за интервю")
                    msg = f"🟡 ЗАЯВКА ЗА СРЕЩА:\n- Опция 1: {d1} ({t1})\n- Опция 2: {d2} ({t2})"
                    supabase.table("hr_comments").insert({"application_id": app_id, "author_name": current_user, "comment_text": msg}).execute()
                    st.session_state.force_open_app_id = app_id; st.rerun()
            
            st.divider()
            st.markdown("#### ✅ 2. Окончателно насрочване (От HR)")
            with st.form("interview_form"):
                col_d, col_t, col_y = st.columns(3)
                with col_d: i_date = st.date_input("Точна дата")
                with col_t: i_time = st.time_input("Точен час")
                with col_y: i_type = st.selectbox("Вид интервю", ["В процес на контакт", "Потвърдено интервю"], index=1 if status == "Избран за интервю" else 0)
                
                i_person_sel = st.selectbox("Интервюиращ (Избери или напиши):", sys_users + ["Друг..."])
                if i_person_sel == "Друг...": i_person = st.text_input("Въведете име:")
                else: i_person = i_person_sel
                
                if st.form_submit_button("Насрочи и промени статуса"):
                    if i_person_sel == "Друг..." and not i_person: st.error("Моля въведете име на интервюиращ!")
                    else:
                        supabase.table("hr_applications").update({"interview_details": {"date": str(i_date), "time": str(i_time)[:5], "interviewer": i_person, "type": i_type}, "status": i_type}).eq("id", app_id).execute()
                        log_status_change(app_id, status, i_type)
                        icon = "📞" if i_type == "В процес на контакт" else "🤝"
                        supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": f"{icon} Насрочено '{i_type}' за {i_date} от {str(i_time)[:5]} ч. с {i_person}."}).execute()
                        st.session_state.force_open_app_id = app_id; st.rerun()
        elif is_ghost_record: st.info("Интервютата трябва да се управляват в активната обява.")
        else: st.info("Нямате права за насрочване.")

    with tabs[4]:
        st.write("### 🎯 Субективна оценка (от интервюера)")
        new_sub_rating = st.slider("Заключителна оценка", 0, 6, int(curr_sub_rating), help="0 = Без оценка", disabled=(is_ghost_record or not can_evaluate))
        new_sub_motive = st.text_input("Мотиви за оценката (по желание):", value=curr_sub_motive, disabled=(is_ghost_record or not can_evaluate))
        
        st.divider(); st.write("### 📊 Област на компетентност")
        use_scorecard = st.checkbox("Оцени кандидата по компетентност", value=curr_sc_active, disabled=(is_ghost_record or not can_evaluate))
        
        new_matrix = {}; total_score = 0
        if use_scorecard:
            for cat in score_categories:
                val = st.slider(cat, 1, 6, int(curr_matrix.get(cat, 1)), disabled=(is_ghost_record or not can_evaluate))
                new_matrix[cat] = val; total_score += val
            max_possible = len(score_categories) * 6
            calc_perc = int((total_score / max_possible) * 100) if max_possible > 0 else 0
            st.write(f"**Текущ резултат: {calc_perc}%** ({total_score} от {max_possible} т.) {get_traffic_light_perc(calc_perc)}")
        
        if not is_ghost_record and can_evaluate:
            btn_disabled = False
            if use_scorecard and new_sub_rating == 0:
                st.error("🚨 Моля, въведете и Субективна оценка (1-6) на интервюера!")
                btn_disabled = True
                
            if st.button("💾 Запиши оценка", use_container_width=True, disabled=btn_disabled):
                final_perc = int((sum(new_matrix.values()) / (len(score_categories) * 6)) * 100) if (use_scorecard and len(score_categories) > 0) else 0
                final_score_obj = {"subjective_rating": new_sub_rating, "subjective_motive": new_sub_motive, "scorecard_active": use_scorecard, "profile_matrix": new_matrix, "scorecard_percentage": final_perc}
                supabase.table("hr_applications").update({"manual_score": final_score_obj}).eq("id", app_id).execute()
                
                msg_parts = []
                if new_sub_rating > 0: msg_parts.append(f"Субективна: {new_sub_rating}/6")
                if use_scorecard: msg_parts.append(f"Компетентност: {final_perc}%")
                if msg_parts: supabase.table("hr_comments").insert({"application_id": app_id, "author_name": "🤖 Система", "comment_text": f"📊 Оценяване: {' | '.join(msg_parts)} (въведена от {current_user})"}).execute()
                st.session_state.force_open_app_id = app_id; st.rerun()

# --- ОСНОВЕН РЕНДЕР ---
def render_recruitment_module():
    if "active_company" not in st.session_state: st.session_state.active_company = None
    if "active_campaign_id" not in st.session_state: st.session_state.active_campaign_id = None

    COMPANIES = ["REN", "CIM", "MAS", "BAU", "AST", "CMX", "RXS", "SNW", "RXB", "DXM"]
    
    settings_res = supabase.table("hr_settings").select("*").execute()
    settings_dict = {row["setting_key"]: row["setting_value"] for row in settings_res.data} if settings_res.data else {}
    sys_reject_reasons = settings_dict.get("reject_reasons", ["Неоправдани претенции", "Лошо впечатление", "Липса на опит", "Друго"])
    sys_decline_reasons = settings_dict.get("decline_reasons", ["Започнал друга работа", "Недоволен от условията", "Друго"])
    score_categories = settings_dict.get("score_categories", ["Търговски", "Складов", "Сервизен", "Маркетингов", "Бек-офис/Управленски"])
    ai_prompts = settings_dict.get("ai_prompts", {"recruitment_analysis": "Ти си експерт по подбор. Анализирай CV-то..."})

    users_res = supabase.table("users").select("username").execute()
    sys_users = sorted([u['username'] for u in users_res.data]) if users_res.data else []

    all_pos_res = supabase.table("hr_positions").select("*").order("company_name").order("title").execute()
    all_global_positions = all_pos_res.data if all_pos_res.data else []
    global_pos_map = {p["id"]: p for p in all_global_positions}

    c1, c2 = st.columns([3,1])
    c1.header("📋 Модул Подбор (V38 Analytics-Ready)")
    with c2:
        if st.button("📅 Глобален график интервюта", use_container_width=True):
            all_int_apps = supabase.table("hr_applications").select("*, hr_candidates(*)").neq("interview_details", "null").eq("is_deleted", False).execute().data or []
            open_interview_dashboard(all_int_apps, global_pos_map)

    selected_nav = st.pills("Навигация", ["🌍 Дашборд"] + COMPANIES, default=st.session_state.active_company if st.session_state.active_company else "🌍 Дашборд")
    if selected_nav == "🌍 Дашборд":
        if st.session_state.active_company: st.session_state.active_company = None; st.session_state.active_campaign_id = None; st.rerun()
    elif selected_nav != st.session_state.active_company: st.session_state.active_company = selected_nav; st.session_state.active_campaign_id = None; st.rerun()

    if not st.session_state.active_company:
        st.write("### 🌍 Активни обяви (Глобален Дашборд)")
        new_apps = supabase.table("hr_applications").select("position_id").eq("status", "Нов").eq("is_deleted", False).execute().data or []
        new_counts = {}
        for a in new_apps: new_counts[a["position_id"]] = new_counts.get(a["position_id"], 0) + 1
            
        dash_positions = [p for p in all_global_positions if p['company_name'] in COMPANIES and p.get('status') != 'Архивирана']
        priority_map = {"🔥 ПОЖАР": 4, "Спешно": 3, "Нормално": 2, "Оглеждаме се": 1}
        dash_positions.sort(key=lambda x: (priority_map.get(x.get('priority', 'Нормално'), 2), new_counts.get(x['id'], 0)), reverse=True)
        
        if dash_positions:
            for pinfo in dash_positions:
                count = new_counts.get(pinfo['id'], 0)
                p_level = pinfo.get('priority', 'Нормално')
                border_color = "red" if p_level == "🔥 ПОЖАР" else ("orange" if p_level == "Спешно" else "gray")
                
                with st.container():
                    st.markdown(f"""<div style="border-left: 5px solid {border_color}; padding: 10px; border-radius: 5px; background-color: #1e1e1e; margin-bottom: 10px;">""", unsafe_allow_html=True)
                    col1, col2, col3, col4 = st.columns([3, 1, 2, 1])
                    
                    base_str = f" ({pinfo.get('base_location')})" if pinfo.get('base_location') else ""
                    col1.markdown(f"**{pinfo['title']}**<br><span style='font-size:0.8em; color:#888;'>💰 {pinfo.get('salary_min','-')} - {pinfo.get('salary_max','-')} EUR | 📍 {pinfo.get('city','-')}{base_str} | {pinfo.get('work_type','-')}</span>", unsafe_allow_html=True)
                    col2.caption(f"🏢 {pinfo['company_name']}")
                    
                    if p_level == "🔥 ПОЖАР": col3.error(f"🔥 ПОЖАР ({count} Нови)")
                    elif p_level == "Спешно": col3.warning(f"⚡ Спешно ({count} Нови)")
                    elif p_level == "Оглеждаме се": col3.success(f"👀 Оглеждаме се ({count} Нови)")
                    else: col3.info(f"ℹ️ Нормално ({count} Нови)")
                    
                    if col4.button("Отвори", key=f"op_{pinfo['id']}", use_container_width=True): 
                        st.session_state.active_company = pinfo['company_name']; st.session_state.active_campaign_id = pinfo['id']; st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
        else: st.info("В момента няма активни обяви.")
            
        if st.session_state.get('user_role') in ["Супер-админ", "Администратор"]:
            st.divider()
            with st.expander("🗑️ Системно кошче (Изтрити кандидати)"):
                deleted_apps = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("is_deleted", True).execute().data or []
                if deleted_apps:
                    for d_app in deleted_apps:
                        c_name = d_app["hr_candidates"]["full_name"]
                        p_name = global_pos_map.get(d_app["position_id"], {}).get("title", "Неизвестна обява")
                        dc1, dc2, dc3 = st.columns([4, 1, 1])
                        dc1.markdown(f"**{c_name}** *(Обява: {p_name})*")
                        if dc2.button("♻️ Възстанови", key=f"res_{d_app['id']}"):
                            supabase.table("hr_applications").update({"is_deleted": False}).eq("id", d_app['id']).execute()
                            st.rerun()
                        if dc3.button("❌ Хард Делийт", key=f"hd_{d_app['id']}"):
                            supabase.table("hr_applications").delete().eq("id", d_app['id']).execute()
                            st.rerun()
                else: st.success("Кошчето е празно.")
                
        if check_permission("recruitment", "manage_positions"):
            st.divider()
            with st.expander("⚙️ Системни настройки (Суперадмин)"):
                with st.form("settings_form"):
                    st.write("📊 **Категории и Причини**")
                    nr = st.text_area("Причини за 'Отхвърлен':", value="\n".join(sys_reject_reasons))
                    nd = st.text_area("Причини за 'Отказал':", value="\n".join(sys_decline_reasons))
                    sc = st.text_area("Области на компетентност (Matrix):", value="\n".join(score_categories))
                    
                    st.divider()
                    st.write("🤖 **AI Инструкции (System Prompts)**")
                    ai_rec = st.text_area("Анализ на CV (Recruitment Engine):", value=ai_prompts.get("recruitment_analysis", ""))
                    
                    if st.form_submit_button("💾 Запиши настройките"):
                        supabase.table("hr_settings").update({"setting_value": [x.strip() for x in nr.split("\n") if x.strip()]}).eq("setting_key", "reject_reasons").execute()
                        supabase.table("hr_settings").update({"setting_value": [x.strip() for x in nd.split("\n") if x.strip()]}).eq("setting_key", "decline_reasons").execute()
                        supabase.table("hr_settings").update({"setting_value": [x.strip() for x in sc.split("\n") if x.strip()]}).eq("setting_key", "score_categories").execute()
                        supabase.table("hr_settings").update({"setting_value": {"recruitment_analysis": ai_rec}}).eq("setting_key", "ai_prompts").execute()
                        st.success("Обновено!"); st.rerun()
        return

    current_company_positions = [p for p in all_global_positions if p["company_name"] == st.session_state.active_company]
    active_camps = {p["id"]: get_pos_display_name(p) for p in current_company_positions if p.get('status') != 'Архивирана'}
    archived_camps = {p["id"]: get_pos_display_name(p) for p in current_company_positions if p.get('status') == 'Архивирана'}
    camp_options = {**active_camps, **archived_camps}
    
    if st.session_state.active_campaign_id not in camp_options:
        st.session_state.active_campaign_id = list(camp_options.keys())[0] if camp_options else None

    if not st.session_state.active_campaign_id:
        st.warning("Няма кампании в тази фирма.")
        if check_permission("recruitment", "manage_positions"):
            if st.button("➕ Създай първа кампания"): open_new_campaign_modal(st.session_state.active_company)
        return

    c_camp1, c_camp2 = st.columns([5, 1])
    with c_camp1:
        selected_pos_id = st.selectbox("Изберете кампания:", options=list(camp_options.keys()), format_func=lambda x: camp_options[x], index=list(camp_options.keys()).index(st.session_state.active_campaign_id))
        if selected_pos_id != st.session_state.active_campaign_id: 
            st.session_state.active_campaign_id = selected_pos_id
            st.rerun()
            
    with c_camp2:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if check_permission("recruitment", "manage_positions") and st.button("➕ Създай кампания", use_container_width=True):
            open_new_campaign_modal(st.session_state.active_company)

    target_pos_id = st.session_state.active_campaign_id
    pos_info = next((p for p in current_company_positions if p["id"] == target_pos_id), {})
    is_archived = (pos_info.get("status") == "Архивирана")

    if check_permission("recruitment", "manage_positions"):
        with st.expander("⚙️ Управление на обявата", expanded=False):
            st.write("📝 **Редакция на параметри**")
            with st.form("edit_pos_form"):
                e_c1, e_c2 = st.columns(2)
                with e_c1: e_s_min = st.text_input("Мин. възнаграждение (EUR)", value=pos_info.get("salary_min", ""))
                with e_c1: e_s_max = st.text_input("Макс. възнаграждение (EUR)", value=pos_info.get("salary_max", ""))
                with e_c2: e_city = st.text_input("Град", value=pos_info.get("city", ""))
                with e_c2: e_base = st.text_input("База (незадължително)", value=pos_info.get("base_location", ""))
                wt_opts = ["Присъствено", "Хибрид", "Remote"]
                e_w_type = st.selectbox("Тип работа", wt_opts, index=wt_opts.index(pos_info.get("work_type", "Присъствено")) if pos_info.get("work_type") in wt_opts else 0)
                pri_opts = ["Оглеждаме се", "Нормално", "Спешно", "🔥 ПОЖАР"]
                e_priority = st.selectbox("Приоритет (Спешност)", pri_opts, index=pri_opts.index(pos_info.get("priority", "Нормално")) if pos_info.get("priority") in pri_opts else 1)
                
                if st.form_submit_button("💾 Запиши промените"):
                    supabase.table("hr_positions").update({"salary_min": e_s_min, "salary_max": e_s_max, "city": e_city, "base_location": e_base, "work_type": e_w_type, "priority": e_priority}).eq("id", target_pos_id).execute()
                    st.success("Параметрите са обновени успешно!")
                    time.sleep(1); st.rerun()
            
            st.divider()
            ac1, ac2 = st.columns(2)
            with ac1:
                if is_archived:
                    if st.button("🟢 Активирай кампанията", use_container_width=True):
                        supabase.table("hr_positions").update({"status": "Активна"}).eq("id", target_pos_id).execute()
                        st.rerun()
                else:
                    if st.button("🗃️ Архивирай кампанията", use_container_width=True):
                        supabase.table("hr_positions").update({"status": "Архивирана"}).eq("id", target_pos_id).execute()
                        st.rerun()
            with ac2:
                if st.button("🚨 Изтрий кампанията", type="primary", use_container_width=True):
                    for a in supabase.table("hr_applications").select("id").eq("position_id", target_pos_id).execute().data or []:
                        supabase.table("hr_applications").update({"is_deleted": True}).eq("id", a["id"]).execute()
                    supabase.table("hr_positions").delete().eq("id", target_pos_id).execute()
                    st.session_state.active_campaign_id = None; st.rerun()

    if not is_archived and check_permission("recruitment", "upload_candidates"):
        with st.expander(f"📥 Импорт към '{pos_info['title']}'"):
            if "up_key" not in st.session_state: st.session_state.up_key = 0
            files = st.file_uploader("ZIP архиви", type="zip", accept_multiple_files=True, key=f"up_{st.session_state.up_key}")
            if files and st.button("▶️ Старт импорт", type="primary"):
                pb = st.progress(0); sc = 0
                for idx, f in enumerate(files):
                    try:
                        n, d, p = parse_jobs_zip(f)
                        c = supabase.table("hr_candidates").insert({"full_name": n, "raw_cv_data": d, "photo_thumbnail": p}).execute()
                        if c.data: 
                            app_res = supabase.table("hr_applications").insert({"candidate_id": c.data[0]["id"], "position_id": target_pos_id, "status": "Нов"}).execute()
                            if app_res.data: log_status_change(app_res.data[0]["id"], "None (New)", "Нов")
                            sc += 1
                    except: pass
                    pb.progress(int(((idx + 1) / len(files)) * 100))
                st.success(f"Качени {sc} кандидати!"); time.sleep(1.5); st.session_state.up_key += 1; st.rerun()

    st.divider()
    apps_raw = supabase.table("hr_applications").select("*, hr_candidates(*), hr_comments(count)").eq("position_id", target_pos_id).eq("is_deleted", False).execute().data or []
    
    # ТЪРСАЧКА
    search_query = st.text_input("🔍 Търси (Име, CV, Бележки)...")
    if search_query:
        sq = search_query.lower()
        filtered_apps = []
        for a in apps_raw:
            c_name = a["hr_candidates"]["full_name"].lower()
            cv_text = a["hr_candidates"].get("raw_cv_data", {}).get("cv_text", "").lower()
            notes_res = supabase.table("hr_comments").select("comment_text").eq("application_id", a["id"]).execute()
            notes = " ".join([cm["comment_text"] for cm in notes_res.data]).lower() if notes_res.data else ""
            if sq in c_name or sq in cv_text or sq in notes: filtered_apps.append(a)
        apps_raw = filtered_apps
    
    c_f1, c_f2 = st.columns([3, 1])
    KANBAN_STATUSES = ["Всички", "Нов", "Установи контакт", "В процес на контакт", "Възможно интервю", "Избран за интервю", "Потвърдено интервю", "Направено предложение", "Отхвърлен", "Отказал", "Преместен"]
    with c_f1: status_filter = st.pills("Филтър:", KANBAN_STATUSES, default="Всички")
    with c_f2:
        sort_order = st.selectbox("Сортиране:", ["Най-нови", "Субективна оценка (1-6)", "% по Скор-карта"], label_visibility="collapsed")
        show_backups = st.checkbox("❓ Само Резерви", value=False)
            
    if status_filter != "Всички": apps_raw = [a for a in apps_raw if a["status"] == status_filter]
    if show_backups: apps_raw = [a for a in apps_raw if a.get("is_backup") == True]
    
    if sort_order == "Субективна оценка (1-6)": apps_raw.sort(key=lambda x: int(x.get("manual_score", {}).get("subjective_rating", 0)) if isinstance(x.get("manual_score"), dict) else 0, reverse=True)
    elif sort_order == "% по Скор-карта": apps_raw.sort(key=lambda x: int(x.get("manual_score", {}).get("scorecard_percentage", 0)) if isinstance(x.get("manual_score"), dict) else 0, reverse=True)
    else: apps_raw.sort(key=lambda x: x["created_at"], reverse=True)
    
    if apps_raw:
        cols = st.columns(4)
        for i, app in enumerate(apps_raw):
            c = app["hr_candidates"]
            with cols[i % 4]:
                card_border = "#ff4b4b" if app.get("is_backup") else "#444"
                with st.container(border=True):
                    st.markdown(f"<style>div[data-testid='stVerticalBlock'] > div:nth-child({i+1}) > div {{border-color: {card_border}!important;}}</style>", unsafe_allow_html=True)
                    backup_icon = "❓ " if app.get("is_backup") else ""
                    emoji_icon = EMOJI_MAP.get(app['status'], "")
                    st.markdown(f"<div style='float:right;'>{emoji_icon}</div>{backup_icon}**{c['full_name']}** {'📦' if app.get('hr_comments', [{}])[0].get('count', 0) > 0 else ''}<br><span style='font-size:0.8em;'>{app['status']}</span>", unsafe_allow_html=True)
                    if st.button("📄 Отвори", key=f"btn_{app['id']}", use_container_width=True):
                        open_candidate_card(app["id"], c["id"], c["full_name"], app["status"], c["raw_cv_data"], c["photo_thumbnail"], app["manual_score"], all_global_positions, target_pos_id, app["created_at"], app.get("interview_details", {}), sys_reject_reasons, sys_decline_reasons, score_categories, sys_users, app.get("is_backup", False))
    else: st.info("Няма кандидати.")

    if "force_open_app_id" in st.session_state and st.session_state.force_open_app_id:
        f_app = supabase.table("hr_applications").select("*, hr_candidates(*)").eq("id", st.session_state.force_open_app_id).execute().data
        if f_app: st.session_state.force_open_app_id = None; open_candidate_card(f_app[0]["id"], f_app[0]["hr_candidates"]["id"], f_app[0]["hr_candidates"]["full_name"], f_app[0]["status"], f_app[0]["hr_candidates"]["raw_cv_data"], f_app[0]["hr_candidates"]["photo_thumbnail"], f_app[0]["manual_score"], all_global_positions, f_app[0]["position_id"], f_app[0]["created_at"], f_app[0].get("interview_details", {}), sys_reject_reasons, sys_decline_reasons, score_categories, sys_users, f_app[0].get("is_backup", False))

if __name__ == "__main__":
    render_recruitment_module()
