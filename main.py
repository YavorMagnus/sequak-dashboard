import streamlit as st
from supabase import create_client, Client
import pandas as pd
import numpy as np
import datetime
import re

# --- НАСТРОЙКИ НА СТРАНИЦАТА ---
st.set_page_config(page_title="SequaK Workspace", page_icon="🏗️", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #111111; color: #FFFFFF; }
    h1, h2, h3 { color: #FFD700; } 
    .stMetric label { color: #FFD700 !important; font-size: 1.2rem !important; }
    div[data-testid="metric-container"] {
        background-color: #222222; border: 1px solid #FFD700; padding: 15px; border-radius: 8px; box-shadow: 0 4px 6px rgba(255, 215, 0, 0.1);
    }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #222222; border-radius: 4px; padding: 10px 20px; color: #FFFFFF; }
    .stTabs [aria-selected="true"] { background-color: #FFD700 !important; color: #111111 !important; font-weight: bold; }
    .status-overdue { color: #ff4b4b; font-weight: bold; }
    .status-ok { color: #00cc66; }
    </style>
    """, unsafe_allow_html=True)

# --- СВЪРЗВАНЕ С БАЗАТА ДАННИ ---
SUPABASE_URL = "https://cymfodenkklcjhjgfeau.supabase.co"
SUPABASE_KEY = "sb_publishable_blR-3tOs1E8M-gXtv8DVBA_LiEGG8Y6"

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_connection()

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

# --- УМЕН ПАРСЪР ЗА ЧАС ---
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

# ==========================================================
# --- НОВИ СПИСЪЦИ (DROPDOWNS) ЗА ФАЗА 2 ---
# ==========================================================
ROLES_LIST = ["Контролинг", "Отговорник качество", "Управител", "Пряк ръководител", "Служител", "RXG-адм", "CEO", "Друг"]
MAIN_STATUSES = ["Чака заключение и препоръка", "Чака проверка", "Чака възлагане", "Чака приключване", "Приключено"]
CONCLUSIONS = ["Техническа грешка", "Липса на знания/умения", "Нарушение", "Не сме сигурни", "Липса на ресурс", "Дезорганизация", "Идея за подобрение", "Друго", "Грешим/няма проблем"]
RECOMMENDATIONS = ["Техническа корекция", "Обучение", "Наказание", "Проверка (поле)", "Планиране на ресурс", "Реорганизация", "Обсъждане с колеги", "Друго", "Нищо"]

# ==========================================================
# --- ПОПЪП ДИАЛОЗИ (НОВИЯТ ИЗГЛЕД НА СИГНАЛИТЕ) ---
# ==========================================================
@st.dialog("Картон на сигнала", width="large")
def show_ticket_details(ticket):
    st.markdown(f"### Сигнал от: **{ticket.get('client_name', 'Неизвестен')}**")
    st.caption(f"Дата на постъпване: {ticket.get('event_datetime', '')} | Канал: {ticket.get('channel', '')} | Касае: {ticket.get('case_type', '')}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Телефон:** {ticket.get('client_phone', '-')}")
        st.write(f"**Имейл:** {ticket.get('client_email', '-')}")
        st.write(f"**ЕИК:** {ticket.get('client_eik', '-')}")
    with col2:
        st.write(f"**Договор №:** {ticket.get('contract_number', '-')}")
        st.write(f"**Машина/и:** {ticket.get('machines', '-')}")
        st.write(f"**Очаква ли се действие с клиент:** {'Да' if ticket.get('client_action_needed') else 'Не'}")
    
    st.info(f"**Описание:** {ticket.get('description', '')}")
    st.markdown("---")
    
    st.subheader("Продължаване на процеса (Контролинг)")
    
    # Тук симулираме динамичната форма за Фаза 2
    current_status = ticket.get('current_status', 'Чака заключение и препоръка')
    st.write(f"Текущ мастър статус: **{current_status}**")
    
    if current_status == "Чака проверка":
        st.warning("В момента се извършва проверка.")
        check_result = st.text_input("До какво доведе проверката? (до 100 символа)", max_chars=100)
        if st.button("Приключи проверката"):
            st.success("Визуална симулация: Проверката е маркирана като приключена.")
    else:
        new_conc = st.selectbox("Заключение контролинг", ["Избери..."] + CONCLUSIONS)
        new_rec = st.selectbox("Препоръка контролинг", ["Избери..."] + RECOMMENDATIONS)
        
        if new_rec == "Проверка (поле)":
            st.text_input("Какво точно ще се проверява? (до 100 символа)", max_chars=100)
            
        assignee = st.selectbox("Възложено на (Роля)", ["Избери..."] + ROLES_LIST)
        deadline = st.date_input("Ръчен срок (Край до)")
        
        if st.button("Запази следваща стъпка", type="primary"):
            st.success("Визуална симулация: Стъпката е запазена в Историята!")

@st.dialog("Списък със сигнали")
def show_company_tickets(company_code, df_complaints):
    st.subheader(f"Всички сигнали за {company_code}")
    
    if df_complaints.empty:
        st.write("Няма данни за тази фирма.")
        return
        
    comp_df = df_complaints[df_complaints['Фирма'] == company_code]
    if comp_df.empty:
        st.write("Няма данни за тази фирма.")
        return

    # Извеждаме сигналите като списък от "карти" (expanders или колони с бутони)
    for _, row in comp_df.iterrows():
        status = row.get('current_status', 'Неопределен')
        client = row.get('client_name', 'Неизвестен')
        # Симулираме просрочие (в реалния вариант ще се смята от current_deadline)
        is_overdue = False 
        
        colA, colB, colC = st.columns([3, 2, 1])
        with colA:
            st.write(f"👤 **{client}**")
            st.caption(f"Дата: {row.get('event_datetime', '')}")
        with colB:
            color = "red" if is_overdue else "orange" if status != "Приключено" else "green"
            st.markdown(f"Статус: <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
        with colC:
            if st.button("Отвори", key=f"btn_open_{row['id']}"):
                show_ticket_details(row.to_dict())
        st.divider()

# ==========================================================
# --- СТРАНИЧНО МЕНЮ (SIDEBAR) ---
# ==========================================================
st.sidebar.title("🏗️ SequaK Меню")
page = st.sidebar.radio("Изберете модул:", ["📊 Оперативен Дашборд", "📝 Регистър Оплаквания (РО)"])
st.sidebar.markdown("---")
st.sidebar.caption("Входът е защитен. Версия 2.0 (Preview)")

# ==========================================================
# --- СТРАНИЦА 1: ОПЕРАТИВЕН ДАШБОРД (БЕЗ ПРОМЕНИ!) ---
# ==========================================================
if page == "📊 Оперативен Дашборд":
    # --- ТУК ОСТАВА СТАРИЯТ КОД ЗА ПП ---
    # (Запазен е 1:1, за да не чупим нищо по ПП)
    try:
        response_pp = supabase.table("missed_profits").select("*, companies(code)").execute()
        df_pp = pd.DataFrame(response_pp.data)
        if not df_pp.empty:
            df_pp['company_code'] = df_pp['companies'].apply(lambda x: x.get('code', 'UNKNOWN').upper() if isinstance(x, dict) else 'UNKNOWN')
            df_pp['clean_machine'] = df_pp['item_tag'].apply(lambda x: str(x).split('|')[-1].strip() if '|' in str(x) else str(x))
        else:
            df_pp['company_code'] = 'UNKNOWN'
            df_pp['clean_machine'] = 'UNKNOWN'

        response_ro = supabase.table("complaints").select("id").neq("status", "Приключен").execute()
        open_cases = len(response_ro.data)

        st.title("📊 Оперативен Дашборд")
        st.markdown("---")
        col1, col2 = st.columns([1, 2.5])
        with col1:
            st.subheader("Пропуснати ползи")
            total_eur = df_pp['total_value_eur'].sum() if not df_pp.empty else 0
            st.metric(label="Общо пропуски (EUR)", value=f"€ {total_eur:,.2f}")
        with col2:
            st.subheader("Топ 10 Машини (по изпусната сума)")
            tab_all, tab_ren, tab_cim, tab_mas, tab_cmx = st.tabs(["Всички", "REN", "CIM", "MAS", "CMX"])
            def show_top_10(df_filtered):
                if df_filtered.empty or 'clean_machine' not in df_filtered.columns:
                    st.write("Няма данни.")
                    return
                top_10 = df_filtered.groupby('clean_machine')['total_value_eur'].sum().nlargest(10).reset_index()
                top_10.columns = ['Машина', 'Изпусната сума (€)']
                styled_df = top_10.style.format({'Изпусната сума (€)': '€ {:,.2f}'}).set_properties(**{'color': '#FFD700'})
                st.dataframe(styled_df, use_container_width=True, hide_index=True)

            with tab_all: show_top_10(df_pp)
            with tab_ren: show_top_10(df_pp[df_pp['company_code'] == 'REN'])
            with tab_cim: show_top_10(df_pp[df_pp['company_code'].isin(['CIM', 'RCD'])])
            with tab_mas: show_top_10(df_pp[df_pp['company_code'] == 'MAS'])
            with tab_cmx: show_top_10(df_pp[df_pp['company_code'] == 'CMX'])

        st.markdown("---")
        st.subheader("Отворени сигнали (РО)")
        st.metric(label="Чакащи реакция", value=f"{open_cases} бр.")
    except Exception as e:
        st.error(f"Възникна грешка: {e}")

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
                    required_cols = ['Дата', 'Тагове', 'Обща стойност', 'Резултат', 'Фирма']
                    if all(col in df_uploaded.columns for col in required_cols):
                        df_to_insert = df_uploaded[required_cols].copy()
                        df_to_insert = df_to_insert.rename(columns={
                            'Дата': 'event_date', 'Тагове': 'item_tag',
                            'Обща стойност': 'total_value_eur', 'Резултат': 'resolution_status'
                        })
                        def get_smart_transaction_type(tag):
                            tag_str = str(tag)
                            if 'Наем' in tag_str: return 'Наем'
                            elif 'Поръчка' in tag_str or 'Продажба' in tag_str: return 'Продажба'
                            return 'Неопределен'
                        df_to_insert['transaction_type'] = df_to_insert['item_tag'].apply(get_smart_transaction_type)
                        df_to_insert['event_date'] = pd.to_datetime(df_to_insert['event_date'], dayfirst=True).dt.strftime('%Y-%m-%d %H:%M:%S')
                        df_to_insert['total_value_eur'] = pd.to_numeric(df_to_insert['total_value_eur'], errors='coerce').fillna(0)
                        df_to_insert['resolution_status'] = df_to_insert['resolution_status'].fillna('Неопределен')
                        df_to_insert['mapped_code'] = df_to_insert['Фирма'].apply(standardize_company_code)
                        df_to_insert['company_id'] = df_to_insert['mapped_code'].map(COMPANY_MAP)
                        df_to_insert = df_to_insert.dropna(subset=['item_tag', 'event_date', 'company_id'])
                        df_to_insert = df_to_insert.replace({float('nan'): None, np.nan: None})
                        
                        existing_fingerprints = set()
                        if not df_pp.empty and 'event_date' in df_pp.columns:
                            existing_dates = pd.to_datetime(df_pp['event_date']).dt.strftime('%Y-%m-%d %H:%M:%S')
                            existing_sigs = df_pp['company_id'].astype(str) + "|" + df_pp['item_tag'].astype(str) + "|" + existing_dates + "|" + df_pp['total_value_eur'].astype(str)
                            existing_fingerprints = set(existing_sigs)

                        new_dates = pd.to_datetime(df_to_insert['event_date']).dt.strftime('%Y-%m-%d %H:%M:%S')
                        df_to_insert['fingerprint'] = df_to_insert['company_id'].astype(str) + "|" + df_to_insert['item_tag'].astype(str) + "|" + new_dates + "|" + df_to_insert['total_value_eur'].astype(str)
                        
                        df_to_insert = df_to_insert.drop_duplicates(subset=['fingerprint'])
                        df_final = df_to_insert[~df_to_insert['fingerprint'].isin(existing_fingerprints)].copy()
                        df_final = df_final.drop(columns=['Фирма', 'mapped_code', 'fingerprint'])
                        
                        if df_final.empty:
                            st.info("⚠️ Всички тези данни вече са качени в базата! Няма нови записи за добавяне.")
                        else:
                            records = df_final.to_dict(orient='records')
                            supabase.table("missed_profits").insert(records).execute()
                            skipped_count = len(df_to_insert) - len(df_final)
                            st.success(f"🎉 Успешно добавени {len(df_final)} НОВИ записа! (Пропуснати {skipped_count} вече съществуващи). Презареждам...")
                            st.rerun() 
                    else:
                        st.warning("⚠️ Липсват нужни колони.")
        except Exception as e:
            st.error(f"Възникна грешка: {e}")

# ==========================================================
# --- СТРАНИЦА 2: РЕГИСТЪР ОПЛАКВАНИЯ (РО) - НОВ ДИЗАЙН ---
# ==========================================================
elif page == "📝 Регистър Оплаквания (РО)":
    st.title("📝 Управление на Сигнали (РО) - Фаза 2")
    
    tab_list, tab_new = st.tabs(["👁️ Птичи поглед (Дашборд)", "➕ Въвеждане на нов сигнал"])
    
    # ==========================================
    # --- ТАБ 1: ПТИЧИ ПОГЛЕД (ДАСШБОРД ФИРМИ) ---
    # ==========================================
    with tab_list:
        st.markdown("### Активно следене на процеси по фирми")
        st.caption("Кликнете върху бутона под дадена фирма, за да видите детайли и просрочия.")
        
        # Зареждане на данни (с предпазител, ако новите полета липсват в базата)
        try:
            res = supabase.table("complaints").select("*, companies(code)").execute()
            df_complaints = pd.DataFrame(res.data)
            if not df_complaints.empty:
                df_complaints['Фирма'] = df_complaints['companies'].apply(lambda x: x.get('code', '') if isinstance(x, dict) else '')
                # Ако новите полета все още не са създадени в DB, симулираме ги за да не крашне:
                if 'current_status' not in df_complaints.columns:
                    df_complaints['current_status'] = "Чака заключение и препоръка"
                if 'client_action_needed' not in df_complaints.columns:
                    df_complaints['client_action_needed'] = False
        except Exception as e:
            st.error(f"Грешка при връзка с DB (нормално преди ъпдейта): {e}")
            df_complaints = pd.DataFrame()

        # Генериране на колони за всяка фирма
        cols = st.columns(len(COMPANY_LIST))
        for i, comp in enumerate(COMPANY_LIST):
            with cols[i]:
                st.markdown(f"<h4 style='text-align: center; color: white;'>{comp}</h4>", unsafe_allow_html=True)
                
                # Изчисляване на симулирани бройки
                if not df_complaints.empty and 'Фирма' in df_complaints.columns:
                    comp_data = df_complaints[df_complaints['Фирма'] == comp]
                    unresolved = len(comp_data[comp_data['current_status'] != 'Приключено'])
                    overdue = 0 # Тук в бъдеще ще броим days > deadline
                else:
                    unresolved, overdue = 0, 0
                
                # Метрики
                st.metric("Неприключени", f"{unresolved} бр.")
                st.metric("Просрочени", f"{overdue} бр.")
                
                if st.button(f"🔍 Отвори {comp}", key=f"open_dash_{comp}", use_container_width=True):
                    show_company_tickets(comp, df_complaints)
    
    # ==========================================
    # --- ТАБ 2: ВЪВЕЖДАНЕ (ПЪРВИЧЕН КАРТОН) ---
    # ==========================================
    with tab_new:
        st.write("Форма за въвеждане на първичен картон от служител/кол център.")
        st.markdown("---")

        if "form_key" not in st.session_state:
            st.session_state.form_key = 0

        with st.form(f"new_complaint_form_{st.session_state.form_key}"):
            st.subheader("Основни данни")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                channel = st.selectbox("Канал на постъпване *", ["Телефон", "Email", "Чат", "Друго"])
            with col2:
                company_selected = st.selectbox("Фирма *", COMPANY_LIST)
            with col3:
                event_date = st.date_input("Дата на сигнала *")
            with col4:
                event_time_str = st.text_input("Час (напр. 1430 или 14:30) *", placeholder="Въведете цифри...")

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
                # НОВО ПОЛЕ ЗА ВТОРОСТЕПЕНЕН СТРИЙМ
                client_action_needed = st.checkbox("Очаква ли се действие с клиента?", value=False, help="Маркирай, ако отговорник качество трябва да се свърже обратно.")
                
            st.subheader("Същност на проблема")
            col9, col10 = st.columns(2)
            with col9:
                case_type = st.selectbox("Касае *", ["Наем", "Продажба", "Ремонт", "Друго"])
                call_number = st.text_input("Номер на разговора (за аудио запис)")
            with col10:
                # НОВО ПОЛЕ МАШИНИ (замества "Препоръчано действие")
                machines = st.text_input("Машина/и", max_chars=100, placeholder="Въведете машина (до 100 символа)")
                
            description = st.text_area("Изложение на проблема *", height=120, placeholder="Опишете сбито какъв е проблемът на клиента...")
            
            st.write("*Полетата със звезда са задължителни.*")
            submit_button = st.form_submit_button("Запиши първичен картон", type="primary")

            if submit_button:
                formatted_time = parse_smart_time(event_time_str)
                
                if not company_selected or not client_name or not description or not event_time_str:
                    st.error("⚠️ Моля, попълнете Фирма, Дата, Час, Име на клиент и Изложение на проблема!")
                elif not formatted_time:
                    st.error("⚠️ Невалиден час! Моля, въведете коректен час (например: 1430, 9:15, 14:30:00).")
                else:
                    try:
                        company_id = COMPANY_MAP.get(company_selected)
                        datetime_str = f"{event_date.strftime('%Y-%m-%d')} {formatted_time}"
                        
                        new_record = {
                            "channel": channel,
                            "event_datetime": datetime_str,
                            "company_id": company_id,
                            "client_name": client_name,
                            "client_phone": client_phone,
                            "client_email": client_email,
                            "client_type": client_type,
                            "client_eik": client_eik,
                            "contract_number": contract_number,
                            "case_type": case_type,
                            "call_number": call_number,
                            "machines": machines, # Ново
                            "client_action_needed": client_action_needed, # Ново
                            "description": description,
                            "current_status": "Чака заключение и препоръка" # Нов статус
                        }
                        
                        # Ако полетата ги няма в DB, това ще даде грешка. Затова го хващаме:
                        supabase.table("complaints").insert(new_record).execute()
                        
                        st.success(f"✅ Първичният картон е създаден успешно!")
                        st.session_state.form_key += 1
                        st.rerun()
                    except Exception as e:
                        st.error(f"Грешка при запис в базата. Вероятно новите полета все още не са добавени в Supabase: {e}")
