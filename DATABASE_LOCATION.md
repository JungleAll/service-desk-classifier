# Расположение базы данных PostgreSQL и поведение при остановке

**Дата создания:** 2025-01-18 08:15:00  
**Версия:** 1.0  
**Последнее обновление:** 2025-01-18 08:15:00

---

## Где находится база данных PostgreSQL

### Вариант 1: Docker Compose (текущая конфигурация)

При использовании `docker-compose.yml` PostgreSQL хранит данные в **Docker Volume**.

#### Конфигурация из `docker-compose.yml`:

```yaml
postgres:
  image: postgres:15-alpine
  volumes:
    - postgres_data:/var/lib/postgresql/data
    - ./database/schema.sql:/docker-entrypoint-initdb.d/schema.sql

volumes:
  postgres_data:  # Именованный Docker Volume
```

#### Физическое расположение данных:

**Windows:**
```
C:\ProgramData\Docker\wsl\data\ext4.vhdx
Или через Docker Desktop:
\\wsl$\docker-desktop-data\data\docker\volumes\service-desk-classifier_postgres_data\_data
```

**Linux:**
```
/var/lib/docker/volumes/service-desk-classifier_postgres_data/_data
```

**Mac:**
```
~/Library/Containers/com.docker.docker/Data/vms/0/data/docker/volumes/service-desk-classifier_postgres_data/_data
```

#### Как узнать точное расположение:

```bash
# Проверка информации о volume
docker volume inspect service-desk-classifier_postgres_data

# Просмотр всех volumes
docker volume ls

# Просмотр содержимого volume (требует прав)
docker run --rm -v service-desk-classifier_postgres_data:/data alpine ls -la /data
```

**Вывод команды `docker volume inspect`:**

```json
[
    {
        "CreatedAt": "2025-01-18T08:00:00Z",
        "Driver": "local",
        "Labels": {
            "com.docker.compose.project": "service-desk-classifier",
            "com.docker.compose.volume": "postgres_data"
        },
        "Mountpoint": "/var/lib/docker/volumes/service-desk-classifier_postgres_data/_data",
        "Name": "service-desk-classifier_postgres_data",
        "Options": null,
        "Scope": "local"
    }
]
```

**Важно:** `Mountpoint` показывает путь внутри Docker VM, а не на вашем компьютере напрямую.

### Вариант 2: Локальная установка PostgreSQL

Если PostgreSQL установлен локально (не через Docker), данные находятся:

**Windows:**
```
C:\Program Files\PostgreSQL\15\data\
Или: C:\Users\<username>\AppData\Local\PostgreSQL\data\
```

**Linux:**
```
/var/lib/postgresql/15/main/
Или: /usr/local/pgsql/data/
```

**Mac:**
```
/usr/local/var/postgres/
Или: ~/Library/Application Support/PostgreSQL/var-15/
```

---

## Что происходит с базой данных при остановке приложения

### Сценарий 1: `docker compose down` (стандартная остановка)

**Что происходит:**

✅ **Данные сохраняются:**
- Контейнер PostgreSQL останавливается
- Все данные остаются в Docker Volume `postgres_data`
- Volume **НЕ удаляется**

**Результат:**
- ✅ Все таблицы сохраняются (`ticket_events`, `configuration`, `audit_logs`, и др.)
- ✅ Все данные сохраняются (обращения, конфигурация, метрики, аудит)
- ✅ При следующем запуске (`docker compose up`) все данные будут доступны

**Команда:**
```bash
docker compose down
```

**Что сохраняется:**
- ✅ Все таблицы БД
- ✅ Все записи в таблицах
- ✅ Настройки конфигурации
- ✅ История аудита
- ✅ Метрики классификаций

### Сценарий 2: `docker compose down -v` (остановка с удалением volumes)

**Что происходит:**

❌ **Данные удаляются:**
- Контейнер PostgreSQL останавливается
- Docker Volume `postgres_data` **удаляется**
- Все данные теряются

**Результат:**
- ❌ Все таблицы удаляются
- ❌ Все данные удаляются (обращения, конфигурация, метрики, аудит)
- ⚠️ При следующем запуске БД будет инициализирована заново через `schema.sql`

**Команда:**
```bash
docker compose down -v
```

**Что удаляется:**
- ❌ Все таблицы БД
- ❌ Все записи в таблицах
- ❌ Настройки конфигурации
- ❌ История аудита
- ❌ Метрики классификаций

**Что восстанавливается:**
- ✅ Схема БД (из `database/schema.sql`)
- ✅ Начальные значения конфигурации
- ✅ Информация о модели v1.0

### Сценарий 3: Остановка отдельных сервисов (не PostgreSQL)

**Что происходит:**

✅ **Данные сохраняются:**
- PostgreSQL продолжает работать
- Все данные остаются доступными
- Только приложение останавливается

**Пример:**
```bash
# Остановка только приложений
docker compose stop ingestion-service ml-service config-service output-service

# PostgreSQL продолжает работать
docker ps | grep postgres  # Контейнер все еще работает
```

**Результат:**
- ✅ Все данные сохраняются
- ✅ Можно подключиться к БД напрямую
- ✅ При запуске сервисов все данные будут доступны

### Сценарий 4: Перезапуск контейнера PostgreSQL

**Что происходит:**

✅ **Данные сохраняются:**
- Контейнер перезапускается
- Volume остается смонтированным
- Все данные остаются в volume

**Команда:**
```bash
# Перезапуск только PostgreSQL
docker compose restart postgres

# Или через docker
docker restart service-desk-postgres
```

**Результат:**
- ✅ Все данные сохраняются
- ✅ БД доступна после перезапуска

---

## 🔄 Сравнение сценариев остановки

| Действие | Команда | Данные сохраняются? | Volume удаляется? | БД инициализируется заново? |
|----------|---------|---------------------|-------------------|------------------------------|
| **Стандартная остановка** | `docker compose down` | ✅ Да | ❌ Нет | ❌ Нет |
| **Остановка с удалением** | `docker compose down -v` | ❌ Нет | ✅ Да | ✅ Да (из schema.sql) |
| **Остановка приложений** | `docker compose stop <service>` | ✅ Да | ❌ Нет | ❌ Нет |
| **Перезапуск PostgreSQL** | `docker compose restart postgres` | ✅ Да | ❌ Нет | ❌ Нет |

---

## 💾 Резервное копирование данных (не реализовано)

### Создание резервной копии БД

**Способ 1: pg_dump (рекомендуется)**

```bash
# Создание дампа БД
docker exec service-desk-postgres pg_dump -U postgres service_desk_db > backup_$(date +%Y%m%d_%H%M%S).sql

# Или через docker compose
docker compose exec postgres pg_dump -U postgres service_desk_db > backup_$(date +%Y%m%d_%H%M%S).sql
```

**Способ 2: Копирование volume**

```bash
# Создание копии volume
docker run --rm -v service-desk-classifier_postgres_data:/source -v $(pwd):/backup alpine tar czf /backup/postgres_data_backup_$(date +%Y%m%d_%H%M%S).tar.gz /source
```

### Восстановление из резервной копии

```bash
# Восстановление из дампа
docker exec -i service-desk-postgres psql -U postgres service_desk_db < backup_20250118_081500.sql

# Или через docker compose
docker compose exec -T postgres psql -U postgres service_desk_db < backup_20250118_081500.sql
```

---

## 📊 Структура данных PostgreSQL

### Таблицы в БД (из `database/schema.sql`):

1. **ticket_events** - все обращения и их статусы
2. **metrics** - метрики классификаций
3. **configuration** - текущая конфигурация системы
4. **config_audit_log** - история изменений конфигурации
5. **model_versions** - информация о версиях моделей
6. **error_logs** - логи ошибок
7. **audit_logs** - аудит обработки результатов

### Размер данных:

Ориентировочные размеры таблиц:

| Таблица | Типичный размер |
|---------|----------------|
| `ticket_events` | ~1-10 MB (зависит от количества обращений) |
| `config_audit_log` | ~100-500 KB (история изменений) |
| `audit_logs` | ~500 KB - 5 MB (история обработки) |
| `error_logs` | ~100-500 KB (логи ошибок) |
| `metrics` | ~100 KB - 1 MB (метрики) |
| `configuration` | ~10 KB (конфигурация) |
| `model_versions` | ~10 KB (версии моделей) |

**Общий размер БД:** ~2-20 MB (для среднего использования)

---

## 🔍 Проверка состояния БД

### Проверка размера БД:

```bash
# Размер базы данных
docker exec service-desk-postgres psql -U postgres -d service_desk_db -c "SELECT pg_size_pretty(pg_database_size('service_desk_db'));"

# Размер каждой таблицы
docker exec service-desk-postgres psql -U postgres -d service_desk_db -c "
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

### Подключение к БД:

```bash
# Через docker exec
docker exec -it service-desk-postgres psql -U postgres -d service_desk_db

# Через docker compose
docker compose exec postgres psql -U postgres -d service_desk_db

# Локальное подключение (если порт 5432 открыт)
psql -h localhost -U postgres -d service_desk_db
```

---

## ⚠️ Важные замечания

### 1. Бэкапы перед удалением

**ВСЕГДА создавайте бэкап перед выполнением:**
```bash
docker compose down -v  # Удалит все данные!
```

### 2. Миграции данных

При изменении схемы БД:
- Создайте бэкап
- Обновите `database/schema.sql`
- При следующем запуске с `-v` схема применится заново

### 3. Персистентность данных

**Данные сохраняются между перезапусками:**
- ✅ При `docker compose down` и `docker compose up`
- ✅ При перезапуске контейнера
- ✅ При обновлении Docker

**Данные удаляются при:**
- ❌ `docker compose down -v`
- ❌ Удалении volume вручную
- ❌ Переустановке Docker

---

## 📝 Рекомендации

### Для разработки:

1. Используйте `docker compose down` (без `-v`) для сохранения данных
2. Создавайте бэкапы регулярно
3. Используйте `-v` только когда нужно сбросить данные

### Для production:

1. Настройте автоматические бэкапы
2. Используйте внешние volumes или bind mounts
3. Мониторьте размер БД
4. Регулярно проверяйте целостность данных

---

**Дата последнего обновления:** 2025-01-18 08:15:00  
**Версия:** 1.0

