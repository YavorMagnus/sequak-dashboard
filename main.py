import streamlit as st
from supabase import create_client, Client
import pandas as pd
import numpy as np
import datetime
from datetime import timedelta
from dateutil.relativedelta import relativedelta
import re
import plotly.express as px
import io

# --- НАСТРОЙКИ НА СТРАНИЦАТА ---
st.set_page_config(page_title="SequaK Workspace", page_icon="🏗️", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #111111; color: #FFFFFF; }
    h1, h2, h3, h4 { color: #FFD700; } 
    /* Увеличен шрифт и удебеляване за етикетите на KPI метриките */
    .stMetric label { color: #FFD700 !important; font-size: 1.3rem !important; font-weight: 600 !important; line-height: 1.2 !important; padding-bottom: 5px; }
    div[data-testid="metric-container"] {
        background-color: #222222; border: 1px solid #FFD700; padding: 15px; border-radius: 8px; box-shadow: 0 4px 6px rgba(255, 215, 0, 0.1);
    }
    .market-metric {
        background-color: #1a1a1a; border: 1px solid #444444; padding: 10px; border-radius: 8px; text-align: center; font-size: 1.1rem;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #222222; border-radius: 4px; padding: 10px 20px; color: #FFFFFF; }
    .stTabs [aria-selected="true"] { background-color: #FFD700 !important; color: #111111 !important; font-weight: bold; }
    
    .history-card { background-color: #333333; padding: 10px; border-left: 3px solid #FFD700; margin-bottom: 10px; border-radius: 4px; }
    .client-stream { background-color: #0d2136; padding: 20px; border-radius: 8px; border-left: 5px solid #00aaff; margin-top: 10px; box-shadow: 0 2px 4px rgba(0,170,255,0.1); }
    .client-stream h4 { color: #00aaff; margin-top: 0; }
    .analytic-card { background-color: #1e1e1e; padding: 20px; border-radius: 8px; border-top: 3px solid #FFD700; margin-bottom: 20px; }
    
    /* Стилизиране на таблиците в дашборда */
    [data-testid="stDataFrame"] { background-color: #1e1e1e; border-radius: 8px; }
    
    /* Стилизиране на Radio бутоните да приличат на табове */
    div[role="radiogroup"] { flex-wrap: wrap; gap: 10px; margin-bottom: 15px; }
    </style>
    """, unsafe_allow_html=True)

# --- СВЪРЗВАНЕ С БАЗАТА ДАННИ ---
SUPABASE_URL = "https://cymfodenkklcjhjgfeau.supabase.co"
SUPABASE_KEY = "sb_publishable_blR-3tOs1E8M-gXtv8DVBA_LiEGG8Y6"

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_connection()

# ==========================================================
# --- ФАЗА 3: СИГУРНОСТ И ЛОГИН (RBAC) ---
# ==========================================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.username = None

if not st.session_state.logged_in:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h2 style='text-align: center; color: #FFD700;'>🔐 Вход в SequaK Workspace</h2>", unsafe_allow_html=True)
        with st.form("login_form"):
            user_input = st.text_input("Потребител")
            pass_input = st.text_input("Парола", type="password")
            submit_login = st.form_submit_button("Влез в системата", use_container_width=True)

            if submit_login:
                if not user_input or not pass_input:
                    st.error("Моля, въведете потребител и парола.")
                else:
                    res = supabase.table("users").select("*").eq("username", user_input).eq("password", pass_input).execute()
                    if res.data:
                        user_data = res.data[0]
                        st.session_state.logged_in = True
                        st.session_state.user_role = user_data['role']
                        st.session_state.username = user_data['username']
                        st.rerun()
                    else:
                        st.error("Грешен потребител или парола!")
    st.stop() 

# ==========================================================
# --- ГЛОБАЛНИ ФУНКЦИИ И ДАННИ ---
# ==========================================================
@st.cache_data(ttl=600)
def get_companies():
    try:
        res = supabase.table("companies").select("id, code").execute()
        return {row['code'].upper(): row['id'] for row in res.data}
    except Exception:
        return {}

COMPANY_MAP = get_companies()
COMPANY_LIST = list(COMPANY_MAP.keys()) if COMPANY_MAP else ["Няма заредени фирми"]

def standardize_company_code(excel_name):
    name = str(excel_name).lower()
    if 'ren' in name: return 'REN'
    if 'rcd' in name or ('cim' in name and 'cmx' not in name): 
        return 'CIM' if 'CIM' in COMPANY_MAP else 'RCD'
    if 'mas' in name: return 'MAS'
    if 'cmx' in name: return 'CMX'
    return str(excel_name).upper().strip()

def parse_smart_time(t_str):
    if not t_str: return None
    t_str = str(t_str).strip()
    if ':' in t_str:
        parts = t_str.split(':')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            hh, mm = int(parts[0]), int(parts[1])
            if 0 <= hh <= 23 and 0 <= mm <= 59: return f"{hh:02d}:{mm:02d}:00"
        elif len(parts) == 3 and all(p.isdigit() for p in parts):
            hh, mm, ss = int(parts[0]), int(parts[1]), int(parts[2])
            if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59: return f"{hh:02d}:{mm:02d}:{ss:02d}"
    clean_str = re.sub(r"\D", "", t_str)
    if len(clean_str) in [3, 4]:
        clean_str = clean_str.zfill(4)
        hh, mm = int(clean_str[:2]), int(clean_str[2:])
        if 0 <= hh <= 23 and 0 <= mm <= 59: return f"{hh:02d}:{mm:02d}:00"
    elif len(clean_str) in [5, 6]:
        clean_str = clean_str.zfill(6)
        hh, mm, ss = int(clean_str[:2]), int(clean_str[2:4]), int(clean_str[4:])
        if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59: return f"{hh:02d}:{mm:02d}:{ss:02d}"
    return None

ROLES_LIST = ["Служител", "Пряк ръководител", "Отговорник качество", "Управител", "Контролинг", "RXG-адм", "CEO", "Друг"]
CONCLUSIONS = ["Техническа грешка", "Липса на знания/умения", "Нарушение", "Не сме сигурни", "Липса на ресурс", "Дезорганизация", "Идея за подобрение", "Друго", "Грешим/няма проблем"]
RECOMMENDATIONS = ["Техническа корекция", "Обучение", "Наказание", "Проверка (поле)", "Планиране на ресурс", "Реорганизация", "Обсъждане с колеги", "Друго", "Нищо"]
TERMINAL_STATUSES = ["Приключено", "Сгрешен/Анулиран"]

def get_related_signals(ticket, df_complaints):
    if df_complaints is None or df_complaints.empty:
        return pd.DataFrame()
        
    c_phone = str(ticket.get('client_phone', '')).strip()
    c_email = str(ticket.get('client_email', '')).strip()
    c_eik = str(ticket.get('client_eik', '')).strip()
    
    if not c_phone and not c_email and not c_eik:
        return pd.DataFrame()
        
    t_date = pd.to_datetime(ticket.get('event_datetime'), errors='coerce')
    if pd.isna(t_date): return pd.DataFrame()
    if t_date.tzinfo is not None: t_date = t_date.replace(tzinfo=None)
    
    mask = (df_complaints['id'] != ticket['id'])
    
    comp_dates = pd.to_datetime(df_complaints['event_datetime'], errors='coerce')
    if comp_dates.dt.tz is not None: comp_dates = comp_dates.dt.tz_localize(None)
    
    date_diff = (comp_dates - t_date).abs()
    mask &= (date_diff.dt.days <= 30)
    
    match_cond = pd.Series(False, index=df_complaints.index)
    if c_phone: match_cond |= (df_complaints['client_phone'].astype(str).str.strip() == c_phone)
    if c_email: match_cond |= (df_complaints['client_email'].astype(str).str.strip() == c_email)
    if c_eik: match_cond |= (df_complaints['client_eik'].astype(str).str.strip() == c_eik)
    
    return df_complaints[mask & match_cond]

@st.dialog("Картон на сигнала", width="large")
def show_ticket_details(ticket, df_complaints_param):
    related_df = get_related_signals(ticket, df_complaints_param)
    
    if not related_df.empty:
        st.error(f"⚠️ **ВНИМАНИЕ: Открити са {len(related_df)} свързани сигнала за този клиент през последните 30 дни!**")
        for _, dup_row in related_df.iterrows():
            dup_date = pd.to_datetime(dup_row.get('event_datetime')).strftime('%d.%m.%Y')
            dup_status = dup_row.get('current_status', 'Неопределен')
            with st.expander(f"Свързан сигнал от {dup_date} ({dup_row.get('Фирма', '')}) - Статус: {dup_status}"):
                st.markdown(f"**Канал:** {dup_row.get('channel', '-')} | **Касае:** {dup_row.get('case_type', '-')}")
                st.markdown(f"**Описание:** {dup_row.get('description', '-')}")
                st.info("💡 *Бележка: За да редактирате този свързан сигнал, използвайте Търсачката.*")
        st.markdown("---")

    st.markdown(f"### Сигнал от: **{ticket.get('client_name', 'Неизвестен')}**")
    st.caption(f"Дата: {ticket.get('event_datetime', '')} | Канал: {ticket.get('channel', '')} | Касае: {ticket.get('case_type', '')}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Телефон:** {ticket.get('client_phone', '-')}")
        st.write(f"**Имейл:** {ticket.get('client_email', '-')}")
        st.write(f"**ЕИК:** {ticket.get('client_eik', '-')}")
    with col2:
        st.write(f"**Договор №:** {ticket.get('contract_number', '-')}")
        st.write(f"**Машина/и:** {ticket.get('machines', '-')}")
        st.write(f"**Аудио запис (номер):** {ticket.get('call_number', '-')}")
    
    st.info(f"**Описание:** {ticket.get('description', '')}")
    st.markdown("---")

    st.subheader("📋 Хронология на действията")
    history_res = supabase.table("complaint_history").select("*").eq("complaint_id", ticket['id']).order("created_at", desc=False).execute()
    history_data = history_res.data
    
    if not history_data:
        st.write("Все още няма предприети действия.")
    else:
        for record in history_data:
            created_at_fmt = pd.to_datetime(record['created_at']).strftime('%d.%m.%Y %H:%M')
            deadline_str = f" | Срок: {record['deadline_date']}" if record.get('deadline_date') else ""
            assigned_str = f" | Към: {record['assigned_to']}" if record.get('assigned_to') else ""
            st.markdown(f"""
            <div class="history-card">
                <strong>{created_at_fmt} - {record['action_type']}</strong> {assigned_str} {deadline_str}<br>
                <em>{record.get('action_details', '')}</em>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    
    current_status = ticket.get('current_status', 'Чака заключение и препоръка')
    
    if current_status == "Сгрешен/Анулиран":
        st.error("🚫 Този сигнал е маркиран като СГРЕШЕН / АНУЛИРАН и е заключен за редакция.")
        return
    elif current_status == "Приключено":
        st.success("✅ Този сигнал е ПРИКЛЮЧЕН.")
        return

    st.subheader("🤝 Комуникация с клиент (Външен процес)")
    current_client_action = ticket.get('client_action_needed', False)
    new_client_action = st.toggle("Извънреден диспут: Очаква се действие с клиента", value=current_client_action, key=f"tgl_{ticket['id']}")
    
    if new_client_action != current_client_action:
        supabase.table("complaints").update({"client_action_needed": new_client_action}).eq("id", ticket['id']).execute()
        action_text = "Активиран" if new_client_action else "Дезактивиран"
        supabase.table("complaint_history").insert({
            "complaint_id": ticket['id'],
            "action_type": f"Диспут с клиент: {action_text}",
            "created_by": st.session_state.username
        }).execute()
        st.rerun()

    if new_client_action:
        st.markdown('<div class="client-stream"><h4>Въвеждане на комуникация</h4>', unsafe_allow_html=True)
        client_step = st.selectbox("Изберете етап", ["1. Изпратен мейл до О.К.", "2. Предложение към клиент (от О.К.)", "3. Удовлетвореност (Финал)"], key=f"cs_{ticket['id']}")
        
        c_details = ""
        c_deadline = None
        
        if client_step == "1. Изпратен мейл до О.К.":
            mail_date = st.date_input("Дата на мейла", key=f"md_{ticket['id']}")
            c_details = f"Изпратен имейл на: {mail_date.strftime('%d.%m.%Y')}"
        elif client_step == "2. Предложение към клиент (от О.К.)":
            c_details = st.text_area("Въведете направеното предложение", key=f"pt_{ticket['id']}")
            c_deadline = st.date_input("Очакван отговор до (Срок)", key=f"pd_{ticket['id']}")
        elif client_step == "3. Удовлетвореност (Финал)":
            is_satisfied = st.radio("Удовлетворен ли е клиентът?", ["Да", "Не"], horizontal=True, key=f"sat_{ticket['id']}")
            follow_up = st.text_input("Коментар (ако НЕ е удовлетворен)", key=f"fc_{ticket['id']}")
            c_details = f"Клиентът е удовлетворен: {is_satisfied}. Коментар: {follow_up}"

        if st.button("💾 Запиши действие с клиент", key=f"btn_c_{ticket['id']}"):
            history_payload = {
                "complaint_id": ticket['id'], "action_type": f"Клиент: {client_step.split('. ')[1]}",
                "action_details": c_details, "deadline_date": str(c_deadline) if c_deadline else None,
                "created_by": st.session_state.username
            }
            supabase.table("complaint_history").insert(history_payload).execute()
            st.success("Действието с клиента е записано в хронологията!")
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")

    st.subheader("⚙️ Продължаване на процеса (Вътрешен)")
    st.write(f"Текущ мастър статус: **{current_status}**")
    
    if current_status == "Чака проверка":
        st.warning("В момента се изисква проверка според последната стъпка.")
        check_result = st.text_input("До какво доведе проверката? (до 100 символа)", max_chars=100, key=f"cr_{ticket['id']}")
        if st.button("Приключи проверката", type="primary", key=f"btn_chk_{ticket['id']}"):
            if not check_result:
                st.error("Моля, въведете резултат от проверката.")
            else:
                supabase.table("complaint_history").insert({
                    "complaint_id": ticket['id'], "action_type": "Резултат от проверка", 
                    "action_details": check_result, "created_by": st.session_state.username
                }).execute()
                supabase.table("complaints").update({"current_status": "Чака заключение и препоръка", "current_deadline": None}).eq("id", ticket['id']).execute()
                st.rerun()
    else:
        new_conc = st.selectbox("Заключение контролинг", ["Избери..."] + CONCLUSIONS, key=f"nc_{ticket['id']}")
        new_rec = st.selectbox("Препоръка контролинг", ["Избери..."] + RECOMMENDATIONS, key=f"nr_{ticket['id']}")
        field_details = ""
        if new_rec == "Проверка (поле)":
            field_details = st.text_input("Какво точно ще се проверява?", max_chars=100, key=f"fd_{ticket['id']}")
            
        assignee = st.selectbox("Възложено на (Роля)", ["Избери..."] + ROLES_LIST, key=f"as_{ticket['id']}")
        deadline = st.date_input("Ръчен срок (Край до)", value=None, key=f"dl_{ticket['id']}")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            save_step = st.button("💾 Запази следваща стъпка", type="primary", key=f"btn_s_{ticket['id']}")
        with col_btn2:
            close_ticket = st.button("✅ ПРИКЛЮЧИ СИГНАЛА", key=f"btn_x_{ticket['id']}")

        if save_step:
            if new_conc == "Избери..." or new_rec == "Избери...": st.error("Моля, изберете Заключение и Препоръка!")
            elif new_rec == "Проверка (поле)" and not field_details: st.error("Моля, опишете какво ще се проверява.")
            elif new_rec != "Проверка (поле)" and assignee == "Избери...": st.error("Моля, изберете на кого възлагате изпълнението (Роля)!")
            else:
                next_status = "Чака проверка" if new_rec == "Проверка (поле)" else "Чака приключване"
                action_text = f"Заключение: {new_conc} | Препоръка: {new_rec}"
                full_details = f"{action_text}. Детайли: {field_details}" if field_details else action_text
                supabase.table("complaint_history").insert({
                    "complaint_id": ticket['id'], "action_type": "Назначена стъпка", "action_details": full_details,
                    "assigned_to": assignee if assignee != "Избери... " else None, "deadline_date": str(deadline) if deadline else None,
                    "created_by": st.session_state.username
                }).execute()
                supabase.table("complaints").update({"current_status": next_status, "current_deadline": str(deadline) if deadline else None}).eq("id", ticket['id']).execute()
                st.rerun()
                
        if close_ticket:
            supabase.table("complaints").update({"current_status": "Приключено", "current_deadline": None}).eq("id", ticket['id']).execute()
            supabase.table("complaint_history").insert({"complaint_id": ticket['id'], "action_type": "Сигналът е приключен", "created_by": st.session_state.username}).execute()
            st.rerun()

    st.markdown("---")
    with st.expander("🚫 Опции за анулиране (Сгрешен запис)"):
        st.warning("Внимание: Анулирането ще преустанови следенето на този сигнал.")
        cancel_reason = st.text_input("Причина за анулиране (задължително):", key=f"cancel_reason_{ticket['id']}")
        if st.button("ПОТВЪРДИ АНУЛИРАНЕТО", type="secondary", key=f"btn_cancel_{ticket['id']}"):
            if not cancel_reason.strip(): st.error("Моля, въведете причина за анулирането.")
            else:
                supabase.table("complaint_history").insert({
                    "complaint_id": ticket['id'], "action_type": "Сигналът е АНУЛИРАН", 
                    "action_details": f"Причина: {cancel_reason}", "created_by": st.session_state.username
                }).execute()
                supabase.table("complaints").update({"current_status": "Сгрешен/Анулиран", "current_deadline": None}).eq("id", ticket['id']).execute()
                st.rerun()

def show_company_tickets(company_code, df_complaints):
    col_title, col_btn = st.columns([4, 1])
    with col_title: st.subheader(f"📋 Всички сигнали за {company_code}")
    with col_btn:
        if st.button("✖ Затвори списъка", use_container_width=True):
            st.session_state.active_company = None
            st.rerun()
            
    if df_complaints.empty:
        st.write("Няма данни.")
        return
        
    comp_df = df_complaints[df_complaints['Фирма'] == company_code].sort_values(by="event_datetime", ascending=False)
    if comp_df.empty:
        st.info("Няма регистрирани сигнали за тази фирма.")
        return

    for _, row in comp_df.iterrows():
        status = row.get('current_status', 'Неопределен')
        client = row.get('client_name', 'Неизвестен')
        has_client_action = row.get('client_action_needed', False)
        
        is_overdue = False
        deadline_val = row.get('current_deadline')
        if pd.notna(deadline_val) and status not in TERMINAL_STATUSES:
            dt_obj = pd.to_datetime(deadline_val, errors='coerce')
            if pd.notna(dt_obj) and dt_obj.date() < datetime.date.today():
                is_overdue = True
                
        has_dup = not get_related_signals(row, df_complaints).empty
        dup_badge = " <span style='color:#ff4b4b;' title='Има свързани сигнали (30 дни)'>🚨</span>" if has_dup else ""
                
        colA, colB, colC = st.columns([3, 2, 1])
        with colA:
            strike = "s" if status == "Сгрешен/Анулиран" else "strong"
            client_display = f"👤 <{strike}>{client}</{strike}>{dup_badge}" + (" <span style='color:#00aaff;'>🔵 [В диспут]</span>" if has_client_action and status not in TERMINAL_STATUSES else "")
            st.markdown(client_display, unsafe_allow_html=True)
            dt_str = pd.to_datetime(row.get('event_datetime')).strftime('%d.%m.%Y %H:%M') if pd.notna(row.get('event_datetime')) else ""
            st.caption(f"Дата: {dt_str}")
        with colB:
            color = "gray" if status == "Сгрешен/Анулиран" else "red" if is_overdue else "green" if status == "Приключено" else "orange"
            st.markdown(f"Статус: <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
            if is_overdue: st.markdown("<span style='color:red; font-size:0.8em;'>⚠️ Просрочен!</span>", unsafe_allow_html=True)
        with colC:
            if st.button("Отвори", key=f"btn_open_{row['id']}"):
                show_ticket_details(row.to_dict(), df_complaints)
        st.divider()

# ==========================================================
# --- СТРАНИЧНО МЕНЮ (SIDEBAR) ДИНАМИЧНО ---
# ==========================================================
st.sidebar.title("🏗️ SequaK Меню")

available_pages = ["📊 ПП - Дашборд", "📈 Анализи и Справки (РО)"]
if st.session_state.user_role == "Администратор":
    available_pages.insert(1, "📝 Регистър Оплаквания (РО)")

page = st.sidebar.radio("Изберете модул:", available_pages)

st.sidebar.markdown("---")
st.sidebar.write(f"👤 **Профил:** {st.session_state.username}")
st.sidebar.write(f"🛡️ **Достъп:** {st.session_state.user_role}")

if st.sidebar.button("🚪 Изход от системата", use_container_width=True):
    st.session_state.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("Входът е защитен. Версия 4.6 (Pro-Fix)")

# ==========================================================
# --- СТРАНИЦА 1: ОПЕРАТИВЕН ДАШБОРД (ПП) ---
# ==========================================================
if page == "📊 ПП - Дашборд":
    try:
        response_pp = supabase.table("missed_profits").select("*, companies(code)").limit(100000).execute()
        df_pp = pd.DataFrame(response_pp.data)
        
        if not df_pp.empty:
            df_pp['company_code'] = df_pp['companies'].apply(lambda x: x.get('code', 'UNKNOWN').upper() if isinstance(x, dict) else 'UNKNOWN')
            df_pp['clean_machine'] = df_pp['item_tag'].apply(lambda x: str(x).split('|')[-1].strip() if '|' in str(x) else str(x))
            df_pp['event_date'] = pd.to_datetime(df_pp['event_date'], errors='coerce')
            if df_pp['event_date'].dt.tz is not None:
                df_pp['event_date'] = df_pp['event_date'].dt.tz_localize(None)
                
            # КОРИГИРАНА ЛОГИКА ЗА ЧЕТЕНЕ НА 'consultant'
            if 'consultant' not in df_pp.columns:
                df_pp['consultant'] = 'Неизвестен'
            else:
                df_pp['consultant'] = df_pp['consultant'].fillna('Неизвестен')
        else:
            df_pp['company_code'] = 'UNKNOWN'
            df_pp['clean_machine'] = 'UNKNOWN'
            df_pp['consultant'] = 'Неизвестен'
            df_pp['event_date'] = pd.to_datetime(datetime.date.today())

        st.title("📊 ПП (Пропуснати ползи) - Дашборд")
        
        if df_pp.empty:
            st.info("В момента няма заредени данни за пропуснати ползи.")
        else:
            min_date = df_pp['event_date'].min().date() if pd.notna(df_pp['event_date'].min()) else datetime.date.today()
            max_date = df_pp['event_date'].max().date() if pd.notna(df_pp['event_date'].max()) else datetime.date.today()
            
            st.markdown("### 🔍 Избор на период")
            col_f1, col_f2 = st.columns([1, 2])
            with col_f1:
                date_range = st.date_input("Покажи данни за времето от-до:", value=(min_date, max_date), min_value=min_date, max_value=max_date)
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                df_filtered = df_pp[(df_pp['event_date'].dt.date >= start_date) & (df_pp['event_date'].dt.date <= end_date)].copy()
            else:
                df_filtered = df_pp.copy()

            st.markdown("---")
            
            if 'resolution_status' in df_filtered.columns:
                df_filtered['safe_status_kpi'] = df_filtered['resolution_status'].astype(str).str.lower().str.strip()
                valid_statuses = ['отказва се', 'нямаме наличност']
                
                df_kpi = df_filtered[df_filtered['safe_status_kpi'].isin(valid_statuses)]
                
                total_eur = df_kpi['total_value_eur'].sum() if not df_kpi.empty else 0
                total_count = len(df_kpi)
                avg_eur = total_eur / total_count if total_count > 0 else 0
                
                # Изчисления за пазарния интерес
                total_all_searches = len(df_filtered)
                service_rate = ((total_all_searches - total_count) / total_all_searches * 100) if total_all_searches > 0 else 0
                top_tag_overall = df_filtered['clean_machine'].mode()[0] if not df_filtered.empty else "-"
            else:
                total_eur, total_count, avg_eur, total_all_searches, service_rate, top_tag_overall = 0, 0, 0, 0, 0, "-"

            # --- ОСНОВНИ KPI КАРТИ (€) ---
            st.markdown('<div class="analytic-card">', unsafe_allow_html=True)
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("Пропуснати ползи (неналичност/отказ)", f"€ {total_eur:,.2f}")
            kpi2.metric("Общо броя необслужени", f"{total_count} бр.")
            kpi3.metric("Средно на брой необслужено", f"€ {avg_eur:,.2f}")
            
            # --- ВТОРИЧНИ KPI КАРТИ (Пазарен обем) ---
            st.markdown("<br>", unsafe_allow_html=True)
            mk1, mk2, mk3 = st.columns(3)
            with mk1: st.markdown(f'<div class="market-metric">🎯 Общ пазарен интерес: <b>{total_all_searches}</b> запитвания</div>', unsafe_allow_html=True)
            with mk2: st.markdown(f'<div class="market-metric">📈 Коефициент на обслужване: <b>{service_rate:.1f}%</b></div>', unsafe_allow_html=True)
            with mk3: st.markdown(f'<div class="market-metric">🔥 Най-търсено общо: <b>{top_tag_overall}</b></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            col_ch1, col_ch2 = st.columns([1.5, 1])
            
            with col_ch1:
                st.subheader("📑 Анализ по Статус / Фирми / Консултанти")
                tab_table, tab_chart, tab_consultants = st.tabs(["📊 Детайли по Статус", "📈 Обща Графика", "👨‍💼 По Консултанти (КА)"])
                
                with tab_table:
                    if not df_filtered.empty and 'resolution_status' in df_filtered.columns:
                        df_status = df_filtered.copy()
                        df_status['safe_status'] = df_status['resolution_status'].astype(str).str.lower().str.strip()
                        
                        df_status['refused_count'] = df_status['safe_status'].str.contains('отказва се', na=False).astype(int)
                        df_status['refused_sum'] = np.where(df_status['safe_status'].str.contains('отказва се', na=False), df_status['total_value_eur'], 0)
                        
                        df_status['no_stock_count'] = df_status['safe_status'].str.contains('нямаме наличност', na=False).astype(int)
                        df_status['no_stock_sum'] = np.where(df_status['safe_status'].str.contains('нямаме наличност', na=False), df_status['total_value_eur'], 0)
                        
                        df_status['not_offered_count'] = df_status['safe_status'].str.contains('не предлагаме', na=False).astype(int)

                        status_summary = df_status.groupby('company_code')[
                            ['refused_count', 'refused_sum', 'no_stock_count', 'no_stock_sum', 'not_offered_count']
                        ].sum().reset_index()
                        
                        status_summary.columns = [
                            'Фирма', 
                            'Отказва се (Бр.)', 'Отказва се (€)', 
                            'Няма наличност (Бр.)', 'Няма наличност (€)', 
                            'Не предлагаме (Бр.)'
                        ]
                        
                        status_summary = status_summary.sort_values(by='Няма наличност (€)', ascending=False)
                        
                        status_summary['Общо (Бр.)'] = status_summary['Отказва се (Бр.)'] + status_summary['Няма наличност (Бр.)'] + status_summary['Не предлагаме (Бр.)']
                        status_summary['Общо (€)'] = status_summary['Отказва се (€)'] + status_summary['Няма наличност (€)']
                        
                        total_row = pd.DataFrame({
                            'Фирма': ['ОБЩО'],
                            'Отказва се (Бр.)': [status_summary['Отказва се (Бр.)'].sum()],
                            'Отказва се (€)': [status_summary['Отказва се (€)'].sum()],
                            'Няма наличност (Бр.)': [status_summary['Няма наличност (Бр.)'].sum()],
                            'Няма наличност (€)': [status_summary['Няма наличност (€)'].sum()],
                            'Не предлагаме (Бр.)': [status_summary['Не предлагаме (Бр.)'].sum()],
                            'Общо (Бр.)': [status_summary['Общо (Бр.)'].sum()],
                            'Общо (€)': [status_summary['Общо (€)'].sum()]
                        })
                        
                        status_summary = pd.concat([total_row, status_summary], ignore_index=True)

                        styled_status = status_summary.style.format({
                            'Отказва се (€)': '€ {:,.2f}',
                            'Няма наличност (€)': '€ {:,.2f}',
                            'Общо (€)': '€ {:,.2f}'
                        }).set_properties(**{'color': '#FFD700'})
                        
                        st.dataframe(styled_status, use_container_width=True, hide_index=True)
                    else:
                        st.write("Няма данни за статуси в избрания период.")
                
                with tab_chart:
                    if not df_filtered.empty:
                        company_group = df_filtered.groupby('company_code')['total_value_eur'].sum().reset_index()
                        company_group = company_group.sort_values('total_value_eur', ascending=False)
                        fig = px.bar(company_group, x='company_code', y='total_value_eur', 
                                     labels={'company_code': 'Фирма', 'total_value_eur': 'Стойност (€)'},
                                     color='company_code', color_discrete_sequence=px.colors.sequential.Plasma)
                        fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color='white', showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.write("Няма данни за избрания период.")

                with tab_consultants:
                    if not df_filtered.empty and 'consultant' in df_filtered.columns:
                        # Групиране по консултант (КА)
                        cons_group = df_filtered.groupby('consultant').agg(
                            total_calls=('resolution_status', 'count'),
                            missed_calls=('safe_status_kpi', lambda x: x.isin(['отказва се', 'нямаме наличност']).sum())
                        ).reset_index()
                        
                        # Премахваме празни или невалидни
                        cons_group = cons_group[(cons_group['total_calls'] > 0) & (cons_group['consultant'] != 'Неизвестен')]
                        
                        if not cons_group.empty:
                            cons_group['missed_pct'] = (cons_group['missed_calls'] / cons_group['total_calls']) * 100
                            
                            max_missed = cons_group.loc[cons_group['missed_pct'].idxmax()]
                            min_missed = cons_group.loc[cons_group['missed_pct'].idxmin()]
                            
                            st.markdown(f"**🔴 Най-голям % изпуснати ползи:** {max_missed['consultant']} ({max_missed['missed_pct']:.1f}% от техните запитвания)")
                            st.markdown(f"**🟢 Най-малък % изпуснати ползи:** {min_missed['consultant']} ({min_missed['missed_pct']:.1f}% от техните запитвания)")
                            
                            cons_group.columns = ['Консултант (КА)', 'Общо Запитвания (Бр.)', 'Изпуснати Ползи (Бр.)', 'Процент Изпуснати (%)']
                            styled_cons = cons_group.sort_values('Процент Изпуснати (%)', ascending=False).style.format({
                                'Процент Изпуснати (%)': '{:.1f}%'
                            }).set_properties(**{'color': '#00aaff'})
                            
                            st.dataframe(styled_cons, use_container_width=True, hide_index=True)
                        else:
                            st.info("Няма достатъчно данни с попълнени Консултанти (КА).")
                    else:
                        st.write("Колонката 'КА' липсва в данните.")

            with col_ch2:
                st.subheader("🏆 Топ 15 Машини")
                
                status_filter = st.radio(
                    "Срез по статус на обаждането:",
                    ["Всички", "Информира се", "Отказва се", "Нямаме наличност", "Не предлагаме"],
                    horizontal=True
                )

                if status_filter != "Всички":
                    df_top15_base = df_filtered[df_filtered['resolution_status'].astype(str).str.strip().str.lower() == status_filter.lower()]
                else:
                    df_top15_base = df_filtered.copy()

                tab_all, tab_ren, tab_cim, tab_mas, tab_cmx = st.tabs(["Всички", "REN", "CIM", "MAS", "CMX"])
                
                def show_top_15(df_to_show, current_status):
                    if df_to_show.empty or 'clean_machine' not in df_to_show.columns:
                        st.write("Няма данни за този срез.")
                        return

                    if current_status in ["Не предлагаме", "Информира се"]:
                        top_15 = df_to_show.groupby('clean_machine').size().reset_index(name='Брой')
                        top_15 = top_15.nlargest(15, 'Брой')
                        top_15.columns = ['Машина', 'Търсения (бр.)']
                        styled_df = top_15.style.format({'Търсения (бр.)': '{} бр.'}).set_properties(**{'color': '#FFD700'})
                    else:
                        top_15 = df_to_show.groupby('clean_machine')['total_value_eur'].sum().nlargest(15).reset_index()
                        top_15.columns = ['Машина', 'Изпусната сума (€)']
                        styled_df = top_15.style.format({'Изпусната сума (€)': '€ {:,.2f}'}).set_properties(**{'color': '#FFD700'})

                    st.dataframe(styled_df, use_container_width=True, hide_index=True)

                with tab_all: show_top_15(df_top15_base, status_filter)
                with tab_ren: show_top_15(df_top15_base[df_top15_base['company_code'] == 'REN'], status_filter)
                with tab_cim: show_top_15(df_top15_base[df_top15_base['company_code'].isin(['CIM', 'RCD'])], status_filter)
                with tab_mas: show_top_15(df_top15_base[df_top15_base['company_code'] == 'MAS'], status_filter)
                with tab_cmx: show_top_15(df_top15_base[df_top15_base['company_code'] == 'CMX'], status_filter)
            
            st.markdown("---")
            with st.expander("📥 Изтегляне на филтрираните данни (Excel)"):
                st.write(f"Готови за изтегляне: **{len(df_filtered)}** записа (отговарящи на избрания по-горе период).")
                
                buffer_pp = io.BytesIO()
                export_df_pp = df_filtered.copy()
                
                if 'companies' in export_df_pp.columns:
                    export_df_pp = export_df_pp.drop(columns=['companies'])
                
                with pd.ExcelWriter(buffer_pp, engine='openpyxl') as writer:
                    export_df_pp.to_excel(writer, index=False, sheet_name='Пропуснати_Ползи')
                
                st.download_button(
                    label="💾 Изтегли като .xlsx",
                    data=buffer_pp.getvalue(),
                    file_name=f"SequaK_PP_{start_date}_to_{end_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )

    except Exception as e:
        st.error(f"Възникна грешка: {e}")

    # ОГРАНИЧЕНИЕ ЗА ВНОС: Само Администратор може да вижда този панел
    if st.session_state.user_role == "Администратор":
        st.markdown("---")
        st.header("📥 Внос на данни (Пропуснати ползи)")
        uploaded_file = st.file_uploader("Изберете Excel файл (.xlsx)", type=["xlsx", "xls"])
        if uploaded_file is not None:
            try:
                xls_file = pd.ExcelFile(uploaded_file)
                selected_sheet = st.selectbox("Изберете страница:", xls_file.sheet_names)
                df_uploaded = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
                st.success(f"✅ Заредена страница '{selected_sheet}'.")
                
                if st.button("🚀 ИЗПРАТИ ДАННИТЕ КЪМ БАЗАТА", type="primary"):
                    with st.spinner("Проверка за дубликати и запис... моля изчакайте!"):
                        # ТУК ДОБАВЯМЕ "КА"
                        required_cols = ['Дата', 'Тагове', 'Обща стойност', 'Резултат', 'Фирма', 'КА']
                        if all(col in df_uploaded.columns for col in required_cols):
                            df_to_insert = df_uploaded[required_cols].copy()
                            # ПРЕИМЕНУВАМЕ "КА" НА consultant
                            df_to_insert = df_to_insert.rename(columns={
                                'Дата': 'event_date', 'Тагове': 'item_tag',
                                'Обща стойност': 'total_value_eur', 'Резултат': 'resolution_status',
                                'КА': 'consultant'
                            })
                            def get_smart_transaction_type(tag):
                                tag_str = str(tag)
                                if 'Наем' in tag_str: return 'Наем'
                                elif 'Поръчка' in tag_str or 'Продажба' in tag_str: return 'Продажба'
                                return 'Неопределен'
                            df_to_insert['transaction_type'] = df_to_insert['item_tag'].apply(get_smart_transaction_type)
                            df_to_insert['event_date'] = pd.to_datetime(df_to_insert['event_date'], dayfirst=True).dt.strftime('%Y-%m-%d %H:%M:%S')
                            
                            if df_to_insert['total_value_eur'].dtype == object:
                                df_to_insert['total_value_eur'] = df_to_insert['total_value_eur'].astype(str).str.replace(r'\s+', '', regex=True).str.replace(',', '.')
                            df_to_insert['total_value_eur'] = pd.to_numeric(df_to_insert['total_value_eur'], errors='coerce').fillna(0)
                            
                            df_to_insert['resolution_status'] = df_to_insert['resolution_status'].fillna('Неопределен')
                            df_to_insert['mapped_code'] = df_to_insert['Фирма'].apply(standardize_company_code)
                            df_to_insert['company_id'] = df_to_insert['mapped_code'].map(COMPANY_MAP)
                            df_to_insert['consultant'] = df_to_insert['consultant'].fillna('Неизвестен').astype(str)
                            
                            df_to_insert = df_to_insert.dropna(subset=['item_tag', 'event_date', 'company_id'])
                            df_to_insert = df_to_insert.replace({float('nan'): None, np.nan: None})
                            
                            # --- ВЪЗСТАНОВЕН ПЕРФЕКТЕН ФИЛТЪР НА ПОТРЕБИТЕЛЯ ---
                            existing_fingerprints = set()
                            if not df_pp.empty and 'event_date' in df_pp.columns:
                                db_cmp = df_pp['company_code'].astype(str).str.strip().str.upper()
                                db_tag = df_pp['item_tag'].astype(str).str.strip().str.lower()
                                db_date = pd.to_datetime(df_pp['event_date'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
                                db_val = pd.to_numeric(df_pp['total_value_eur'], errors='coerce').fillna(0).round(2).apply(lambda x: f"{x:.2f}")
                                
                                existing_sigs = db_cmp + "|" + db_tag + "|" + db_date + "|" + db_val
                                existing_fingerprints = set(existing_sigs)

                            new_cmp = df_to_insert['mapped_code'].astype(str).str.strip().str.upper()
                            new_tag = df_to_insert['item_tag'].astype(str).str.strip().str.lower()
                            new_date = pd.to_datetime(df_to_insert['event_date'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
                            new_val = pd.to_numeric(df_to_insert['total_value_eur'], errors='coerce').fillna(0).round(2).apply(lambda x: f"{x:.2f}")

                            df_to_insert['fingerprint'] = new_cmp + "|" + new_tag + "|" + new_date + "|" + new_val
                            
                            df_to_insert = df_to_insert.drop_duplicates(subset=['fingerprint'])
                            df_final = df_to_insert[~df_to_insert['fingerprint'].isin(existing_fingerprints)].copy()
                            df_final = df_final.drop(columns=['Фирма', 'mapped_code', 'fingerprint'])
                            
                            if df_final.empty:
                                st.info("⚠️ Всички тези данни вече са качени в базата! Няма нови записи за добавяне.")
                            else:
                                records = df_final.to_dict(orient='records')
                                # Тук разчитаме на upsert, за да се възползваме и от SQL правилото като втори щит
                                supabase.table("missed_profits").upsert(records, on_conflict="event_date, item_tag, total_value_eur, company_id").execute()
                                st.success(f"🎉 Успешно добавени {len(df_final)} НОВИ записа! Презареждам...")
                                st.rerun() 
                        else:
                            st.warning(f"⚠️ Липсват нужни колони. Уверете се, че Екселът съдържа следните колонки точно с тези имена: {', '.join(required_cols)}")
            except Exception as e:
                st.error(f"Възникна грешка: {e}")

# ==========================================================
# --- СТРАНИЦА 2: РЕГИСТЪР ОПЛАКВАНИЯ (РО) ---
# ==========================================================
elif page == "📝 Регистър Оплаквания (РО)":
    st.title("📝 Управление на Сигнали (РО) - Фаза 2")
    
    if 'active_company' not in st.session_state:
        st.session_state.active_company = None
        
    try:
        res = supabase.table("complaints").select("*, companies(code)").limit(100000).execute()
        df_complaints = pd.DataFrame(res.data)
        if not df_complaints.empty:
            df_complaints['Фирма'] = df_complaints['companies'].apply(lambda x: x.get('code', '') if isinstance(x, dict) else '')
    except Exception as e:
        st.error(f"Грешка при връзка с DB: {e}")
        df_complaints = pd.DataFrame()
        
    tab_list, tab_new = st.tabs(["👁️ Птичи поглед (Дашборд)", "➕ Въвеждане на нов сигнал"])
    
    with tab_list:
        st.markdown("### Активно следене на процеси по фирми")
        st.caption("Кликнете върху бутона под дадена фирма, за да видите детайли и просрочия.")

        NUM_COLS_PER_ROW = 4
        cols = st.columns(NUM_COLS_PER_ROW)
        
        for i, comp in enumerate(COMPANY_LIST):
            with cols[i % NUM_COLS_PER_ROW]:
                with st.container(border=True):
                    st.markdown(f"<h3 style='text-align: center; color: #FFD700; margin-top: 0;'>{comp}</h3>", unsafe_allow_html=True)
                    
                    if not df_complaints.empty and 'Фирма' in df_complaints.columns:
                        comp_data = df_complaints[df_complaints['Фирма'] == comp]
                        unresolved = len(comp_data[~comp_data['current_status'].isin(TERMINAL_STATUSES)])
                        in_dispute = len(comp_data[(~comp_data['current_status'].isin(TERMINAL_STATUSES)) & (comp_data['client_action_needed'] == True)])
                        
                        overdue = 0
                        for _, row in comp_data.iterrows():
                            dl_val = row.get('current_deadline')
                            if row.get('current_status') not in TERMINAL_STATUSES and pd.notna(dl_val):
                                dt_obj = pd.to_datetime(dl_val, errors='coerce')
                                if pd.notna(dt_obj) and dt_obj.date() < datetime.date.today():
                                    overdue += 1
                    else:
                        unresolved, overdue, in_dispute = 0, 0, 0
                    
                    st.write(f"**Неприключени:** {unresolved} бр.")
                    st.write(f"**Просрочени:** {'🔴 ' + str(overdue) if overdue > 0 else '0'} бр.")
                    st.write(f"**В диспут:** {'🔵 ' + str(in_dispute) if in_dispute > 0 else '0'} бр.")
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    if st.button(f"🔍 Отвори списък", key=f"open_dash_{comp}", use_container_width=True):
                        st.session_state.active_company = comp
                        st.rerun()

        if st.session_state.active_company:
            st.markdown("---")
            show_company_tickets(st.session_state.active_company, df_complaints)
            
        st.markdown("---")
        st.markdown("### 🔍 Търсачка")
        search_query = st.text_input("Търсене по: Име, Телефон, ЕИК, Имейл, Договор, Машина или Аудио запис", placeholder="Въведете текст и натиснете Enter...", key="global_search").strip()
        
        if not df_complaints.empty:
            if search_query:
                q = search_query.lower()
                search_cols = ['client_name', 'client_phone', 'client_email', 'client_eik', 'contract_number', 'machines', 'call_number']
                mask = False
                for col in search_cols:
                    if col in df_complaints.columns:
                        mask = mask | df_complaints[col].fillna('').astype(str).str.lower().str.contains(q)
                display_df = df_complaints[mask].sort_values(by="event_datetime", ascending=False)
                st.markdown(f"**Намерени резултати:** {len(display_df)}")
            else:
                st.markdown("#### 🕒 Последни 20 въведени сигнала")
                display_df = df_complaints.sort_values(by="id", ascending=False).head(20)
            
            with st.container(height=400, border=True):
                h_col1, h_col2, h_col3, h_col4, h_col5 = st.columns([1.5, 2, 1, 2, 1])
                h_col1.markdown("**Дата и Час**")
                h_col2.markdown("**Клиент**")
                h_col3.markdown("**Фирма**")
                h_col4.markdown("**Статус**")
                h_col5.markdown("**Действие**")
                st.divider()
                
                if display_df.empty:
                    st.write("Няма намерени записи, отговарящи на критериите.")
                else:
                    for _, row in display_df.iterrows():
                        r_col1, r_col2, r_col3, r_col4, r_col5 = st.columns([1.5, 2, 1, 2, 1])
                        status = row.get('current_status', 'Неопределен')
                        dt_str = pd.to_datetime(row.get('event_datetime')).strftime('%d.%m.%Y %H:%M') if pd.notna(row.get('event_datetime')) else ""
                        r_col1.write(dt_str)
                        
                        has_dup = not get_related_signals(row, df_complaints).empty
                        dup_badge = " <span style='color:#ff4b4b;' title='Има свързани сигнали (30 дни)'>🚨</span>" if has_dup else ""
                        client = row.get('client_name', 'Неизвестен')
                        strike = "s" if status == "Сгрешен/Анулиран" else "span"
                        r_col2.markdown(f"<{strike}>{client}</{strike}>{dup_badge}", unsafe_allow_html=True)
                        r_col3.write(row.get('Фирма', ''))
                        color = "gray" if status == "Сгрешен/Анулиран" else "green" if status == "Приключено" else "orange"
                        r_col4.markdown(f"<span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
                        
                        with r_col5:
                            if st.button("Отвори", key=f"btn_rec_{row['id']}"):
                                show_ticket_details(row.to_dict(), df_complaints)
                        st.markdown("<hr style='margin: 0.2em 0; opacity: 0.2'>", unsafe_allow_html=True)
        else:
            st.info("Все още няма регистрирани сигнали в базата данни.")
            
    with tab_new:
        st.write("Форма за въвеждане на първичен картон от служител/кол център.")
        st.markdown("---")

        if "form_key" not in st.session_state: st.session_state.form_key = 0

        with st.form(f"new_complaint_form_{st.session_state.form_key}"):
            st.subheader("Основни данни")
            col1, col2, col3, col4 = st.columns(4)
            with col1: channel = st.selectbox("Канал на постъпване *", ["Телефон", "Email", "Чат", "Друго"])
            with col2: company_selected = st.selectbox("Фирма *", COMPANY_LIST)
            with col3: event_date = st.date_input("Дата на сигнала *")
            with col4: event_time_str = st.text_input("Час (напр. 1430) *", placeholder="Въведете цифри...")

            st.subheader("Данни за клиента")
            col5, col6, col7, col8 = st.columns([2, 1, 1, 1])
            with col5:
                client_name = st.text_input("Име/Наименование *")
                client_type = st.selectbox("Вид клиент", ["Юридическо лице", "Физическо лице", "Неизвестно"])
            with col6:
                client_phone = st.text_input("Телефон")
                client_eik = st.text_input("ЕИК (за ЮЛ)")
            with col7:
                client_email = st.text_input("Email")
                contract_number = st.text_input("Договор/Поръчка №", max_chars=20)
            with col8:
                client_action_needed = st.checkbox("Очаква ли се действие с клиента?", value=False)
                
            st.subheader("Същност на проблема")
            col9, col10 = st.columns(2)
            with col9:
                case_type = st.selectbox("Касае *", ["Наем", "Продажба", "Ремонт", "Друго"])
                call_number = st.text_input("Номер на разговора (аудио запис)")
            with col10:
                machines = st.text_input("Машина/и", max_chars=100)
                
            description = st.text_area("Изложение на проблема *", height=120)
            st.write("*Полетата със звезда са задължителни.*")
            submit_button = st.form_submit_button("Запиши първичен картон", type="primary")

            if submit_button:
                formatted_time = parse_smart_time(event_time_str)
                if not company_selected or not client_name or not description or not event_time_str:
                    st.error("⚠️ Моля, попълнете задължителните полета!")
                elif not formatted_time:
                    st.error("⚠️ Невалиден час!")
                else:
                    try:
                        company_id = COMPANY_MAP.get(company_selected)
                        datetime_str = f"{event_date.strftime('%Y-%m-%d')} {formatted_time}"
                        new_record = {
                            "channel": channel, "event_datetime": datetime_str, "company_id": company_id,
                            "client_name": client_name, "client_phone": client_phone, "client_email": client_email,
                            "client_type": client_type, "client_eik": client_eik, "contract_number": contract_number,
                            "case_type": case_type, "call_number": call_number, "machines": machines,
                            "client_action_needed": client_action_needed, "description": description,
                            "current_status": "Чака заключение и препоръка"
                        }
                        supabase.table("complaints").insert(new_record).execute()
                        st.success(f"✅ Картонът е създаден успешно! Можете да го отворите от таблицата 'Последни 20'.")
                        st.session_state.form_key += 1
                        st.rerun()
                    except Exception as e:
                        st.error(f"Грешка при запис: {e}")

# ==========================================================
# --- СТРАНИЦА 3: АНАЛИЗИ И СПРАВКИ (РО) ---
# ==========================================================
elif page == "📈 Анализи и Справки (РО)":
    st.title("📈 Анализи и Справки (РО)")
    st.markdown("---")
    
    try:
        res_comp = supabase.table("complaints").select("*, companies(code)").limit(100000).execute()
        df_comp = pd.DataFrame(res_comp.data)
        
        res_hist = supabase.table("complaint_history").select("*").limit(100000).execute()
        df_hist = pd.DataFrame(res_hist.data)
        
        if not df_comp.empty:
            df_comp['Фирма'] = df_comp['companies'].apply(lambda x: x.get('code', 'UNKNOWN') if isinstance(x, dict) else 'UNKNOWN')
            df_comp['event_datetime'] = pd.to_datetime(df_comp['event_datetime'], errors='coerce')
            if df_comp['event_datetime'].dt.tz is not None:
                df_comp['event_datetime'] = df_comp['event_datetime'].dt.tz_localize(None)
            
        if not df_hist.empty:
            df_hist['created_at'] = pd.to_datetime(df_hist['created_at'], errors='coerce')
            if df_hist['created_at'].dt.tz is not None:
                df_hist['created_at'] = df_hist['created_at'].dt.tz_localize(None)
        else:
            df_hist = pd.DataFrame(columns=['id', 'complaint_id', 'action_type', 'action_details', 'assigned_to', 'deadline_date', 'created_by', 'created_at'])
            
    except Exception as e:
        st.error(f"Грешка при зареждане на данните: {e}")
        df_comp = pd.DataFrame()
        df_hist = pd.DataFrame()

    if df_comp.empty:
        st.info("⚠️ Няма достатъчно данни в системата за генериране на справки.")
    else:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            company_options = ["Всички фирми (Холдинг)"] + sorted([c for c in df_comp['Фирма'].unique() if c])
            selected_company = st.selectbox("Избор на обхват:", company_options)
            
        with col_f2:
            period_option = st.radio("Избор на период за анализ:", ["Текущ месец", "Текущо тримесечие", "Текущо полугодие", "Текуща година"], horizontal=True)

        st.markdown("---")

        today = pd.to_datetime(datetime.date.today())
        
        if period_option == "Текущ месец":
            start_current = today.replace(day=1)
            end_current = (start_current + relativedelta(months=1)) - timedelta(days=1)
            start_prev = start_current - relativedelta(months=1)
            end_prev = start_current - timedelta(days=1)
            period_label = "предходния месец"
            
        elif period_option == "Текущо тримесечие":
            current_quarter = (today.month - 1) // 3 + 1
            start_current = datetime.datetime(today.year, 3 * current_quarter - 2, 1)
            end_current = (start_current + relativedelta(months=3)) - timedelta(days=1)
            start_prev = start_current - relativedelta(months=3)
            end_prev = start_current - timedelta(days=1)
            period_label = "предходното тримесечие"
            
        elif period_option == "Текущо полугодие":
            current_half = 1 if today.month <= 6 else 2
            start_current = datetime.datetime(today.year, 1 if current_half == 1 else 7, 1)
            end_current = datetime.datetime(today.year, 6, 30) if current_half == 1 else datetime.datetime(today.year, 12, 31)
            start_prev = start_current - relativedelta(months=6)
            end_prev = start_current - timedelta(days=1)
            period_label = "предходното полугодие"
            
        else:
            start_current = today.replace(month=1, day=1)
            end_current = today.replace(month=12, day=31)
            start_prev = start_current - relativedelta(years=1)
            end_prev = start_current - timedelta(days=1)
            period_label = "предходната година"

        st.write(f"📅 **Анализиран период:** {start_current.strftime('%d.%m.%Y')} - {end_current.strftime('%d.%m.%Y')} (Спрямо: {period_label})")

        if selected_company != "Всички фирми (Холдинг)": df_filtered = df_comp[df_comp['Фирма'] == selected_company].copy()
        else: df_filtered = df_comp.copy()
            
        if df_filtered.empty:
             st.warning(f"Няма регистрирани сигнали за {selected_company}.")
        else:
            df_active = df_filtered[df_filtered['current_status'] != 'Сгрешен/Анулиран'].copy()
            mask_current_in = (df_active['event_datetime'] >= start_current) & (df_active['event_datetime'] <= end_current)
            mask_prev_in = (df_active['event_datetime'] >= start_prev) & (df_active['event_datetime'] <= end_prev)
            
            df_current_in = df_active[mask_current_in]
            df_prev_in = df_active[mask_prev_in]
            
            count_in_current = len(df_current_in)
            count_in_prev = len(df_prev_in)
            delta_in = count_in_current - count_in_prev

            closed_history = df_hist[df_hist['action_type'] == "Сигналът е приключен"].copy()
            closed_merged = pd.merge(df_active[['id', 'current_status']], closed_history[['complaint_id', 'created_at']], left_on='id', right_on='complaint_id', how='inner')
            
            mask_current_closed = (closed_merged['created_at'] >= start_current) & (closed_merged['created_at'] <= end_current)
            mask_prev_closed = (closed_merged['created_at'] >= start_prev) & (closed_merged['created_at'] <= end_prev)
            
            count_closed_current = len(closed_merged[mask_current_closed])
            count_closed_prev = len(closed_merged[mask_prev_closed])
            delta_closed = count_closed_current - count_closed_prev
            
            pct_holding_str = ""
            if selected_company != "Всички фирми (Холдинг)":
                holding_active = df_comp[df_comp['current_status'] != 'Сгрешен/Анулиран']
                holding_closed_merged = pd.merge(holding_active[['id']], closed_history[['complaint_id', 'created_at']], left_on='id', right_on='complaint_id', how='inner')
                total_holding_closed = len(holding_closed_merged[(holding_closed_merged['created_at'] >= start_current) & (holding_closed_merged['created_at'] <= end_current)])
                
                if total_holding_closed > 0:
                    pct = (count_closed_current / total_holding_closed) * 100
                    pct_holding_str = f"({pct:.1f}% от холдинга)"

            dispute_history = df_hist[df_hist['action_type'] == "Диспут с клиент: Активиран"].copy()
            dispute_merged = pd.merge(df_active[['id']], dispute_history[['complaint_id', 'created_at']], left_on='id', right_on='complaint_id', how='inner')
            
            current_disputes_ids = dispute_merged[(dispute_merged['created_at'] >= start_current) & (dispute_merged['created_at'] <= end_current)]['complaint_id'].unique()
            count_disputes_current = len(current_disputes_ids)
            
            prev_disputes_ids = dispute_merged[(dispute_merged['created_at'] >= start_prev) & (dispute_merged['created_at'] <= end_prev)]['complaint_id'].unique()
            delta_disputes = count_disputes_current - len(prev_disputes_ids)
            
            pct_disputes = (count_disputes_current / count_in_current * 100) if count_in_current > 0 else 0

            overdue_signals_count = 0
            for _, row in df_active.iterrows():
                dl_val = row.get('current_deadline')
                if pd.notna(dl_val) and row.get('current_status') not in TERMINAL_STATUSES:
                    dt_obj = pd.to_datetime(dl_val, errors='coerce')
                    if pd.notna(dt_obj) and dt_obj.date() < today.date():
                        overdue_signals_count += 1
            
            pct_overdue = (overdue_signals_count / count_in_current * 100) if count_in_current > 0 else 0

            st.markdown('<div class="analytic-card">', unsafe_allow_html=True)
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric("Постъпили (Входирани)", count_in_current, delta=delta_in, help=f"Брой създадени картони в периода {start_current.strftime('%d.%m')} - {end_current.strftime('%d.%m')}")
            m_col2.metric("Приключени", f"{count_closed_current} {pct_holding_str}", delta=delta_closed, help="Брой сигнали, маркирани като 'Приключено' през избрания период.")
            m_col3.metric("Влезли в диспут", f"{count_disputes_current} ({pct_disputes:.1f}%)", delta=delta_disputes, help="% от общо постъпилите за периода.")
            m_col4.metric("С просрочия (Към момента)", f"{overdue_signals_count} ({pct_overdue:.1f}%)", help="Брой активни сигнали с изтекъл срок. % спрямо постъпилите.")
            st.markdown('</div>', unsafe_allow_html=True)

            g_col1, g_col2 = st.columns(2)
            with g_col1:
                st.subheader("Постъпили по Канал")
                if count_in_current > 0:
                    channel_counts = df_current_in['channel'].value_counts().reset_index()
                    channel_counts.columns = ['Канал', 'Брой']
                    fig_channels = px.pie(channel_counts, values='Брой', names='Канал', hole=0.4, color_discrete_sequence=px.colors.sequential.Plasma)
                    fig_channels.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color='white')
                    st.plotly_chart(fig_channels, use_container_width=True)
                else: st.info("Няма постъпили сигнали за този период.")

            with g_col2:
                st.subheader("Първо Заключение (Приключени)")
                if count_closed_current > 0:
                    closed_ids = closed_merged[mask_current_closed]['id'].tolist()
                    first_conclusions = []
                    for cid in closed_ids:
                        steps = df_hist[(df_hist['complaint_id'] == cid) & (df_hist['action_type'] == 'Назначена стъпка')].sort_values(by='created_at')
                        if not steps.empty:
                            first_step_detail = steps.iloc[0]['action_details']
                            match = re.search(r"Заключение:\s*(.*?)\s*\|", first_step_detail)
                            if match: first_conclusions.append(match.group(1).strip())
                            else: first_conclusions.append("Неизвестно")
                        else: first_conclusions.append("Без заключение")
                            
                    if first_conclusions:
                        conc_df = pd.DataFrame(first_conclusions, columns=['Заключение']).value_counts().reset_index()
                        conc_df.columns = ['Заключение', 'Брой']
                        fig_conc = px.bar(conc_df, x='Заключение', y='Брой', color='Заключение', color_discrete_sequence=px.colors.qualitative.Set3)
                        fig_conc.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color='white', showlegend=False)
                        st.plotly_chart(fig_conc, use_container_width=True)
                    else: st.info("Не са намерени заключения за приключените сигнали.")
                else: st.info("Няма приключени сигнали за този период.")

        st.markdown("---")
        with st.expander("📥 Експорт на данните (Excel)"):
            if not df_comp.empty:
                min_date_db = df_comp['event_datetime'].min()
                max_date_db = df_comp['event_datetime'].max()
                min_date = min_date_db.date() if pd.notna(min_date_db) else today.date()
                max_date = max_date_db.date() if pd.notna(max_date_db) else today.date()
                
                col_ex1, col_ex2 = st.columns([1, 2])
                with col_ex1:
                    export_dates = st.date_input("Период за експорт (Начало - Край):", value=(min_date, max_date), min_value=min_date, max_value=max_date)
                    
                if len(export_dates) == 2:
                    start_export, end_export = export_dates
                    export_df = df_comp[(df_comp['event_datetime'].dt.date >= start_export) & (df_comp['event_datetime'].dt.date <= end_export)].copy()
                    
                    if 'companies' in export_df.columns: export_df = export_df.drop(columns=['companies'])
                    for col in export_df.select_dtypes(include=['datetimetz']).columns:
                        export_df[col] = export_df[col].dt.tz_localize(None)
                        
                    with col_ex2:
                        st.write(f"Готови за експорт: **{len(export_df)} записа**")
                        if len(export_df) > 5000: st.warning("⚠️ Избрали сте над 5000 записа.")
                        
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                            export_df.to_excel(writer, index=False, sheet_name='РО_Експорт')
                        
                        st.download_button(label="💾 Изтегли като .xlsx", data=buffer.getvalue(), file_name=f"SequaK_RO_{start_export}_to_{end_export}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
                else:
                    with col_ex2: st.info("Моля, изберете начална и крайна дата в календара.")
            else: st.info("Няма данни за експорт.")
