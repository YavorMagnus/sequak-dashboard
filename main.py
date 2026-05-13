import streamlit as st

# НАСТРОЙКИТЕ ЗАДЪЛЖИТЕЛНО СА НА ПЪРВИ РЕД!
st.set_page_config(page_title="SequaK Workspace", page_icon="🏗️", layout="wide")

# ИМПОРТИРАНЕ ОТ НОВИТЕ МОДУЛИ
from utils import supabase, check_permission
from mp import render_mp_dashboard
from ro import check_and_show_alerts, render_ro_registry, render_ro_analytics
from admin_panel import render_admin_panel
from recruitment import render_recruitment_module

st.markdown("""
    <style>
    .stApp { background-color: #111111; color: #FFFFFF; }
    h1, h2, h3, h4 { color: #FFD700; } 
    .stMetric label { color: #FFD700 !important; font-size: 1.3rem !important; font-weight: 600 !important; line-height: 1.2 !important; padding-bottom: 5px; }
    div[data-testid="metric-container"] {
        background-color: #222222; border: 1px solid #FFD700; padding: 15px; border-radius: 8px; box-shadow: 0 4px 6px rgba(255, 215, 0, 0.1);
    }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #222222; border-radius: 4px; padding: 10px 20px; color: #FFFFFF; }
    .stTabs [aria-selected="true"] { background-color: #FFD700 !important; color: #111111 !important; font-weight: bold; }
    
    .history-card { background-color: #333333; padding: 12px; border-left: 4px solid #FFD700; margin-bottom: 12px; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
    .client-stream { background-color: #0d2136; padding: 20px; border-radius: 8px; border-left: 5px solid #00aaff; margin-top: 10px; box-shadow: 0 2px 4px rgba(0,170,255,0.1); }
    .client-stream h4 { color: #00aaff; margin-top: 0; }
    .analytic-card { background-color: #1e1e1e; padding: 20px; border-radius: 8px; border-top: 3px solid #FFD700; margin-bottom: 20px; }
    
    [data-testid="stDataFrame"] { background-color: #1e1e1e; border-radius: 8px; }
    th, [data-testid="stDataFrame"] th, .stDataFrame div[data-testid="stColumnHeader"] span { color: #FFFFFF !important; }
    
    div[role="radiogroup"] { flex-wrap: wrap; gap: 10px; margin-bottom: 15px; }
    
    .email-builder-row { background-color: #1e1e1e; padding: 15px; border-radius: 6px; border: 1px solid #444; margin-bottom: 8px; display: flex; align-items: center;}
    .email-preview-box { background-color: #ffffff; color: #000000; padding: 20px; border-radius: 8px; border: 2px dashed #00aaff; margin-top: 20px; user-select: all; }
    
    .kanban-card { background-color: #2a2a2a; border-left: 5px solid #FFD700; padding: 15px; border-radius: 6px; margin-bottom: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.3); }
    .kanban-card.overdue { border-left-color: #ff4b4b; background-color: #3a1c1c; }
    .kanban-card.dispute { border-left-color: #00aaff; }
    .kanban-title { font-size: 1.1em; font-weight: bold; margin-bottom: 5px; color: #ffffff; }
    .kanban-meta { font-size: 0.85em; color: #aaaaaa; margin-bottom: 8px; }
    .kanban-detail { font-size: 0.9em; margin-bottom: 5px; line-height: 1.3; color: #eeeeee; }

    .sort-btn-container button {
        background: none !important;
        border: none !important;
        color: #FFD700 !important;
        font-weight: bold !important;
        padding: 0 !important;
        box-shadow: none !important;
        display: inline-block;
    }
    .sort-btn-container button:hover { text-decoration: underline !important; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================================
# --- СИГУРНОСТ И ЛОГИН (RBAC + ПРАВА) ---
# ==========================================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.username = None
    st.session_state.user_permissions = {}
    st.session_state.alerts_dismissed = False

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
                        st.session_state.user_role = user_data.get('role', 'Четец')
                        st.session_state.username = user_data['username']
                        # Извличаме детайлния JSON с права
                        st.session_state.user_permissions = user_data.get('permissions') or {}
                        st.session_state.alerts_dismissed = False
                        st.rerun()
                    else:
                        st.error("Грешен потребител или парола!")
    st.stop() 

# Извикване на алармите ПРЕДИ страничното меню!
if check_permission("ro_registry", "read"):
    check_and_show_alerts()

# ==========================================================
# --- СТРАНИЧНО МЕНЮ (SIDEBAR) ---
# ==========================================================
st.sidebar.title("🏗️ SequaK Меню")

# ДИНАМИЧНО МЕНЮ НА БАЗА ПРАВА
available_pages = []

if check_permission("mp_dashboard", "read"):
    available_pages.append("📊 ПП - Дашборд")

if check_permission("ro_registry", "read"):
    available_pages.append("📝 Сигнали и оплаквания")
    available_pages.append("📈 Анализи и Справки (РО)")
    
if check_permission("recruitment", "read"):
    available_pages.append("🎯 Рекрутмънт и Подбор")

if st.session_state.user_role == "Супер-админ":
    available_pages.append("⚙️ Управление на достъпи")

if not available_pages:
    st.sidebar.warning("Нямате права за достъп до нито един модул.")
    page = None
else:
    # --- МАГИЯТА ЗА ДИРЕКТНИТЕ ЛИНКОВЕ (PORTIER OVERRIDE) ---
    default_index = 0
    if "app_id" in st.query_params and "🎯 Рекрутмънт и Подбор" in available_pages:
        default_index = available_pages.index("🎯 Рекрутмънт и Подбор")
        
    page = st.sidebar.radio("Изберете модул:", available_pages, index=default_index)

st.sidebar.markdown("---")
st.sidebar.write(f"👤 **Профил:** {st.session_state.username}")
st.sidebar.write(f"🛡️ **Роля:** {st.session_state.user_role}")

if st.sidebar.button("🚪 Изход от системата", use_container_width=True):
    st.session_state.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("Входът е защитен. Версия 8.0 (Хибридни права)")

# ==========================================================
# --- РУТИРАНЕ (ROUTING) ---
# ==========================================================
if page == "📊 ПП - Дашборд":
    render_mp_dashboard()

elif page == "📝 Сигнали и оплаквания":
    render_ro_registry()

elif page == "📈 Анализи и Справки (РО)":
    render_ro_analytics()
    
elif page == "🎯 Рекрутмънт и Подбор":
    render_recruitment_module()

elif page == "⚙️ Управление на достъпи":
    render_admin_panel()
