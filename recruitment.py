import streamlit as st
import pandas as pd
from utils import supabase, check_permission

# --- ТВОИТЕ ФИРМИ (Можеш да ги редактираш тук по всяко време) ---
COMPANIES = [
    "Фирма 1 (Строителство)", 
    "Фирма 2 (Логистика)", 
    "Фирма 3 (Търговия)", 
    "Холдинг Център"
]

# --- THE MODAL: ГОЛЕМИЯТ КАРТОН НА КАНДИДАТА ---
@st.dialog("📄 Картон на кандидата", width="large")
def open_candidate_card(candidate_name, status):
    st.subheader(f"👤 {candidate_name}")
    st.caption(f"Текущ статус: **{status}**")
    
    # Контролен панел (Екшън бутони)
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.selectbox("Промени статус", ["Нов", "Телефонно интервю", "Живо интервю", "Одобрен", "Отхвърлен", "Преместен"], label_visibility="collapsed")
    with col2:
        st.button("💾 Запиши статус", use_container_width=True)
    with col3:
        st.button("✉️ Сподели профил", use_container_width=True)
    with col4:
        st.button("🗑️ Изтрий", type="primary", use_container_width=True)
        
    st.markdown("---")
    
    # Анатомия на досието (Табовете)
    tabs = st.tabs(["📋 Въпросник", "📝 Бележки", "📄 CV", "📞 Интервюта", "📊 Скор-карта"])
    
    with tabs[0]:
        st.info("Тук парсърът ще излее само въпросите и отговорите от HTML-а.")
    with tabs[1]:
        st.warning("Тук ще са вътрешните коментари от екипа и Jobs.bg бележките.")
    with tabs[2]:
        st.success("Тук ще е изчистеният текст от PDF-а (плюс снимката горе вляво).")
    with tabs[3]:
        st.write("История на интервютата и обратна връзка.")
    with tabs[4]:
        st.write("Слайдерите за оценка (Сервизен, Търговски и т.н.).")

# --- ОСНОВЕН РЕНДЕР НА МОДУЛА ---
def render_recruitment_module():
    st.header("📋 Модул Подбор (V4 Enterprise)")

    if not check_permission("recruitment", "read"):
        st.error("Нямате достъп до този модул.")
        return

    # 1. HOLDING VIEW (Филтър по фирми)
    st.write("### 🏢 Работен плот по дружества")
    selected_company = st.pills("Изберете компания", COMPANIES, default=None)

    if not selected_company:
        st.info("👈 Моля, изберете фирма от холдинга, за да заредите кампаниите.")
        return

    st.divider()

    # 2. PROJECT VIEW (Обявите)
    st.write(f"### 💼 Кампании за {selected_company}")
    
    # Създаване на нова позиция (Тест на Матрицата)
    if check_permission("recruitment", "manage_positions"):
        with st.expander("➕ Създай нова обява / кампания"):
            with st.form("new_pos_form"):
                pos_title = st.text_input("Име на позицията (напр. Складов работник)")
                pos_method = st.selectbox("Метод за оценка на кандидатите", ["Процентна матрица", "Обща оценка 1-10", "Свободен текст (за AI)"])
                
                if st.form_submit_button("Регистрирай кампанията"):
                    if pos_title:
                        supabase.table("hr_positions").insert({
                            "company_name": selected_company,
                            "title": pos_title,
                            "evaluation_method": pos_method
                        }).execute()
                        st.success("Кампанията е създадена!")
                        st.rerun()

    # Зареждане на позициите за тази фирма
    pos_res = supabase.table("hr_positions").select("*").eq("company_name", selected_company).order("created_at", desc=True).execute()
    positions = pos_res.data if pos_res.data else []

    if not positions:
        st.warning("Все още няма създадени обяви за това дружество.")
        return

    # 3. GRID VIEW (Кандидатите)
    st.divider()
    selected_pos_title = st.selectbox("Разгледай кандидати за:", [p["title"] for p in positions])
    
    st.write("### 👥 Кандидати")
    
    # Филтър статуси (Вместо Канбан)
    status_filter = st.pills("Филтър по статус:", ["Всички", "Нови / Некласифицирани", "За интервю", "Отхвърлени"], default="Всички")
    
    # Демонстрация на Картона (тъй като базата още е празна)
    st.info("В момента базата е празна. Когато налеем ZIP-овете, тук ще има решетка от карти със снимки.")
    
    if st.button("👁️ Отвори Демо 'Картон на кандидата'"):
        open_candidate_card("Любомир (Демо)", "Нов / Некласифициран")

if __name__ == "__main__":
    render_recruitment_module()
