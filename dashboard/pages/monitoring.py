"""Страница мониторинга системы"""

import streamlit as st
import pandas as pd
from datetime import datetime
import sys
from pathlib import Path

# Добавляем путь к utils
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.api_client import APIClient
from utils.config import COLORS, MOCK_METRICS, MOCK_HISTORY

# Инициализация клиента
if 'api_client' not in st.session_state:
    st.session_state.api_client = APIClient()

# Инициализация истории
if 'classification_history' not in st.session_state:
    st.session_state.classification_history = MOCK_HISTORY.copy()

# Кэширование проверки здоровья (5 секунд)
@st.cache_data(ttl=5)
def get_health_cached():
    """Кэшированная проверка здоровья"""
    try:
        return st.session_state.api_client.get_health(use_mock=True)
    except:
        return {"status": "unhealthy", "model_loaded": False}


def get_model_info():
    """Получение информации о модели"""
    try:
        return st.session_state.api_client.get_model_status(use_mock=True)
    except:
        return {"model_version": "unknown", "is_loaded": False, "num_classes": 17}


def calculate_metrics(history):
    """Расчет метрик из истории"""
    if not history:
        return MOCK_METRICS
    
    total = len(history)
    auto = sum(1 for item in history if item.get("decision") == "auto-process")
    manual = total - auto
    
    confidences = [item.get("confidence", 0) for item in history if "confidence" in item]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0
    
    return {
        "processed_today": total,
        "auto_processed": auto,
        "auto_processed_percent": (auto / total * 100) if total > 0 else 0,
        "manual_review": manual,
        "manual_review_percent": (manual / total * 100) if total > 0 else 0,
        "avg_confidence": avg_conf
    }


def display_history_table(history):
    """Отображение таблицы истории"""
    if not history:
        st.info("История классификаций пуста")
        return
    
    # Подготовка данных для таблицы
    data = []
    for item in history[:20]:  # Последние 20 записей
        text = item.get("text", "")
        text_preview = text[:60] + "..." if len(text) > 60 else text
        
        decision_icon = "✅" if item.get("decision") == "auto-process" else "⏳"
        decision_text = "Авто" if item.get("decision") == "auto-process" else "Ручная"
        
        data.append({
            "ID": item.get("id", "N/A"),
            "Текст": text_preview,
            "Класс": item.get("predicted_type", "N/A"),
            "Уверенность": f"{item.get('confidence', 0) * 100:.1f}%",
            "Решение": f"{decision_icon} {decision_text}",
            "Время": item.get("timestamp", "N/A"),
            "_full_text": text  # Для отображения при клике
        })
    
    df = pd.DataFrame(data)
    
    # Отображение таблицы с возможностью выбора строки
    st.markdown("### 📋 История классификаций")
    
    # Отображаем таблицу
    display_df = df[["ID", "Текст", "Класс", "Уверенность", "Решение", "Время"]].copy()
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )
    
    # Выбор строки через selectbox
    if len(data) > 0:
        st.markdown("---")
        st.markdown("### 📄 Просмотр деталей обращения")
        
        selected_id = st.selectbox(
            "Выберите обращение для просмотра деталей:",
            options=[item["ID"] for item in data],
            format_func=lambda x: f"{x} - {next((item['Текст'] for item in data if item['ID'] == x), '')}"
        )
        
        if selected_id:
            selected_item = next((item for item in data if item["ID"] == selected_id), None)
            if selected_item:
                st.text_area(
                    "Полный текст обращения:",
                    value=selected_item["_full_text"],
                    height=100,
                    disabled=True
                )
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Класс:** {selected_item['Класс']}")
                with col2:
                    st.markdown(f"**Уверенность:** {selected_item['Уверенность']}")
                with col3:
                    st.markdown(f"**Решение:** {selected_item['Решение']}")


def main():
    """Главная функция страницы"""
    st.title("📊 Мониторинг системы")
    
    # Статус системы
    st.markdown("### 🔍 Статус системы")
    
    health = get_health_cached()
    model_info = get_model_info()
    
    col1, col2 = st.columns(2)
    
    with col1:
        if health.get("status") == "healthy" and health.get("model_loaded"):
            st.success("✅ Система работает")
            st.markdown(f"**Версия модели:** {model_info.get('model_version', 'N/A')}")
            st.markdown(f"**Классов:** {model_info.get('num_classes', 'N/A')}")
        else:
            st.error("❌ Система недоступна")
            st.warning("Используются mock данные для демонстрации")
            st.markdown(f"**Версия модели:** {model_info.get('model_version', 'N/A')} (mock)")
            st.markdown(f"**Классов:** {model_info.get('num_classes', 'N/A')}")
    
    with col2:
        # Статус автоклассификации
        auto_classification = st.session_state.get("auto_classification", True)
        status_text = "✅ Включена" if auto_classification else "❌ Отключена"
        st.markdown(f"**Статус автоклассификации:** {status_text}")
        
        threshold = st.session_state.get("confidence_threshold", 0.7)
        st.markdown(f"**Порог уверенности:** {threshold * 100:.0f}%")
    
    st.divider()
    
    # Метрики
    st.markdown("### 📈 Метрики")
    
    history = st.session_state.get("classification_history", [])
    metrics = calculate_metrics(history)
    
    metric_cols = st.columns(4)
    
    with metric_cols[0]:
        st.metric(
            "Обработано сегодня",
            metrics["processed_today"]
        )
    
    with metric_cols[1]:
        auto_pct = metrics["auto_processed_percent"]
        st.metric(
            "Автоматически обработано",
            f"{metrics['auto_processed']} ({auto_pct:.1f}%)"
        )
    
    with metric_cols[2]:
        manual_pct = metrics["manual_review_percent"]
        st.metric(
            "На ручную проверку",
            f"{metrics['manual_review']} ({manual_pct:.1f}%)"
        )
    
    with metric_cols[3]:
        avg_conf = metrics["avg_confidence"]
        st.metric(
            "Средняя уверенность",
            f"{avg_conf * 100:.1f}%"
        )
    
    st.divider()
    
    # История классификаций
    display_history_table(history)
    
    # Обновление данных
    if st.button("🔄 Обновить данные", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# Вызов главной функции (для Streamlit pages)
main()

