"""Главное приложение Streamlit Dashboard для Service Desk Classifier"""

import streamlit as st
import sys
from pathlib import Path

# Добавляем путь к utils
sys.path.insert(0, str(Path(__file__).parent))

from utils.config import COLORS

# Настройка страницы
st.set_page_config(
    page_title="Service Desk Classifier",
    page_icon="🎫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Кастомный CSS для улучшения внешнего вида
st.markdown(f"""
    <style>
        /* Основные стили */
        .main {{
            background-color: {COLORS['background']};
        }}
        
        /* Заголовки */
        h1 {{
            color: {COLORS['primary']};
            font-weight: bold;
        }}
        
        h2 {{
            color: {COLORS['text']};
        }}
        
        h3 {{
            color: {COLORS['text']};
        }}
        
        /* Кнопки */
        .stButton > button {{
            background-color: {COLORS['primary']};
            color: white;
            border-radius: 5px;
            border: none;
            padding: 0.5rem 1rem;
            font-weight: 500;
            transition: all 0.3s ease;
        }}
        
        .stButton > button:hover {{
            background-color: {COLORS['primary']};
            opacity: 0.9;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }}
        
        /* Метрики */
        [data-testid="stMetricValue"] {{
            font-size: 2rem;
            font-weight: bold;
        }}
        
        /* Прогресс-бары */
        .stProgress > div > div > div {{
            background-color: {COLORS['primary']};
        }}
        
        /* Боковая панель */
        .css-1d391kg {{
            background-color: {COLORS['background']};
        }}
        
        /* Контейнеры */
        .block-container {{
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }}
        
        /* Таблицы */
        .dataframe {{
            border-radius: 5px;
        }}
        
        /* Успешные сообщения */
        .stSuccess {{
            background-color: {COLORS['success']};
            color: white;
        }}
        
        /* Предупреждения */
        .stWarning {{
            background-color: {COLORS['warning']};
            color: white;
        }}
        
        /* Ошибки */
        .stError {{
            background-color: {COLORS['error']};
            color: white;
        }}
        
        /* Информация */
        .stInfo {{
            background-color: {COLORS['primary']};
            color: white;
        }}
    </style>
""", unsafe_allow_html=True)

# Боковая панель с навигацией
with st.sidebar:
    st.title("🎫 Service Desk Classifier")
    st.markdown("---")
    
    st.markdown("### 📋 Навигация")
    
    # Информация о сервисе
    st.info("""
    **Service Desk Classifier** - система автоматической классификации обращений.
    
    Используйте вкладки для навигации по функциям.
    """)
    
    st.markdown("---")
    
    # Статус подключения
    try:
        from utils.api_client import APIClient
        api_client = APIClient()
        is_available = api_client.is_available()
        
        if is_available:
            st.success("✅ ML Service доступен")
        else:
            st.warning("⚠️ ML Service недоступен\n(используются mock данные)")
    except:
        st.warning("⚠️ ML Service недоступен\n(используются mock данные)")
    
    st.markdown("---")
    
    # Информация о версии
    st.markdown("**Версия:** 1.0.0")
    st.markdown("**Дата:** 2025-01-15")

# Главная страница
st.title("🎫 Service Desk Classifier Dashboard")
st.markdown("### Добро пожаловать в систему автоматической классификации обращений Service Desk")

st.markdown("---")

# Описание функциональности
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    ### 🚀 Классификация
    Вкладка **Demo** позволяет:
    - Ввести текст обращения
    - Получить предсказание класса
    - Увидеть уверенность модели
    - Просмотреть топ-5 вероятностей
    """)

with col2:
    st.markdown("""
    ### 📊 Мониторинг
    Вкладка **Мониторинг** показывает:
    - Статус системы
    - Метрики обработки
    - Историю классификаций
    - Статистику по решениям
    """)

with col3:
    st.markdown("""
    ### ⚙️ Управление
    Вкладка **Управление** позволяет:
    - Настроить автоклассификацию
    - Изменить порог уверенности
    - Выбрать версию модели
    - Сохранить настройки
    """)

st.markdown("---")

# Быстрый старт
st.markdown("### 🎯 Быстрый старт")

st.markdown("""
1. Перейдите на вкладку **Demo классификации**
2. Введите текст обращения или выберите пример
3. Нажмите кнопку **Классифицировать**
4. Просмотрите результат и метрики
""")

st.info("💡 **Совет:** Если ML Service недоступен, будут использоваться mock данные для демонстрации функциональности.")

# Примеры текстов
with st.expander("📝 Примеры текстов для тестирования"):
    example_texts = [
        "Не могу войти в сетевой диск S:",
        "Увольнение Иванова И.И. с должности менеджера",
        "Заказать визитки для отдела продаж, 500 шт, белые",
        "Согласование запроса на новую виртуальную машину",
        "Падает соединение с ВМ, статус недоступна"
    ]
    
    for i, text in enumerate(example_texts, 1):
        st.markdown(f"**{i}.** {text}")

# Футер
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #7f8c8d;'>"
    "Service Desk Classifier Dashboard v1.0.0 | "
    "Создано для демонстрации ML Service"
    "</div>",
    unsafe_allow_html=True
)

