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
    t_str = str(t_str).strip()
    
    # 1. Ако е пейстнато от ексел с двоеточия (14:30 или 14:30:00)
    if ':' in t_str:
        parts = t_str.split(':')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            hh, mm = int(parts[0]), int(parts[1])
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                return f"{hh:02d}:{mm:02d}:00"
        elif len(parts) == 3 and all(p.isdigit() for p in parts):
            hh, mm, ss = int(parts[0]), int(parts[1]), int(parts[2])
            if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
                return f"{hh:02d}:{mm:02d}:{ss:02d}"
                
    # 2. Ако са въведени само цифри бързо от клавиатурата (1430, 930, 143000)
    clean_str = re.sub(r"\D", "", t_str)
    if len(clean_str) in [3, 4]:
        clean_str = clean_str.zfill(4) # Прави 930 на 0930
        hh, mm = int(clean_str[:2]), int(clean_str[2:])
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return f"{hh:02d}:{mm:02d}:00"
    elif len(clean_str) in [5, 6]:
        clean_str = clean_str.zfill(6)
        hh, mm, ss = int(clean_str[:2]), int(clean_str[2:4]), int(clean_str[4:])
        if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
            return f"{hh:02d}:{mm:02d}:{ss:02d}"
            
    return None # Ако нищо от горните не сработи, значи часът е невалиден

# ==========================================================
# --- СТРАНИЧНО МЕНЮ (SIDEBAR) ---
# ==========================================================
st.sidebar.title("🏗️ SequaK Меню")
page = st.sidebar.radio("Изберете модул:", ["📊 Оперативен Дашборд", "📝 Регистър Оплаквания (РО)"])
st.sidebar.markdown("---")
st.sidebar.caption("Входът е защитен. Версия 1.1")

# ==========================================================
# --- СТРАНИЦА 1: ОПЕРАТИВЕН ДАШБОРД ---
# ==========================================================
if page == "📊 Оперативен Дашборд":
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
    st.write("Пуснете своя работен Excel файл тук. Системата автоматично ще игнорира вече качените дубликати.")

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
# --- СТРАНИЦА 2: РЕГИСТЪР ОПЛАКВАНИЯ (РО) ---
# ==========================================================
elif page == "📝 Регистър Оплаквания (РО)":
    st.title("📝 Управление на Сигнали (РО)")
    st.write("Форма за въвеждане на нов сигнал от служител (Фаза 1)")
    st.markdown("---")

    with st.form("new_complaint_form", clear_on_submit=True):
        st.subheader("Основни данни")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            channel = st.selectbox("Канал на постъпване *", ["Телефон", "Email", "Чат", "Друго"])
        with col2:
            company_selected = st.selectbox("Фирма *", COMPANY_LIST)
        with col3:
            event_date = st.date_input("Дата на сигнала *")
        with col4:
            # Умното текстово поле за час
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
            pass
            
        st.subheader("Същност на проблема")
        col9, col10 = st.columns(2)
        with col9:
            case_type = st.selectbox("Касае *", ["Наем", "Продажба", "Ремонт", "Друго"])
            call_number = st.text_input("Номер на разговора (за аудио запис)")
        with col10:
            recommended_action = st.selectbox("Препоръчано действие", ["Корективно", "Организационно", "Санкционно", "Проверка", "Неприложимо"])
            
        description = st.text_area("Изложение на проблема *", height=120, placeholder="Опишете сбито какъв е проблемът на клиента...")
        
        st.write("*Полетата със звезда са задължителни.*")
        submit_button = st.form_submit_button("Запиши сигнала", type="primary")

        if submit_button:
            # Прекарваме въведеното през умния парсър
            formatted_time = parse_smart_time(event_time_str)
            
            if not company_selected or not client_name or not description or not event_time_str:
                st.error("⚠️ Моля, попълнете Фирма, Дата, Час, Име на клиент и Изложение на проблема!")
            elif not formatted_time:
                st.error("⚠️ Невалиден час! Моля, въведете коректен час (например: 1430, 9:15, 14:30:00).")
            else:
                try:
                    company_id = COMPANY_MAP.get(company_selected)
                    # Използваме вече перфектно форматирания час
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
                        "recommended_action": recommended_action,
                        "description": description,
                        "status": "Постъпил"
                    }
                    
                    supabase.table("complaints").insert(new_record).execute()
                    
                    st.success(f"✅ Сигналът е записан успешно! (Разпознат час: {formatted_time})")
                except Exception as e:
                    st.error(f"Възникна грешка при запис: {e}")
