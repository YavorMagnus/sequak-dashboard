import streamlit as st
from supabase import create_client, Client
import os

# --- УМНА ИНИЦИАЛИЗАЦИЯ НА SUPABASE ---
# Търси ключовете първо в secrets, после в environment variables
try:
    url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("Липсват ключове за Supabase!")
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error(f"Грешка при свързване с базата: {e}")

# Глобални роли в системата
SYSTEM_ROLES = ["Супер-админ", "Администратор", "Power User", "Четец"]

# Матрица на правата (Permissions Matrix)
AVAILABLE_PERMISSIONS = {
    "dashboard": {
        "name": "Модул: Пропуснати ползи",
        "actions": {
            "read": "Визуализация на таблото (Четене)",
            "export": "Експорт на данни (Excel)",
            "upload": "Зареждане на нови данни (Внос)"
        }
    },
    "complaints": {
        "name": "Модул: Регистър Оплаквания",
        "actions": {
            "read": "Визуализация на регистъра (Четене)",
            "create": "Въвеждане на нов сигнал",
            "edit": "Редакция на сигнали (работа по канбан)",
            "cancel": "Анулиране на сигнал (Сгрешен запис)",
            "export": "Експорт на данни (Excel)"
        }
    },
    "recruitment": {
        "name": "Модул: Рекрутмънт",
        "actions": {
            "read": "Визуализация на позиции (Четене)",
            "manage_positions": "Създаване и управление на позиции",
            "upload_candidates": "Зареждане на CV-та",
            "evaluate": "Оценяване и местене по Канбан",
            "schedule": "Насрочване на интервюта",
            "soft_delete": "Изтриване (Преместване в кошче)"
        }
    }
}

def check_permission(module, action):
    """
    Универсална функция за проверка на права.
    Супер-админ и Администратор винаги имат пълен достъп.
    За останалите роли се проверява списъкът с права в сесията.
    """
    if "user_role" not in st.session_state:
        return False
    
    role = st.session_state.user_role
    if role in ["Супер-админ", "Администратор"]:
        return True
        
    permissions = st.session_state.get("permissions", {})
    module_perms = permissions.get(module, [])
    return action in module_perms
