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
        st.metric(label="Общо пропуски (EUR)", value=f"€ {total_eur:,.2f}")

    with col2:
        st.subheader("Отворени сигнали (РО)")
        open_cases = len(df_ro) if not df_ro.empty else 0
        st.metric(label="Чакащи реакция", value=f"{open_cases} бр.")

    with col3:
        st.subheader("Топ 5 Машини (РПП)")
        if not df_pp.empty and 'item_tag' in df_pp.columns:
            st.dataframe(df_pp['item_tag'].value_counts().head(5), use_container_width=True)
        else:
            st.write("Няма данни.")

except Exception as e:
    st.error(f"Възникна грешка при връзката с базата: {e}")

st.markdown("---")

# --- НОВА СЕКЦИЯ: ИМПОРТ НА ДАННИ ---
st.header("📥 Внос на данни")
st.write("Пуснете своя работен Excel файл тук. Системата автоматично ще разпознае данните.")

uploaded_file = st.file_uploader("Изберете Excel файл (.xlsx)", type=["xlsx", "xls"])

if uploaded_file is not None:
    try:
        xls_file = pd.ExcelFile(uploaded_file)
        selected_sheet = st.selectbox("Изберете страница (Sheet):", xls_file.sheet_names)
        df_uploaded = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
        
        st.success(f"✅ Заредена страница '{selected_sheet}' с {len(df_uploaded)} реда. Готови за запис!")
        st.dataframe(df_uploaded.head(5), use_container_width=True)
        
        # --- БУТОН ЗА ЗАПИС В БАЗАТА ---
        if st.button("🚀 ИЗПРАТИ ДАННИТЕ КЪМ БАЗАТА", type="primary"):
            with st.spinner("Записване в Supabase... моля изчакайте!"):
                
                if all(col in df_uploaded.columns for col in ['Дата', 'Тагове', 'Обща стойност', 'Резултат']):
                    
                    df_to_insert = df_uploaded[['Дата', 'Тагове', 'Обща стойност', 'Резултат']].copy()
                    df_to_insert = df_to_insert.rename(columns={
                        'Дата': 'event_date',
                        'Тагове': 'item_tag',
                        'Обща стойност': 'total_value_eur',
                        'Резултат': 'resolution_status'
                    })
                    
                    # ПРЕВОДАЧ ЗА ОХРАНАТА (ХИТРОСТ 2.0)
                    def get_transaction_type(tag):
                        if '|' not in str(tag):
                            return 'Неопределен'
                        raw_type = str(tag).split('|')[0].strip()
                        # Ако в Ексела пише "Поръчка", казваме на базата, че е "Продажба"
                        if raw_type == 'Поръчка':
                            return 'Продажба'
                        return raw_type

                    df_to_insert['transaction_type'] = df_to_insert['item_tag'].apply(get_transaction_type)
                    
                    # Оправяме формата на датата
                    df_to_insert['event_date'] = pd.to_datetime(df_to_insert['event_date'], dayfirst=True).dt.strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Почистваме и застраховаме празните полета
                    df_to_insert['total_value_eur'] = pd.to_numeric(df_to_insert['total_value_eur'], errors='coerce').fillna(0)
                    df_to_insert['resolution_status'] = df_to_insert['resolution_status'].fillna('Неопределен')
                    df_to_insert = df_to_insert.dropna(subset=['item_tag', 'event_date'])
                    
                    # Записваме
                    records = df_to_insert.to_dict(orient='records')
                    supabase.table("missed_profits").insert(records).execute()
                    
                    st.success("🎉 Данните са импортирани успешно! Презареждам таблото...")
                    st.rerun() 
                else:
                    st.warning("⚠️ Не намирам всички нужни колони ('Дата', 'Тагове', 'Обща стойност', 'Резултат'). Моля, проверете файла.")

    except Exception as e:
        st.error(f"Възникна грешка: {e}")
