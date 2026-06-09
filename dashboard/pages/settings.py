"""Страница управления настройками"""

import streamlit as st
import sys
from pathlib import Path

# Добавляем путь к utils
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.api_client import APIClient
from utils.config import COLORS

# Инициализация клиента
if 'api_client' not in st.session_state:
    st.session_state.api_client = APIClient()

# Инициализация настроек
if 'auto_classification' not in st.session_state:
    st.session_state.auto_classification = True

if 'confidence_threshold' not in st.session_state:
    # Пытаемся загрузить из Config Service
    try:
        api_client = APIClient()
        config = api_client.get_config(use_mock=False)
        threshold = config.get("confidence_threshold", 0.7)
        # Убеждаемся, что значение в допустимом диапазоне
        if threshold < 0.01:
            threshold = 0.01
        elif threshold > 1.0:
            threshold = 1.0
        st.session_state.confidence_threshold = threshold
    except Exception:
        st.session_state.confidence_threshold = 0.7

if 'model_version' not in st.session_state:
    st.session_state.model_version = "v1.0"


def main():
    """Главная функция страницы"""
    st.title("⚙️ Управление")
    
    st.markdown("### 🎛️ Настройки классификации")
    
    # Toggle для автоклассификации
    auto_classification = st.toggle(
        "Автоклассификация",
        value=st.session_state.auto_classification,
        help="Когда включена, система автоматически обрабатывает обращения с уверенностью выше порога"
    )
    
    st.info("💡 Когда включена, система автоматически обрабатывает обращения с уверенностью ≥ порога")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Порог уверенности
    st.markdown("### 📊 Порог уверенности")
    
    # Конвертируем значение из десятичной дроби (0.01-1.0) в проценты (1-100) для отображения
    threshold_percent_current = int(st.session_state.confidence_threshold * 100)
    
    threshold_percent = st.slider(
        "",
        min_value=1,
        max_value=100,
        value=threshold_percent_current,
        step=1,
        format="%d%%",
        help="Обращения с уверенностью выше этого порога будут обрабатываться автоматически"
    )
    
    # Конвертируем обратно в десятичную дробь для сохранения
    threshold = threshold_percent / 100.0
    
    # Рекомендация
    if threshold_percent == 70:
        st.success(f"✅ Текущее значение: {threshold_percent}% (рекомендуется)")
    elif threshold_percent < 70:
        st.warning(f"⚠️ Текущее значение: {threshold_percent}% (низкий порог, больше автоматических обработок)")
    else:
        st.info(f"ℹ️ Текущее значение: {threshold_percent}% (высокий порог, больше ручных проверок)")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Версия модели
    st.markdown("### 📦 Версия модели")
    
    model_options = {
        "v1.0": {
            "label": "v1.0 (SMOTE: 97.5%)",
            "description": "Модель с применением SMOTE для балансировки классов, точность 97.5% (classifier_smote_new.pkl)"
        }
    }
    
    # Текущая версия: сначала пробуем Config Service, затем session_state, затем ML, затем дефолт
    try:
        config = st.session_state.api_client.get_config(use_mock=False)
        current_version = config.get("current_model_version")
    except Exception:
        current_version = None

    if not current_version:
        # если есть в session_state (последний выбор пользователя) — используем его
        current_version = st.session_state.get("model_version")

    if not current_version:
        # пробуем получить из ML
        try:
            model_status = st.session_state.api_client.get_model_status(use_mock=True)
            current_version = model_status.get("model_version")
        except Exception:
            current_version = None

    if not current_version:
        current_version = "v1.0"
    
    # Selectbox для выбора версии (только v1.0 доступна)
    if len(model_options) == 1:
        # Если только одна версия, показываем как disabled selectbox
        selected_version = list(model_options.keys())[0]
        st.selectbox(
            "Версия модели",
            options=[selected_version],
            index=0,
            format_func=lambda x: model_options[x]["label"],
            disabled=True,
            help="Доступна только версия v1.0"
        )
    else:
        selected_version = st.selectbox(
            "Выберите версию модели",
            options=list(model_options.keys()),
            index=list(model_options.keys()).index(current_version) if current_version in model_options else 0,
            format_func=lambda x: model_options[x]["label"]
        )
    
    # Описание выбранной версии
    st.info(f"📝 {model_options[selected_version]['description']}")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Кнопка сохранения
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        save_button = st.button(
            "💾 Сохранить настройки",
            type="primary",
            use_container_width=True
        )
    
    # Обработка сохранения
    if save_button:
        # Пытаемся применить версию модели через Config Service, затем перезагрузить модель в ML
        apply_ok = True
        threshold_ok = True
        
        # Обновление порога уверенности
        try:
            resp = st.session_state.api_client.update_threshold(threshold)
            if resp:
                st.success(f"✅ Порог уверенности обновлен до {threshold_percent}% через Config Service")
            else:
                threshold_ok = False
                st.warning("⚠️ Не удалось подтвердить обновление порога через Config Service")
        except Exception as e:
            threshold_ok = False
            st.warning(f"⚠️ Ошибка обновления порога: {str(e)}")
        
        # Переключение версии модели
        try:
            resp = st.session_state.api_client.switch_model_version(selected_version)
            if resp and resp.get("current_model_version") == selected_version:
                st.success(f"✅ Версия модели переключена на {selected_version} через Config Service")
            else:
                apply_ok = False
                st.warning("⚠️ Не удалось подтвердить переключение версии через Config Service")
        except Exception as e:
            apply_ok = False
            st.error(f"❌ Ошибка переключения версии: {str(e)}")

        # Перезагружаем модель в ML Service для применения
        try:
            reload_resp = st.session_state.api_client.reload_model(use_mock=False)
            if reload_resp.get("success"):
                st.success("🔄 ML Service: модель перезагружена")
            else:
                st.warning("⚠️ ML Service: не удалось перезагрузить модель")
        except Exception as e:
            st.warning(f"⚠️ Не удалось вызвать reload модели: {str(e)}")

        # Сохраняем в session_state
        st.session_state.auto_classification = auto_classification
        st.session_state.confidence_threshold = threshold
        st.session_state.model_version = selected_version

        # Итог и синхронизация выбора
        if apply_ok and threshold_ok:
            st.success(f"✅ Настройки успешно сохранены и применены (порог: {threshold_percent}%, модель: {selected_version})")
        else:
            st.info(f"ℹ️ Настройки сохранены локально (порог: {threshold_percent}%, модель: {selected_version}). Примените их вручную при необходимости.")
        
        # Информация о сохраненных настройках
        st.markdown("---")
        st.markdown("### 📋 Текущие настройки")
        
        settings_cols = st.columns(3)
        
        with settings_cols[0]:
            st.metric(
                "Автоклассификация",
                "✅ Включена" if auto_classification else "❌ Отключена"
            )
        
        with settings_cols[1]:
            st.metric(
                "Порог уверенности",
                f"{threshold_percent}%"
            )
        
        with settings_cols[2]:
            st.metric(
                "Версия модели",
                selected_version
            )
    
    st.divider()
    
    # Дополнительная информация
    st.markdown("### ℹ️ Дополнительная информация")
    
    with st.expander("📚 О пороге уверенности"):
        st.markdown("""
        **Порог уверенности** определяет, при какой минимальной уверенности модели 
        обращение будет обработано автоматически.
        
        - **Низкий порог (50-60%)**: Больше обращений обрабатывается автоматически, 
          но выше риск ошибок
        - **Средний порог (70%)**: Рекомендуемый баланс между автоматизацией и точностью
        - **Высокий порог (80-90%)**: Меньше ошибок, но больше обращений требует 
          ручной проверки
        """)
    
    with st.expander("🔄 Перезагрузка модели"):
        st.markdown("""
        Для перезагрузки модели используйте endpoint `/reload_model` в ML Service API.
        
        Это позволяет обновить модель без остановки сервиса (hot reload).
        """)
        
        if st.button("🔄 Перезагрузить модель через API", use_container_width=True):
            with st.spinner("Перезагрузка модели..."):
                try:
                    result = st.session_state.api_client.reload_model(use_mock=False)
                    if result.get("success"):
                        st.success(f"✅ {result.get('message', 'Модель успешно перезагружена')}")
                        if result.get("model_version"):
                            st.info(f"📦 Версия модели: {result.get('model_version')}")
                    else:
                        st.error(f"❌ {result.get('message', 'Не удалось перезагрузить модель')}")
                except ConnectionError as e:
                    st.error(f"❌ ML Service недоступен: {str(e)}")
                    st.info("💡 Убедитесь, что ML Service запущен на http://localhost:8001")
                except Exception as e:
                    st.error(f"❌ Ошибка: {str(e)}")


# Вызов главной функции (для Streamlit pages)
main()

