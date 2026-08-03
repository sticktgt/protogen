# API модуля `data_schema`

Базовый префикс API:

```text
/api/data-schema
```

Все методы требуют авторизованного пользователя. Доступ к данным проверяется по `workspace_id`: пользователь должен иметь доступ к указанному workspace.

`workspace_id` передается:

- как query-параметр в GET и DELETE запросах;
- в JSON-теле POST и PUT запросов.

API работает с логической схемой данных. Он не создает физические таблицы, SQL, миграции и код прототипа.


## AI-синхронизация схемы данных

Синхронизация начинается одним ограниченным LangChain-agent во временной копии схемы. Агент загружает компактный контекст, записывает логическую структуру, напрямую формирует результаты всех требований и завершает работу технической проверкой. Затем выполняются две независимые сфокусированные смысловые проверки: покрытие требований и внутренняя согласованность схемы. При конкретных issues первый отдельный LLM-вызов возвращает полный структурированный план коррекции для `must_fix` и совместимых `advisory`; backend технически применяет его как одну транзакцию. После verification допускаются ограниченные точечные recovery-раунды только по оставшимся `must_fix`, каждый с одним структурированным планом и одной verification. Shell и произвольный доступ к файловой системе не предоставляются.

Backend не интерпретирует требования и не исправляет содержательные решения LLM. Он выполняет только технические операции: проверяет tool payload, допустимые типы и cardinality, точное существование ID, сохранность базовых объектов, полноту классификации актуального набора готовых требований и корректность файлов схемы. Ссылки из базовой схемы на requirement ID, которых нет в актуальном наборе, сохраняются и выводятся аналитику отдельно для ручной проверки; новые неизвестные ID отклоняются. LLM-кандидаты на очистку также сохраняются отдельно, не передаются в correction/recovery и не влияют на возможность применения.

### Запуск и проверка LLM

- `POST /api/data-schema/agent/llm/test` — проверить пользовательскую конфигурацию LLM и tool calling. Тело: `{"workspace_id":"ws_demo"}`.
- `POST /api/data-schema/agent-runs` — начать синхронизацию. Тело содержит `workspace_id`, `requirements_path`, необязательные `user_request` и `base_mode` (`current` или `initial`). Путь должен быть относительным к workspace и не может выходить за его пределы.

Backend копирует требования и текущую схему только во временную папку запуска, сохраняет reference-файлы и запускает агента. В канонической схеме после применения остаётся только `requirements_source.json` со ссылкой и контрольной суммой.

### Состояние и observability

- `GET /api/data-schema/agent-runs/active?workspace_id=...` — активный запуск.
- `GET /api/data-schema/agent-runs/{run_id}?workspace_id=...` — статус, этап, отчёт, встроенные метрики и последние события.
- `GET /api/data-schema/agent-runs/{run_id}/events?workspace_id=...&after=0&limit=200` — инкрементальный журнал, количество LLM/tool calls и token usage.
- `GET /api/data-schema/agent-runs/{run_id}/changes?workspace_id=...` — детерминированный diff сущностей, полей, связей, справочников, значений и requirement links.
- `GET /api/data-schema/agent-runs/{run_id}/file-diff?workspace_id=...` — построчный unified diff файлов между базовой и результирующей схемой.
- `GET /api/data-schema/agent-runs/{run_id}/requirements-data-result?workspace_id=...` — результат для каждого требования: `linked`, `cross_cutting_data`, `no_data`, `unclear` или аварийный `unclassified`.
- `GET /api/data-schema/exports/requirements-data/{run_id}?workspace_id=...` — сохранённая после применения версия результата требований.
- `GET /api/data-schema/agent-runs/{run_id}/diagnostics?workspace_id=...` — ZIP с входом, base/working-схемой, prompt/reference-файлами, событиями, метриками, результатом и traceback. API-ключи не включаются.
- `GET /api/data-schema?workspace_id=...&preview_run_id=...` и read-endpoints схемы с тем же параметром — read-only preview.

Основной агент обычно использует один вызов загрузки контекста, до трёх записей структуры, один полный вызов прямой трассировки и одну validation. После этого выполняются две сфокусированные смысловые проверки. При технических ошибках допускается одна автоматическая попытка исправления; при конкретных смысловых issues — один основной структурированный correction-вызов и, только при оставшихся blockers, ограниченные точечные recovery-раунды без последовательного tool-loop и без повторного полного аудита.

### Решение по результату

- `POST /api/data-schema/agent-runs/{run_id}/apply` — атомарно применить preview, прошедший техническую проверку и завершённый смысловой контроль без неустранённых `must_fix`. Перед применением проверяется, что внешний файл требований не изменился после запуска.
- `POST /api/data-schema/agent-runs/{run_id}/reject` — отклонить результат.
- `POST /api/data-schema/agent-runs/{run_id}/regenerate` — повторить генерацию от базы запуска с комментарием.
- `POST /api/data-schema/agent-runs/{run_id}/cancel` — мягко отменить выполняющийся запуск.
- `GET /api/data-schema/history/latest` и `POST /api/data-schema/history/restore-latest` — просмотреть и восстановить последний snapshot.

Пока запуск выполняется или ожидает решения по preview, ручные write-endpoints возвращают `409`. Все данные одного запуска находятся в `<workspace>/.protoarchitect/data_schema_agent/runs/<run_id>/`. После apply/reject/cancel тяжёлые runtime-файлы удаляются; остаются `run.json` и `diagnostics/attempt_<n>.zip`.

## Объекты API

### Schema

Общее описание схемы данных workspace.

Поля:

```json
{
  "schema_version": "0.1",
  "title": "Логическая схема данных прототипа",
  "description": "",
  "entities": []
}
```

### Entity

Логическая сущность.

```json
{
  "id": "account",
  "title": "Счет",
  "description": "Банковский счет клиента.",
  "fields": []
}
```

### Field

Поле сущности.

```json
{
  "id": "balance",
  "title": "Баланс",
  "type": "decimal",
  "required": true,
  "description": "Текущий остаток по счету."
}
```

Для типа `dictionary` дополнительно используется `dictionary_id`:

```json
{
  "id": "currency",
  "title": "Валюта",
  "type": "dictionary",
  "required": true,
  "description": "Валюта счета.",
  "dictionary_id": "currency"
}
```

Поддерживаемые типы данных:

```text
string
text
integer
decimal
boolean
date
datetime
uuid
dictionary
json
```

### Relation

Логическая связь между сущностями.

```json
{
  "id": "customer_accounts",
  "title": "Счета клиента",
  "source_entity": "customer",
  "target_entity": "account",
  "cardinality": "one_to_many",
  "description": "Один клиент может иметь несколько счетов."
}
```

Поддерживаемые значения `cardinality`:

```text
one_to_one
one_to_many
many_to_one
many_to_many
```

### Link target

Объекты схемы данных, на которые могут ссылаться requirement/UI/API/code links:

```text
entity
field
relation
dictionary
dictionary_value
```

Форматы идентификаторов:

```text
entity            -> account
field             -> account.balance
relation          -> customer_accounts
dictionary        -> currency
dictionary_value  -> currency.RUB
```

## Автоматическое формирование ID

При создании сущности, поля и связи поле `id` можно не передавать. Backend сформирует идентификатор из `title`.

Правила формирования ID описаны в:

```text
modules/data_schema/docs/STORAGE.md
```

LLM и другие модули должны использовать `id`, который вернул API в ответе на создание объекта.

## Агрегированная выдача

### `GET /api/data-schema`

Возвращает рабочую сводку для frontend и других модулей.

Query-параметры:

| Параметр | Обязательный | Описание |
| --- | --- | --- |
| `workspace_id` | да | Идентификатор workspace. |

Пример запроса:

```text
GET /api/data-schema?workspace_id=ws_demo
```

Ответ:

```json
{
  "schema": {},
  "entities": [],
  "relations": [],
  "dictionaries": [],
  "requirement_links": [],
  "ui_links": [],
  "api_links": [],
  "code_links": [],
  "requirements": [],
  "requirement_groups": [],
  "requirement_projects": [],
  "index": {},
  "stats": {
    "entity_count": 0,
    "field_count": 0,
    "relation_count": 0,
    "requirement_link_count": 0,
    "ui_link_count": 0,
    "api_link_count": 0,
    "code_link_count": 0
  }
}
```

Назначение основных полей ответа:

| Поле | Описание |
| --- | --- |
| `schema` | Содержимое `schema.json`. |
| `entities` | Реестр сущностей с вложенным полем `details`, содержащим файл сущности. |
| `relations` | Массив связей из `relations.json`. |
| `dictionaries` | Массив справочников из `dictionaries.json`. |
| `requirement_links` | Связи с требованиями. |
| `ui_links` | Связи с UI-схемой. |
| `api_links` | Связи с API-схемой. |
| `code_links` | Связи с кодом. |
| `requirements` | Требования, динамически прочитанные по `requirements_source.json`. |
| `requirement_groups` | Группы требований из внешнего источника. |
| `requirement_projects` | Проекты требований из внешнего источника. |
| `requirements_source` | Состояние разрешения внешнего источника: path, status, hash и changed_since_sync. |
| `preview_changes` | Структурный diff выбранного preview, если задан `preview_run_id`. |
| `index` | Компактный индекс схемы. |
| `stats` | Счетчики объектов схемы. |

`GET /api/data-schema` пересобирает `index.json` перед возвратом ответа. Необязательный `preview_run_id` возвращает временную схему выбранного запуска в read-only режиме.

## Схема

### `GET /api/data-schema/schema`

Возвращает `schema.json`.

Query-параметры:

| Параметр | Обязательный | Описание |
| --- | --- | --- |
| `workspace_id` | да | Идентификатор workspace. |

Пример:

```text
GET /api/data-schema/schema?workspace_id=ws_demo
```

### `PUT /api/data-schema/schema`

Обновляет название и описание схемы.

Тело запроса:

```json
{
  "workspace_id": "ws_demo",
  "title": "Логическая схема данных прототипа",
  "description": "Описание схемы."
}
```

Поля `title` и `description` необязательны по отдельности. Переданные поля заменяют текущие значения.

Ответ:

```json
{
  "schema": {}
}
```

## Сущности

### `GET /api/data-schema/entities`

Возвращает список сущностей.

Пример:

```text
GET /api/data-schema/entities?workspace_id=ws_demo
```

Ответ:

```json
{
  "entities": [
    {
      "id": "account",
      "title": "Счет",
      "file": "entities/account.json",
      "details": {
        "id": "account",
        "title": "Счет",
        "description": "Банковский счет клиента.",
        "fields": []
      }
    }
  ]
}
```

### `GET /api/data-schema/entities/{entity_id}`

Возвращает одну сущность.

Пример:

```text
GET /api/data-schema/entities/account?workspace_id=ws_demo
```

Если сущность не найдена, возвращается `404`.

### `POST /api/data-schema/entities`

Создает сущность.

Тело запроса:

```json
{
  "workspace_id": "ws_demo",
  "title": "Счет",
  "description": "Банковский счет клиента."
}
```

Поле `id` можно передать, но основной режим — не передавать его и использовать автоматически сформированный ID из ответа.

Ответ:

```json
{
  "entity": {
    "id": "schet",
    "title": "Счет",
    "description": "Банковский счет клиента.",
    "fields": []
  }
}
```

При создании сущности обновляются:

```text
schema.json
entities/<entity_id>.json
index.json
```

### `PUT /api/data-schema/entities/{entity_id}`

Обновляет название и описание сущности.

Тело запроса:

```json
{
  "workspace_id": "ws_demo",
  "title": "Банковский счет",
  "description": "Счет клиента."
}
```

Ответ:

```json
{
  "entity": {}
}
```

Если сущность не найдена, возвращается `404`.

### `DELETE /api/data-schema/entities/{entity_id}`

Удаляет сущность.

Пример:

```text
DELETE /api/data-schema/entities/account?workspace_id=ws_demo
```

Ответ:

```json
{
  "deleted": true
}
```

Сущность нельзя удалить, если у нее есть поля или связи с другими сущностями. Сначала нужно удалить поля и связи.

## Поля сущности

### `POST /api/data-schema/entities/{entity_id}/fields`

Добавляет поле в сущность.

Тело запроса:

```json
{
  "workspace_id": "ws_demo",
  "title": "Баланс",
  "type": "decimal",
  "required": true,
  "description": "Текущий остаток по счету."
}
```

Для поля типа `dictionary`:

```json
{
  "workspace_id": "ws_demo",
  "title": "Валюта",
  "type": "dictionary",
  "required": true,
  "description": "Валюта счета.",
  "dictionary_id": "currency"
}
```

Поле `id` можно не передавать. Backend сформирует идентификатор автоматически из `title` внутри выбранной сущности.

Ответ:

```json
{
  "field": {
    "id": "balans",
    "title": "Баланс",
    "type": "decimal",
    "required": true,
    "description": "Текущий остаток по счету."
  }
}
```

Если сущность не найдена, тип данных не поддерживается или поле не может быть создано, возвращается `400`.

### `PUT /api/data-schema/entities/{entity_id}/fields/{field_id}`

Обновляет поле сущности.

Тело запроса:

```json
{
  "workspace_id": "ws_demo",
  "title": "Текущий баланс",
  "type": "decimal",
  "required": true,
  "description": "Текущий остаток по счету.",
  "dictionary_id": null
}
```

Ответ:

```json
{
  "field": {}
}
```

Если поле меняется на тип, отличный от `dictionary`, `dictionary_id` удаляется из поля.

### `DELETE /api/data-schema/entities/{entity_id}/fields/{field_id}`

Удаляет поле из сущности.

Пример:

```text
DELETE /api/data-schema/entities/account/fields/balance?workspace_id=ws_demo
```

Ответ:

```json
{
  "deleted": true
}
```

Текущая реализация удаляет поле из файла сущности. Связи, которые ссылались на это поле, автоматически не очищаются.

## Связи между сущностями

### `GET /api/data-schema/relations`

Возвращает содержимое `relations.json`.

Пример:

```text
GET /api/data-schema/relations?workspace_id=ws_demo
```

Ответ:

```json
{
  "relations": []
}
```

### `POST /api/data-schema/relations`

Создает связь между сущностями.

Тело запроса:

```json
{
  "workspace_id": "ws_demo",
  "title": "Счета клиента",
  "source_entity": "customer",
  "target_entity": "account",
  "cardinality": "one_to_many",
  "description": "Один клиент может иметь несколько счетов."
}
```

Поле `id` можно не передавать. Backend сформирует идентификатор автоматически из `title`.

Ответ:

```json
{
  "relation": {
    "id": "scheta_klienta",
    "title": "Счета клиента",
    "source_entity": "customer",
    "target_entity": "account",
    "cardinality": "one_to_many",
    "description": "Один клиент может иметь несколько счетов."
  }
}
```

Если указанная сущность не найдена или кардинальность не поддерживается, возвращается `400`.

### `PUT /api/data-schema/relations/{relation_id}`

Обновляет связь между сущностями.

Тело запроса:

```json
{
  "workspace_id": "ws_demo",
  "title": "Счета клиента",
  "source_entity": "customer",
  "target_entity": "account",
  "cardinality": "one_to_many",
  "description": "Один клиент может иметь несколько счетов."
}
```

Ответ:

```json
{
  "relation": {}
}
```

### `DELETE /api/data-schema/relations/{relation_id}`

Удаляет связь между сущностями.

Пример:

```text
DELETE /api/data-schema/relations/customer_accounts?workspace_id=ws_demo
```

Ответ:

```json
{
  "deleted": true
}
```

## Требования

### `GET /api/data-schema/requirements`

Возвращает требования, динамически разрешенные по `requirements_source.json`, и не изменяет внешний файл.

Пример:

```text
GET /api/data-schema/requirements?workspace_id=ws_demo
```

Ответ:

```json
{
  "projects": [],
  "groups": [],
  "requirements": []
}
```

Структура требований не является частью схемы данных. Связи с требованиями используют поле `requirements[].id`.

## Связи с требованиями

### `POST /api/data-schema/requirement-links`

Создает связь требования с объектом схемы данных.

Тело запроса:

```json
{
  "workspace_id": "ws_demo",
  "requirement_id": "REQ-ACCOUNTS-LIST",
  "target_type": "field",
  "target_id": "account.balance",
  "relation": "defines",
  "implementation_status": "planned"
}
```

Ответ:

```json
{
  "link": {
    "id": "req_data_link.1a2b3c4d5e",
    "requirement_id": "REQ-ACCOUNTS-LIST",
    "target_type": "field",
    "target_id": "account.balance",
    "relation": "defines",
    "implementation_status": "planned"
  }
}
```

`id` ссылки формируется backend автоматически.

### `DELETE /api/data-schema/requirement-links/{link_id}`

Удаляет связь с требованием.

Пример:

```text
DELETE /api/data-schema/requirement-links/req_data_link.1a2b3c4d5e?workspace_id=ws_demo
```

Ответ:

```json
{
  "deleted": true
}
```

## Связи с UI-схемой

### `POST /api/data-schema/ui-links`

Создает связь объекта схемы данных с объектом UI-схемы.

Тело запроса:

```json
{
  "workspace_id": "ws_demo",
  "data_target_type": "field",
  "data_target_id": "account.balance",
  "external_target_type": "ui_element",
  "external_target_id": "accounts.list.table.column.balance",
  "relation": "displayed_by"
}
```

Ответ:

```json
{
  "link": {
    "id": "ui_schema_data_link.1a2b3c4d5e",
    "data_target_type": "field",
    "data_target_id": "account.balance",
    "external_schema": "ui_schema",
    "external_target_type": "ui_element",
    "external_target_id": "accounts.list.table.column.balance",
    "relation": "displayed_by"
  }
}
```

`external_schema` устанавливается backend автоматически в значение `ui_schema`.

Frontend выбирает UI-элемент через API модуля `ui_schema`. Другие модули могут передавать уже известный `external_target_id`.

### `DELETE /api/data-schema/ui-links/{link_id}`

Удаляет связь с UI-схемой.

Пример:

```text
DELETE /api/data-schema/ui-links/ui_schema_data_link.1a2b3c4d5e?workspace_id=ws_demo
```

Ответ:

```json
{
  "deleted": true
}
```

## Связи с API-схемой

### `POST /api/data-schema/api-links`

Создает связь объекта схемы данных с объектом API-схемы или будущего описания API.

Тело запроса:

```json
{
  "workspace_id": "ws_demo",
  "data_target_type": "entity",
  "data_target_id": "account",
  "external_target_type": "resource",
  "external_target_id": "accounts",
  "relation": "exposed_by"
}
```

Ответ:

```json
{
  "link": {
    "id": "api_schema_data_link.1a2b3c4d5e",
    "data_target_type": "entity",
    "data_target_id": "account",
    "external_schema": "api_schema",
    "external_target_type": "resource",
    "external_target_id": "accounts",
    "relation": "exposed_by"
  }
}
```

`external_schema` устанавливается backend автоматически в значение `api_schema`.

### `DELETE /api/data-schema/api-links/{link_id}`

Удаляет связь с API-схемой.

Пример:

```text
DELETE /api/data-schema/api-links/api_schema_data_link.1a2b3c4d5e?workspace_id=ws_demo
```

Ответ:

```json
{
  "deleted": true
}
```

## Связи с кодом

### `POST /api/data-schema/code-links`

Создает связь объекта схемы данных с файлом кода.

Тело запроса:

```json
{
  "workspace_id": "ws_demo",
  "target_type": "entity",
  "target_id": "account",
  "code_type": "model",
  "path": "prototype/backend/models/account.py",
  "status": "planned"
}
```

Ответ:

```json
{
  "link": {
    "id": "code_data_link.1a2b3c4d5e",
    "target_type": "entity",
    "target_id": "account",
    "code_type": "model",
    "path": "prototype/backend/models/account.py",
    "status": "planned"
  }
}
```

Текущий UI модуля отображает code links, но не использует ручное добавление таких ссылок как основной сценарий.

### `DELETE /api/data-schema/code-links/{link_id}`

Удаляет связь с кодом.

Пример:

```text
DELETE /api/data-schema/code-links/code_data_link.1a2b3c4d5e?workspace_id=ws_demo
```

Ответ:

```json
{
  "deleted": true
}

```

## Ошибки

Типовые статусы:

| Статус | Когда возникает |
| --- | --- |
| `400` | Некорректные данные, неподдерживаемый тип поля, неподдерживаемая кардинальность, попытка удалить объект с зависимостями. |
| `403` | Пользователь не имеет доступа к workspace. |
| `404` | Запрошенная сущность, поле или связь не найдены. |

Текст ошибки возвращается в поле `detail`.
