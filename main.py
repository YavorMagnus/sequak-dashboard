import streamlit as st
from supabase import create_client, Client
import pandas as pd

# --- НАСТРОЙКИ НА СТРАНИЦАТА (Тъмна тема и жълти акценти) ---
st.set_page_config(page_title="SequaK Dashboard", page_icon="🏗️", layout="wide")

st.markdown("""
    <style>
    /* Тъмен фон и бели текстове като основа */
    .stApp { background-color: #111111; color: #FFFFFF; }
    
    /* Жълт текст за заглавията */
    h1, h2, h3 { color: #FFD700; } 
    
    /* Стилизиране на числата (Метриките) */
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
    # 1. Данни за Пропуснати ползи
    response_pp = supabase.table("missed_profits").select("*").execute()
    df_pp = pd.DataFrame(response_pp.data)

    # 2. Данни за Оплаквания (само отворените)
    response_ro = supabase.table("complaints").select("*, companies(code)").neq("status", "Приключен").execute()
    df_ro = pd.DataFrame(response_ro.data)

    # --- ВИЗУАЛИЗАЦИЯ НА "СВЕТАТА ТРОИЦА" ---
    col1, col2, col3 = st.columns(3)

    # 1. ТОТАЛ ПРОПУСНАТИ ПОЛЗИ (EUR)
    with col1:
        st.subheader("Пропуснати ползи")
        if not df_pp.empty:
            total_eur = df_pp['total_value_eur'].sum()
            st.metric(label="Общо пропуски (Тестови данни)", value=f"€ {total_eur:,.2f}")
        else:
            st.metric(label="Общо пропуски", value="€ 0.00")

    # 2. БРОЙ ПРОСРОЧЕНИ ОПЛАКВАНИЯ
    with col2:
        st.subheader("Отворени сигнали (РО)")
        if not df_ro.empty:
            open_cases = len(df_ro)
            st.metric(label="Чакащи реакция", value=f"{open_cases} бр.")
        else:
            st.metric(label="Чакащи реакция", value="0 бр.")

    # 3. ТОП 5 МАШИНИ ПО ТЪРСЕНЕ (Leaderboard)
    with col3:
        st.subheader("Топ 5 Машини (РПП)")
        if not df_pp.empty:
            top_items = df_pp['item_tag'].value_counts().head(5)
            st.dataframe(top_items, use_container_width=True)
        else:
            st.write("Няма данни за машини.")

except Exception as e:
    st.error(f"Възникна грешка при връзката с базата: {e}")

st.markdown("---")
st.info("Това е базовата визия. След като я подкараме, ще добавим формата за логин на управителите и бутона за импорт на Excel.")
