"""Страница демонстрации классификации"""

import streamlit as st
from datetime import datetime
import sys
from pathlib import Path

# Добавляем путь к utils
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.api_client import APIClient
from utils.config import COLORS, MOCK_HISTORY, DASHBOARD_MODE

# Инициализация клиента
if 'api_client' not in st.session_state:
    st.session_state.api_client = APIClient()

# Инициализация истории
if 'classification_history' not in st.session_state:
    st.session_state.classification_history = MOCK_HISTORY.copy()

# Инициализация примера текста
if 'example_texts' not in st.session_state:
    st.session_state.example_texts = [
        "Не могу войти в сетевой диск S:",
        "Увольнение Иванова И.И. с должности менеджера",
        "Заказать визитки для отдела продаж, 500 шт, белые",
        "Согласование запроса на новую виртуальную машину",
        "Падает соединение с ВМ, статус недоступна"
    ]


def add_to_history(text: str, result: dict):
    """Добавление результата в историю"""
    history_item = {
        "id": f"ticket_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "text": text,
        "predicted_type": result.get("predicted_type", "Неизвестно"),
        "confidence": result.get("confidence", 0.0),
        "decision": result.get("decision", "manual-review"),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Добавляем в начало списка
    st.session_state.classification_history.insert(0, history_item)
    
    # Ограничиваем размер истории
    if len(st.session_state.classification_history) > 20:
        st.session_state.classification_history = st.session_state.classification_history[:20]


def display_result(result: dict):
    """Отображение результата классификации"""
    predicted_type = result.get("predicted_type", "Неизвестно")
    confidence = result.get("confidence", 0.0)
    decision = result.get("decision", "manual-review")
    # Поддержка обоих форматов: dict или список {category, score}
    probs_raw = result.get("probabilities", {})
    if isinstance(probs_raw, list):
        probabilities = {item.get("category"): item.get("score", 0.0) for item in probs_raw if isinstance(item, dict)}
    elif isinstance(probs_raw, dict):
        probabilities = probs_raw
    else:
        probabilities = {}
    
    # Три метрики в колонках
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 🏷️ Тип задачи")
        st.markdown(f"<h2 style='color: {COLORS['primary']}; margin-top: 0;'>{predicted_type}</h2>", 
                   unsafe_allow_html=True)
    
    with col2:
        st.markdown("### 📊 Уверенность")
        confidence_percent = confidence * 100
        color = COLORS['success'] if confidence >= 0.7 else COLORS['warning']
        st.markdown(f"<h2 style='color: {color}; margin-top: 0;'>{confidence_percent:.1f}%</h2>", 
                   unsafe_allow_html=True)
    
    with col3:
        st.markdown("### ⚡ Решение")
        if decision == "auto-process":
            st.markdown(f"<h2 style='color: {COLORS['success']}; margin-top: 0;'>✅ Автоматическая обработка</h2>", 
                       unsafe_allow_html=True)
        else:
            st.markdown(f"<h2 style='color: {COLORS['warning']}; margin-top: 0;'>⏳ Ручная проверка</h2>", 
                       unsafe_allow_html=True)
    
    st.divider()
    
    # Топ-5 вероятностей
    st.markdown("### 📈 Топ-5 вероятностей классов")
    
    # Сортируем вероятности по убыванию
    sorted_probs = sorted(
        probabilities.items(), 
        key=lambda x: x[1], 
        reverse=True
    )[:5]
    
    for class_name, prob in sorted_probs:
        prob_percent = prob * 100
        st.markdown(f"**{class_name}**")
        st.progress(prob, text=f"{prob_percent:.1f}%")
        st.markdown("<br>", unsafe_allow_html=True)


def main():
    """Главная функция страницы"""
    st.title("🎫 Service Desk Classifier")
    st.markdown("### Автоматическая классификация обращений в Service Desk")
    
    # Переключатель режима работы
    col_mode, col_info = st.columns([1, 3])
    with col_mode:
        current_mode = st.session_state.get("dashboard_mode", DASHBOARD_MODE)
        new_mode = st.selectbox(
            "Режим работы:",
            ["demo", "production"],
            index=0 if current_mode == "demo" else 1,
            help="Demo: быстрая классификация без логирования. Production: полный pipeline с логированием в БД."
        )
        if new_mode != current_mode:
            st.session_state.dashboard_mode = new_mode
            st.session_state.api_client.mode = new_mode
            st.rerun()
    
    with col_info:
        if current_mode == "production":
            st.info("🔒 Production режим: классификация через Ingestion Service с полным логированием в ticket_events")
        else:
            st.info("⚡ Demo режим: прямая классификация через ML Service (быстро, без логирования в БД)")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Инициализация текста из session_state
    if 'input_text' not in st.session_state:
        st.session_state.input_text = ""
    
    # Кнопки для примеров
    st.markdown("**Примеры для тестирования:**")
    example_cols = st.columns(5)
    for i, (col, example) in enumerate(zip(example_cols, st.session_state.example_texts)):
        with col:
            if st.button(f"Пример {i+1}", key=f"example_{i}", use_container_width=True):
                st.session_state.input_text = example
                st.rerun()
    
    # Текстовое поле для ввода
    # Используем key="input_text" - Streamlit автоматически синхронизирует значение
    # При нажатии на кнопки примеров значение устанавливается в st.session_state.input_text
    # и автоматически отображается в text_area благодаря key
    # Не передаем value явно - Streamlit использует значение из session_state через key
    text_input = st.text_area(
        "Введите текст обращения:",
        height=150,
        placeholder="Введите текст обращения...",
        key="input_text"
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Кнопка классификации
    classify_button = st.button(
        "🚀 Классифицировать",
        type="primary",
        use_container_width=True,
        disabled=len(text_input.strip()) < 3
    )
    
    # Результат классификации
    if classify_button and text_input.strip():
        current_mode = st.session_state.get("dashboard_mode", DASHBOARD_MODE)
        spinner_text = "Обработка запроса..." if current_mode == "demo" else "Создание тикета и обработка через pipeline..."
        
        with st.spinner(spinner_text):
            try:
                result = st.session_state.api_client.classify_text(
                    text_input.strip(),
                    use_mock=True,
                    mode=current_mode
                )
                
                if result:
                    # Добавляем в историю
                    add_to_history(text_input.strip(), result)
                    
                    # Отображаем результат
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown("---")
                    st.markdown("### ✅ Результат классификации")
                    display_result(result)
                    
                    # Информация о версии модели
                    try:
                        cfg = st.session_state.api_client.get_config(use_mock=True)
                        cfg_version = cfg.get("current_model_version", "unknown")
                    except Exception:
                        cfg_version = "unknown"

                    model_version = result.get("model_version", "unknown")

                    if cfg_version and cfg_version != "unknown":
                        if model_version != "unknown" and model_version != cfg_version:
                            st.warning(f"📦 Активная версия (Config): {cfg_version} • Ответ ML: {model_version}")
                        else:
                            st.info(f"📦 Версия модели: {cfg_version}")
                    else:
                        st.info(f"📦 Версия модели: {model_version}")
                    
                    # Показываем ticket_id в production режиме
                    if current_mode == "production" and result.get("ticket_id"):
                        ticket_id = result.get("ticket_id")
                        st.success(f"✅ Тикет создан: `{ticket_id}` (запись в ticket_events)")
                
            except ConnectionError as e:
                st.error(f"❌ {str(e)}")
                if current_mode == "production":
                    st.info("💡 Убедитесь, что Ingestion Service запущен на http://localhost:8000")
                else:
                    st.info("💡 Убедитесь, что ML Service запущен на http://localhost:8001")
            
            except ValueError as e:
                st.error(f"❌ Ошибка валидации: {str(e)}")
            
            except Exception as e:
                st.error(f"❌ Неожиданная ошибка: {str(e)}")
                st.info("💡 Используются mock данные для демонстрации")
                
                # Показываем mock результат
                result = st.session_state.api_client.classify_text(
                    text_input.strip(),
                    use_mock=True
                )
                if result:
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown("---")
                    st.markdown("### ✅ Результат классификации (Mock данные)")
                    display_result(result)
    
    # Предупреждение о минимальной длине
    if text_input and len(text_input.strip()) < 3:
        st.warning("⚠️ Текст должен содержать минимум 3 символа")


# Вызов главной функции (для Streamlit pages)
main()

