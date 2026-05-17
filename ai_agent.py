import google.generativeai as genai
import streamlit as st

# Инициализация на Gemini API с ключа от Streamlit Secrets
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    # Използваме динамичен алиас 'gemini-flash' - винаги сочи към най-новата стабилна версия!
    model = genai.GenerativeModel('gemini-flash')
except Exception as e:
    st.error(f"Грешка при зареждане на Gemini API: {e}")

def translate_cv_text(original_text):
    """
    Превежда текста на български и го форматира:
    [Превод]
    ---
    [Оригинал]
    """
    if not original_text or len(original_text.strip()) < 5:
        return original_text

    prompt = f"""
    You are a professional HR assistant and translator.
    Translate the following candidate CV or questionnaire text into Bulgarian.
    Return strictly the translated text, nothing else. Do not add conversational filler.

    TEXT TO TRANSLATE:
    {original_text}
    """

    try:
        response = model.generate_content(prompt)
        translated_text = response.text.strip()
        
        # Форматиране: Превод отгоре, оригинален текст отдолу
        final_output = f"{translated_text}\n\n---\n**Оригинален текст:**\n{original_text}"
        return final_output
        
    except Exception as e:
        # В случай на грешка (напр. паднал интернет), връщаме оригинала, за да не трием данни
        return f"⚠️ Системна грешка при превода: {e}\n\n{original_text}"

# Тук утре ще добавим втората функция: evaluate_candidate_with_ai()
