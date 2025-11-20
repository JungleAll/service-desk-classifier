# Настройка Jira Service Desk API

## Обзор

Приложение поддерживает два способа создания тикетов в Jira:

1. **Стандартный Jira REST API** (`/rest/api/3/issue`) — для обычных Jira проектов
2. **Jira Service Desk API** (`/rest/servicedeskapi/request`) — для Jira Service Management проектов

## Когда использовать Service Desk API?

Используйте Service Desk API, если:
- Вы работаете с Jira Service Management (ранее Jira Service Desk)
- Нужно создавать requests (заявки) в Service Desk проектах
- Требуется учет специфики Service Desk (request types, SLA, каналы и т.д.)

## Настройка Service Desk API

### 1. Получение Service Desk ID

Service Desk ID можно получить несколькими способами:

#### Способ 1: Через REST API
```bash
curl -u username:api_token \
  "https://your-instance.atlassian.net/rest/servicedeskapi/servicedesk"
```

Ответ содержит список Service Desk проектов с их ID:
```json
{
  "size": 1,
  "values": [
    {
      "id": "1",
      "projectId": "10000",
      "projectName": "IT Service Desk",
      "projectKey": "ITSD"
    }
  ]
}
```

#### Способ 2: Через UI
1. Откройте Jira Service Management
2. Перейдите в Project Settings → Service Desk
3. В URL будет виден ID: `.../servicedesk/1/...` (где `1` — это Service Desk ID)

### 2. Получение Request Type ID

Request Type ID можно получить через REST API:

```bash
curl -u username:api_token \
  "https://your-instance.atlassian.net/rest/servicedeskapi/servicedesk/{serviceDeskId}/requesttype"
```

Пример ответа:
```json
{
  "size": 3,
  "values": [
    {
      "id": "1",
      "name": "Incident",
      "description": "Report an incident"
    },
    {
      "id": "2",
      "name": "Service Request",
      "description": "Request a service"
    }
  ]
}
```

### 3. Настройка переменных окружения

Установите следующие переменные окружения:

```bash
# Включить Service Desk API
export JIRA_USE_SERVICEDESK_API=true

# Обязательные параметры
export JIRA_SERVICE_DESK_ID="1"  # ID вашего Service Desk проекта
export JIRA_REQUEST_TYPE_ID="1"   # ID типа запроса (например, Incident)

# Стандартные параметры Jira
export JIRA_URL="https://your-instance.atlassian.net"
export JIRA_USER="your-email@example.com"
export JIRA_API_TOKEN="your-api-token"
export JIRA_PROJECT_KEY="ITSD"  # Не используется в Service Desk API, но может потребоваться для других операций
```

### 4. Пример конфигурации в docker-compose.yml

```yaml
services:
  output_service:
    environment:
      - JIRA_USE_SERVICEDESK_API=true
      - JIRA_SERVICE_DESK_ID=1
      - JIRA_REQUEST_TYPE_ID=1
      - JIRA_URL=https://your-instance.atlassian.net
      - JIRA_USER=your-email@example.com
      - JIRA_API_TOKEN=your-api-token
      - DESTINATION_TYPE=jira
```

## Формат запроса Service Desk API

При использовании Service Desk API запрос отправляется в следующем формате:

```json
{
  "serviceDeskId": "1",
  "requestTypeId": "1",
  "requestFieldValues": {
    "summary": "Краткое описание",
    "description": "Полное описание",
    "priority": {
      "name": "Medium"
    }
  }
}
```

## Сравнение API

| Параметр | Стандартный API | Service Desk API |
|----------|----------------|------------------|
| Endpoint | `/rest/api/3/issue` | `/rest/servicedeskapi/request` |
| Проект | `project.key` | `serviceDeskId` |
| Тип | `issuetype.name` | `requestTypeId` |
| Подходит для | Обычные Jira проекты | Service Management проекты |
| Учет SLA | Нет | Да |
| Request Types | Нет | Да |
| Каналы | Нет | Да |

## Документация

- [Jira Service Management REST API](https://docs.atlassian.com/jira-servicedesk/REST/5.17.2/)
- [Создание requests через Service Desk API](https://docs.atlassian.com/jira-servicedesk/REST/5.17.2/#servicedeskapi/request-createRequest)

## Устранение неполадок

### Ошибка: "JIRA_SERVICE_DESK_ID не настроен"
- Убедитесь, что `JIRA_USE_SERVICEDESK_API=true`
- Проверьте, что `JIRA_SERVICE_DESK_ID` установлен и содержит корректный ID

### Ошибка: "JIRA_REQUEST_TYPE_ID не настроен"
- Убедитесь, что `JIRA_REQUEST_TYPE_ID` установлен
- Проверьте, что ID соответствует существующему Request Type в вашем Service Desk проекте

### Ошибка 400: "Invalid request"
- Проверьте формат запроса
- Убедитесь, что Service Desk ID и Request Type ID существуют
- Проверьте права доступа пользователя к Service Desk проекту

### Ошибка 403: "Forbidden"
- Убедитесь, что пользователь имеет права на создание requests в Service Desk проекте
- Проверьте, что API token имеет необходимые права

