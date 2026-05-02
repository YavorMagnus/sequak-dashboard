import streamlit as st
from supabase import create_client, Client
import pandas as pd

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
    </style>
    """, unsafe_allow_html=True)

# --- СВЪРЗВАНЕ С БАЗАТА ДАННИ ---
SUPABASE_URL = "https://cymfodenkklcjhjgfeau.supabase.co"
SUPABASE_KEY = "sb_publishable_blR-3tOs1E8M-gXtv8DVBA_LiEGG8Y6"

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_connection()

# --- ЗАГЛАВИЕ ---
st.title("🏗️ SequaK - Оперативен Дашборд")
st.markdown("---")

# --- ИЗВЛИЧАНЕ НА ДАННИТЕ ---
try:
    response_pp = supabase.table("missed_profits").select("*").execute()
    df_pp = pd.DataFrame(response_pp.data)

    response_ro = supabase.table("complaints").select("*, companies(code)").neq("status", "Приключен").execute()
    df_ro = pd.DataFrame(response_ro.data)

    # --- ВИЗУАЛИЗАЦИЯ НА ДАШБОРДА ---
    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Пропуснати ползи")
        total_eur = df_pp['total_value_eur'].sum() if not df_pp.empty else 0
        st.metric(label="Общо пропуски (Тестови данни)", value=f"€ {total_eur:,.2f}")

    with col2:
        st.subheader("Отворени сигнали (РО)")
        open_cases = len(df_ro) if not df_ro.empty else 0
        st.metric(label="Чакащи реакция", value=f"{open_cases} бр.")

    with col3:
        st.subheader("Топ 5 Машини (РПП)")
        if not df_pp.empty:
            st.dataframe(df_pp['item_tag'].value_counts().head(5), use_container_width=True)
        else:
            st.write("Няма данни.")

except Exception as e:
    st.error(f"Възникна грешка при връзката с базата: {e}")

st.markdown("---")

# --- НОВА СЕКЦИЯ: ИМПОРТ НА ДАННИ (EXCEL) ---
st.header("📥 Внос на данни (РПП и РО)")
st.write("Пуснете своя работен Excel файл тук, за да го заредим в системата.")

uploaded_file = st.file_uploader("Изберете Excel файл (.xlsx)", type=["xlsx", "xls"])

if uploaded_file is not None:
    try:
        # Четем всички страници (sheets) от файла
        xls_file = pd.ExcelFile(uploaded_file)
        
        # Падащо меню за избор на страница
        selected_sheet = st.selectbox("Изберете страница (Sheet) с данните:", xls_file.sheet_names)
        
        # Зареждаме само избраната страница
        df_uploaded = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
        
        st.success(f"✅ Успешно заредена страница '{selected_sheet}' с {len(df_uploaded)} реда!")
        
        # Показваме първите 10 реда за превю
        st.write("👀 Преглед на първите 10 реда от файла:")
        st.dataframe(df_uploaded.head(10), use_container_width=True)
        
        st.info("💡 Следваща стъпка: Ще добавим бутона 'Изпрати към базата', който автоматично ще сортира тези данни по правилните таблици.")
    except Exception as e:
        st.error(f"Възникна грешка при четенето на файла: {e}")
