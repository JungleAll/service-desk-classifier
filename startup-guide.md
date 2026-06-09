# Полное пошаговое руководство по запуску Service Desk Classifier

## Список сервисов

Имеется пять сервисов (для полноценного запуска):
1. **Ingestion Service** (порт 8000) — прием обращений, валидация, постановка в очередь Redis
2. **Config Service** (порт 8002) — хранение конфигурации (активная версия модели, порог уверенности и т.д.)
3. **ML Service** (порт 8001) — API для классификации (читает активную версию из Config, может работать с Worker)
4. **Output Service** (порт 8003) — обработка результатов (коннекторы Jira/FileSystem/Mock)
5. **Dashboard** (порт 8501) — веб-интерфейс для демонстрации и управления

А также инфраструктура:
- **PostgreSQL** (порт 5432) — БД (ticket_events, configuration и т.д.)
- **Redis** (порт 6379) — очередь и кэш предсказаний

Рекомендуемый порядок запуска (локально):
1) PostgreSQL, Redis
2) Config Service (8002)
3) ML Service (8001)
4) Ingestion Service (8000) — опционально, если используете автоматическую обработку
5) Output Service (8003)
6) Dashboard (8501)

Альтернатива: `docker-compose up -d` — поднимет все компоненты в корректном порядке (см. раздел ниже).

---

## Порядок запуска сервисов (локально)

### Шаг A: Запустите инфраструктуру
- PostgreSQL и Redis (через docker или уже установленное окружение)
  - Пример (docker):
    ```bash
    docker compose up -d postgres redis
    ```
  - Проверьте, что переменные окружения для подключения настроены (см. shared/README.md).

### Шаг B: Запустите Config Service (порт 8002)
```bash
cd config_service
pip install -r requirements.txt
python run.py
```
Проверьте:
- http://localhost:8002/health — должен вернуть `healthy`
- http://localhost:8002/config — текущая конфигурация (в т.ч. current_model_version)

### Шаг C: Запустите ML Service (порт 8001)
```bash
cd ml_service
pip install -r requirements.txt
python run.py
```
**Важно:** ML Service при старте и перед классификацией пытается прочитать активную версию модели из Config Service. Если Config Service недоступен, ML Service продолжит работу с версией по умолчанию (v1.0) и выведет предупреждение в логах.

**Режимы работы ML Service:**
- **REST API режим (по умолчанию):** Worker отключен, классификация только через HTTP API
- **Worker режим:** Автоматическая обработка очереди Redis (включить через `WORKER_ENABLED=true`)

Проверьте:
- http://localhost:8001/health — должен вернуть `healthy`
- http://localhost:8001/model/status — увидите `model_version`, соответствующую Config
- В сообщении health будет указан статус Worker (если включен)

### Шаг C1 (опционально): Запустите Ingestion Service (порт 8000)
```bash
cd ingestion_service
pip install -r requirements.txt
python run.py
```
**Когда нужен:** Если используете автоматическую обработку через Worker или хотите создавать тикеты через API.

Проверьте:
- http://localhost:8000/health — должен вернуть `healthy`
- http://localhost:8000/docs — документация API

### Шаг D: Запустите Output Service (порт 8003)
```bash
cd output_service
pip install -r requirements.txt
python run.py
```
При отсутствии Jira рекомендуется:
- Установить `DESTINATION_TYPE=filesystem` или `DESTINATION_TYPE=mock`.
- Проверить: http://localhost:8003/health — должен вернуть `healthy`.

### Шаг E: Запустите Dashboard (порт 8501)
```bash
cd dashboard
pip install -r requirements.txt
streamlit run app.py
```
Откройте: http://localhost:8501

---

## Запуск через Docker Compose (все сразу)

### Подготовка (опционально)

Если вы запускаете локально (не через Docker), может потребоваться инициализация БД:

```bash
# Установите зависимости для инициализации БД
pip install psycopg2-binary

# Инициализируйте базу данных
python database/init_db.py
```

**Примечание:** При использовании Docker Compose БД инициализируется автоматически через `database/schema.sql`.

### Запуск всех сервисов

```bash
# Запуск всех сервисов
docker compose up -d

# Просмотр логов
docker compose logs -f

# Просмотр логов конкретного сервиса
docker compose logs -f ml-service

# Проверка статуса всех контейнеров
docker compose ps
```

Порядок будет корректным (DB/Redis → Config → ML → Ingestion → Output → Dashboard).

### Проверка работоспособности

```bash
# Health checks всех сервисов
curl http://localhost:8000/health  # Ingestion
curl http://localhost:8001/health  # ML Service
curl http://localhost:8002/health  # Config
curl http://localhost:8003/health  # Output

# Или откройте в браузере:
# http://localhost:8000/docs - Ingestion API
# http://localhost:8001/docs - ML Service API
# http://localhost:8002/docs - Config API
# http://localhost:8003/docs - Output API
# http://localhost:8501 - Dashboard
```

### Остановка

```bash
# Остановка всех сервисов
docker compose down

# Остановка с удалением volumes (удалит данные БД и Redis)
docker compose down -v
```

---

## Быстрый старт (5 минут)

### Шаг 1: Проверьте Python

Откройте командную строку (Windows: Win+R → cmd) и введите:

```bash
python --version
```

Должно быть: `Python 3.11` или выше. Если нет, установите с https://www.python.org/downloads/

---

### Шаг 2: Откройте командную строку в папке проекта

**Windows:**
1. Откройте проводник
2. Перейдите в папку с проектом (где находятся `ml_service` и `dashboard`)
3. В адресной строке напишите `cmd` и нажмите Enter

**Должно быть:**
```
C:\Users\YourName\service-desk-classifier>
```

---

### Шаг 3: Создайте виртуальное окружение (первый раз)

```bash
python -m venv venv
```

**Что это делает:** Создает изолированную среду для проекта

**Ждите:** ~30 секунд

---

### Шаг 4: Активируйте виртуальное окружение

**Windows:**
```bash
venv\Scripts\activate
```

**Mac/Linux:**
```bash
source venv/bin/activate
```

**Успех:** В начале строки появится `(venv)`
```
(venv) C:\Users\YourName\service-desk-classifier>
```

---

## Запуск ML Service (обязательно первым!)

**Примечание:** Для минимальной конфигурации (быстрый старт) Config Service опционален. ML Service может работать без него, используя версию модели по умолчанию (v1.0). Однако для полноценной работы рекомендуется запустить Config Service перед ML Service.

### Шаг 5: Установите зависимости ML Service

```bash
cd ml_service
pip install -r requirements.txt
```

**Ждите:** 2-5 минут (устанавливаются библиотеки)

**Что должно появиться:**
```
Successfully installed fastapi-0.104.1 uvicorn-0.24.0 ...
```

---

### Шаг 6: Проверьте наличие моделей

**Убедитесь, что в папке `models/v1.0/` есть файлы:**

```
models/v1.0/
├── classifier_smote_new.pkl
├── vectorizer_smote.pkl
└── label_encoder_smote.pkl

**Если файлов нет:** Скопируйте из папки с обученными моделями

---

### Шаг 7: Запустите ML Service

**Способ 1 (Рекомендуемый):**
```bash
python run.py
```

**Способ 2:**
```bash
uvicorn app:app --host 0.0.0.0 --port 8001
```

**Успех! Должно появиться:**
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
Loading models...
Models loaded successfully
  Classes: 17
ℹWorker отключен. Используйте REST API для классификации.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001
```

**Или если Worker включен:**
```
Worker для обработки очереди запущен
```

**ML Service запущен**

**Не закрывайте это окно!** ML Service должен работать все время.

**Примечание:** По умолчанию Worker отключен. Для автоматической обработки очереди установите `WORKER_ENABLED=true` перед запуском (см. раздел "Режимы работы ML Service" ниже).

---

### Шаг 8: Проверьте ML Service

**Откройте второе окно командной строки** (не закрывайте первое!)

**Windows:**
1. Win+R → cmd
2. Перейдите в папку проекта

**Проверка 1: Healthcheck**
```bash
curl http://localhost:8001/health
```

**Должно вернуться:**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "model_version": "v1.0",
  "message": "Сервис работает нормально"
}
```

**Или если Worker включен:**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "model_version": "v1.0",
  "message": "Сервис работает нормально (Worker: running)"
}
```

**Если у вас нет curl (Windows):**
Откройте браузер и перейдите по адресу:
```
http://localhost:8001/docs
```

Должна открыться страница Swagger UI с документацией API.

---

## Запуск Dashboard (веб-интерфейс)

### Шаг 9: Откройте третье окно командной строки

**Не закрывайте предыдущие окна!**

---

### Шаг 10: Активируйте виртуальное окружение

```bash
venv\Scripts\activate
```

---

### Шаг 11: Установите зависимости Dashboard

```bash
cd dashboard
pip install -r requirements.txt
```

**Ждите:** 1-2 минуты

---

### Шаг 12: Запустите Dashboard

```bash
streamlit run app.py
```

**Успех! Должно появиться:**
```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.1.100:8501
```

**Браузер автоматически откроется на http://localhost:8501**

**Dashboard запущен!**

---

## Режимы работы ML Service

ML Service поддерживает два режима работы:

### Режим 1: REST API (по умолчанию, без Worker)

**Описание:** Классификация выполняется только по HTTP запросу через API.

**Когда использовать:**
- Для демонстрации и тестирования
- Для разработки и отладки
- Когда нужен полный контроль над процессом

**Как использовать:**
```bash
# Worker отключен по умолчанию
# Просто запустите ML Service
python ml_service/run.py

# Классификация через API
curl -X POST "http://localhost:8001/classify" \
  -H "Content-Type: application/json" \
  -d '{"text": "Не могу войти в систему"}'
```

### Режим 2: С Worker (автоматическая обработка очереди)

**Описание:** Worker автоматически обрабатывает тикеты из очереди Redis.

**Когда использовать:**
- Для production окружения
- Для автоматической обработки большого количества тикетов
- Когда тикеты поступают из Ingestion Service

**Как включить:**
```bash
# 1. Установите переменные окружения
export WORKER_ENABLED=true
export OUTPUT_SERVICE_URL=http://localhost:8003
export REDIS_HOST=localhost
export REDIS_PORT=6379

# 2. Запустите ML Service
python ml_service/run.py

# 3. Создайте тикет через Ingestion Service
curl -X POST "http://localhost:8000/tickets" \
  -H "Content-Type: application/json" \
  -d '{"text": "Не могу войти в систему", "source": "api"}'

# 4. Worker автоматически обработает тикет:
#    - Получит из очереди Redis
#    - Классифицирует
#    - Отправит в Output Service
#    - Обновит статус в БД
```

**Поток работы с Worker:**
```
Ingestion Service → Redis Queue → ML Service Worker (внутри ML Service) → Output Service → Jira/FileSystem
```

**Примечание:** Worker является частью ML Service и работает как фоновый процесс внутри него, а не как отдельный сервис.

**Проверка статуса Worker:**
```bash
curl http://localhost:8001/health
# В ответе будет: "message": "Сервис работает нормально (Worker: running)"
```

Подробнее см. `ml_service/README.md` раздел "Режимы работы".

---

## Использование Dashboard

### Вкладка 1: Demo классификации

1. **Введите текст обращения** (или нажмите кнопку с примером)
   ```
   Не могу войти в систему
   ```

2. **Нажмите "Классифицировать"**

3. **Увидите результат:**
   - Тип задачи: "Запрос на обслуживание"
   - Уверенность: 95%
   - Решение: Автоматическая обработка
   - Топ-5 вероятностей с диаграммой

---

### Вкладка 2: Мониторинг

**Показывает:**
- Статус системы (зеленый индикатор)
- Информация о модели (v1.0, 17 классов)
- Таблица с историей классификаций

---

### Вкладка 3: Управление

**Можно настроить:**
- Включить/выключить автоклассификацию
- Изменить порог уверенности (slider 50%-100%)
- Выбрать версию модели

---

## Тестирование

### Тест 1: Через Dashboard

1. Откройте http://localhost:8501
2. Вкладка "Demo"
3. Введите: `"Не могу войти в корпоративную почту"`
4. Нажмите "Классифицировать"
5. Результат: "Запрос на обслуживание" с высокой уверенностью

---

### Тест 2: Через API (curl) - Прямая классификация

**Откройте командную строку:**

```bash
curl -X POST http://localhost:8001/classify ^
  -H "Content-Type: application/json" ^
  -d "{\"text\": \"Увольнение сотрудника Иванова И.И.\"}"
```

**Результат:**
```json
{
  "predicted_type": "HR: Увольнение",
  "confidence": 0.98,
  "decision": "auto-process"
}
```

### Тест 2a: Через Ingestion Service (с автоматической обработкой, если Worker включен)

**Создание тикета:**
```bash
curl -X POST "http://localhost:8000/tickets" ^
  -H "Content-Type: application/json" ^
  -d "{\"text\": \"Увольнение сотрудника Иванова И.И.\", \"source\": \"api\"}"
```

**Проверка статуса:**
```bash
# Используйте ticket_id из предыдущего ответа
curl "http://localhost:8000/status/{ticket_id}"
```

**Если Worker включен:** Тикет будет автоматически обработан. Если Worker отключен, тикет останется в очереди.

---

### Тест 3: Через Swagger UI

1. Откройте http://localhost:8001/docs
2. Найдите `POST /classify`
3. Нажмите "Try it out"
4. Введите текст: `"Заказать визитки для отдела"`
5. Нажмите "Execute"
6. Результат: "Заказ визиток"

---

## Примеры текстов для тестирования

### 1. HR-запросы:
```
"Увольнение Петрова П.П. с должности менеджера"
→ HR: Увольнение (98%)

"Приём нового сотрудника в отдел продаж"
→ HR: Приём (95%)
```

### 2. Технические запросы:
```
"Не могу подключиться к сетевому диску S:"
→ Запрос на обслуживание (92%)

"Согласование запроса на новую виртуальную машину"
→ Заявка на согласование ВМ (89%)
```

### 3. Административные запросы:
```
"Заказать визитки для 5 сотрудников, белые"
→ Заказ визиток (97%)

"Оформить гостевой пропуск на Иванова на 3 дня"
→ Заказ гостевого пропуска (94%)
```

---

## Частые проблемы и решения

### Проблема 1: "Python не найден"

**Решение:**
1. Установите Python 3.11+ с https://www.python.org/downloads/
2. При установке поставьте галочку "Add Python to PATH"

---

### Проблема 2: "pip не найден"

**Решение:**
```bash
python -m pip install --upgrade pip
```

---

### Проблема 3: ML Service не запускается

**Проверьте:**
1. Есть ли файлы моделей в `models/v1.0/`?
2. Активировано ли виртуальное окружение? (должен быть `(venv)`)
3. Установлены ли зависимости? (`pip install -r requirements.txt`)

**Ошибка: "Models not found"**
```bash
# Убедитесь, что вы в папке ml_service
cd ml_service

# Проверьте путь к моделям
ls ../models/v1.0/
```

---

### Проблема 4: Dashboard не подключается к ML Service

**Проверьте:**
1. Работает ли ML Service? Откройте http://localhost:8001/health
2. Правильный ли порт? ML Service должен быть на порту 8001

**Решение:**
```bash
# В Dashboard можно указать другой адрес ML Service
export ML_SERVICE_URL=http://localhost:8001
streamlit run app.py
```

---

### Проблема 5: "Port already in use"

**Решение:**

**Порт 8001 занят:**
```bash
# Запустите ML Service на другом порту
uvicorn app:app --host 0.0.0.0 --port 8081
```

**Порт 8501 занят:**
```bash
# Запустите Dashboard на другом порту
streamlit run app.py --server.port 8502
```

---

### Проблема 6: Ошибка импорта (ModuleNotFoundError)

**Решение:**
```bash
# Убедитесь, что виртуальное окружение активировано
venv\Scripts\activate

# Переустановите зависимости
pip install -r requirements.txt --force-reinstall
```

---

### Проблема 7: Проблемы с Docker Compose

#### Проблемы с подключением к БД

```bash
# Проверьте логи PostgreSQL
docker compose logs postgres

# Проверьте, что БД инициализирована
docker compose exec postgres psql -U postgres -d service_desk_db -c "\dt"
```

#### Проблемы с Redis

```bash
# Проверьте логи Redis
docker compose logs redis

# Проверьте подключение
docker compose exec redis redis-cli ping
```

#### Проблемы с моделями в Docker

```bash
# Убедитесь, что модели находятся в models/v1.0/
ls -la models/v1.0/

# Должны быть:
# - classifier_smote_new.pkl
# - vectorizer_smote.pkl
# - label_encoder_smote.pkl

# Проверьте, что volume смонтирован правильно в docker-compose.yml
```

---

## Остановка сервисов

**Для остановки любого сервиса:**
1. Перейдите в окно с запущенным сервисом
2. Нажмите `Ctrl+C`

**Должно появиться:**
```
Shutting down...
INFO:     Application shutdown complete.
```

---

## Перезапуск сервисов

**Если нужно перезапустить:**

1. Остановите сервис (`Ctrl+C`)
2. Запустите заново:

**ML Service:**
```bash
cd ml_service
python run.py
```

**Dashboard:**
```bash
cd dashboard
streamlit run app.py
```

---

## Структура окон при работе

**У вас должно быть открыто несколько окон (в зависимости от режима):**

**Минимальная конфигурация (REST API режим):**
```
Окно 1: ML Service (порт 8001)
├── Командная строка
└── Вывод: "Uvicorn running on http://0.0.0.0:8001"
└── Примечание: Config Service опционален для минимальной конфигурации

Окно 2: Dashboard (порт 8501)
├── Командная строка
└── Вывод: "You can now view your Streamlit app..."

Окно 3: Браузер
├── http://localhost:8501 (Dashboard)
└── 3 вкладки: Demo, Мониторинг, Управление
```

**Полная конфигурация (с Worker и автоматической обработкой):**
```
Окно 1: PostgreSQL + Redis (через Docker или отдельно)
Окно 2: Config Service (порт 8002) - рекомендуется для управления конфигурацией
Окно 3: ML Service (порт 8001) с Worker (Worker работает внутри ML Service)
Окно 4: Ingestion Service (порт 8000)
Окно 5: Output Service (порт 8003)
Окно 6: Dashboard (порт 8501)
Окно 7: Браузер с Dashboard
```

---

## Финальная проверка

### Checklist готовности к демонстрации:

**Минимальная конфигурация (REST API):**
- [ ] ML Service запущен (http://localhost:8001/health возвращает `healthy`)
- [ ] Dashboard открыт в браузере (http://localhost:8501)
- [ ] Классификация работает (попробуйте любой текст)
- [ ] Все 3 вкладки отображаются

**Полная конфигурация (с автоматической обработкой):**
- [ ] PostgreSQL и Redis запущены
- [ ] Config Service запущен (http://localhost:8002/health)
- [ ] ML Service запущен с Worker (http://localhost:8001/health показывает "Worker: running")
- [ ] Ingestion Service запущен (http://localhost:8000/health)
- [ ] Output Service запущен (http://localhost:8003/health)
- [ ] Dashboard открыт в браузере (http://localhost:8501)
- [ ] Автоматическая обработка работает (создайте тикет через Ingestion Service)

**Если все пункты выполнены — вы готовы к демонстрации.**

---

## Для демонстрации жюри

### Сценарий презентации (3-5 минут):

**1. Открытие (30 секунд)**
```
"Мы создали автоматизированную систему классификации обращений Service Desk,
которая с точностью 98.5% определяет тип обращения и принимает решение о
необходимости ручной обработки."
```

**2. Demo (2 минуты)**
- Откройте вкладку "Demo"
- Покажите 3-4 примера:
  1. "Не могу войти в систему" → Запрос на обслуживание (95%)
  2. "Увольнение Иванова И.И." → HR: Увольнение (98%)
  3. "Заказать визитки" → Заказ визиток (97%)
  4. "Какая погода?" → Низкая уверенность → Ручная проверка

**3. Мониторинг (1 минута)**
- Покажите вкладку "Мониторинг"
- Объясните метрики (80% авто, 20% ручная)
- Покажите историю обращений

**4. Управление (1 минута)**
- Покажите вкладку "Управление"
- Измените порог уверенности
- Переключите модель

**5. Заключение (30 секунд)**
```
"Система готова к интеграции с Jira, имеет REST API для автоматизации,
поддерживает два режима работы (REST API и автоматическая обработка через Worker),
и может обрабатывать тысячи обращений в час."
```

**Дополнительно (если есть время):**
- Покажите автоматическую обработку через Worker (создайте тикет через Ingestion Service)
- Покажите, как переключаться между режимами работы

---

## Поддержка

**Если что-то не работает:**

1. **Проверьте логи** в окне с запущенным сервисом
2. **Перезапустите сервисы** (Ctrl+C, затем запустить заново)
3. **Проверьте порты** (8000, 8001, 8002, 8003, 8501 должны быть свободны)
4. **Переустановите зависимости** (`pip install -r requirements.txt --force-reinstall`)

---
