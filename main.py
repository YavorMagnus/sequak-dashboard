import streamlit as st
from supabase import create_client, Client
import pandas as pd
import numpy as np

# --- НАСТРОЙКИ НА СТРАНИЦАТА ---
st.set_page_config(page_title="SequaK Dashboard", page_icon="🏗️", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #111111; color: #FFFFFF; }
    h1, h2, h3 { color: #FFD700; } 
    .stMetric label { color: #FFD700 !important; font-size: 1.2rem !important; }
    div[data-testid="metric-container"] {
        background-color: #222222; 
        border: 1px solid #FFD700; 
        padding: 15px; 
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(255, 215, 0, 0.1);
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

# Зареждаме ID-тата на фирмите
try:
    comp_res = supabase.table("companies").select("id, code").execute()
    COMPANY_MAP = {row['code'].upper(): row['id'] for row in comp_res.data}
except Exception:
    COMPANY_MAP = {}

# УМЕН ПРЕВОДАЧ НА ФИРМИ (вече с RCD!)
def standardize_company_code(excel_name):
    name = str(excel_name).lower()
    if 'ren' in name: return 'REN'
    # Ако намери RCD или CIM, го насочваме правилно според това какво очаква базата
    if 'rcd' in name or ('cim' in name and 'cmx' not in name): 
        return 'CIM' if 'CIM' in COMPANY_MAP else 'RCD'
    if 'mas' in name: return 'MAS'
    if 'cmx' in name: return 'CMX'
    return str(excel_name).upper().strip()

# --- ИЗВЛИЧАНЕ НА ДАННИТЕ ---
try:
    response_pp = supabase.table("missed_profits").select("*, companies(code)").execute()
    df_pp = pd.DataFrame(response_pp.data)
    
    if not df_pp.empty:
        df_pp['company_code'] = df_pp['companies'].apply(lambda x: x.get('code', 'UNKNOWN').upper() if isinstance(x, dict) else 'UNKNOWN')
        df_pp['clean_machine'] = df_pp['item_tag'].apply(lambda x: str(x).split('|')[-1].strip() if '|' in str(x) else str(x))
    else:
        df_pp['company_code'] = 'UNKNOWN'
        df_pp['clean_machine'] = 'UNKNOWN'

    response_ro = supabase.table("complaints").select("*, companies(code)").neq("status", "Приключен").execute()
    df_ro = pd.DataFrame(response_ro.data)

    # --- ЗАГЛАВИЕ И ДАШБОРД ---
    st.title("🏗️ SequaK - Оперативен Дашборд")
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
        # Осигуряваме се, че табът CIM ще хване и RCD, ако базата го е запазила така
        with tab_cim: show_top_10(df_pp[df_pp['company_code'].isin(['CIM', 'RCD'])])
        with tab_mas: show_top_10(df_pp[df_pp['company_code'] == 'MAS'])
        with tab_cmx: show_top_10(df_pp[df_pp['company_code'] == 'CMX'])

    st.markdown("---")
    st.subheader("Отворени сигнали (РО)")
    open_cases = len(df_ro) if not df_ro.empty else 0
    st.metric(label="Чакащи реакция", value=f"{open_cases} бр.")

except Exception as e:
    st.error(f"Възникна грешка: {e}")

st.markdown("---")

# --- СЕКЦИЯ: ИМПОРТ ---
st.header("📥 Внос на данни")
st.write("Пуснете своя работен Excel файл тук.")

uploaded_file = st.file_uploader("Изберете Excel файл (.xlsx)", type=["xlsx", "xls"])

if uploaded_file is not None:
    try:
        xls_file = pd.ExcelFile(uploaded_file)
        selected_sheet = st.selectbox("Изберете страница:", xls_file.sheet_names)
        df_uploaded = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
        
        st.success(f"✅ Заредена страница '{selected_sheet}'.")
        
        if st.button("🚀 ИЗПРАТИ ДАННИТЕ КЪМ БАЗАТА", type="primary"):
            with st.spinner("Анализиране и запис... моля изчакайте!"):
                
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
                    
                    # Магически превод на фирмите - вече включва RCD!
                    df_to_insert['mapped_code'] = df_to_insert['Фирма'].apply(standardize_company_code)
                    df_to_insert['company_id'] = df_to_insert['mapped_code'].map(COMPANY_MAP)
                    
                    # 🔴 ЗАЩИТА
                    df_to_insert = df_to_insert.dropna(subset=['item_tag', 'event_date', 'company_id'])
                    df_to_insert = df_to_insert.replace({float('nan'): None, np.nan: None})
                    df_to_insert = df_to_insert.drop(columns=['Фирма', 'mapped_code'])
                    
                    records = df_to_insert.to_dict(orient='records')
                    supabase.table("missed_profits").insert(records).execute()
                    
                    st.success("🎉 Данните са импортирани успешно! Презареждам...")
                    st.rerun() 
                else:
                    st.warning("⚠️ Липсват нужни колони.")
    except Exception as e:
        st.error(f"Възникна грешка: {e}")
