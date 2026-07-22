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
| `requirements` | Список требований из локального `requirements.json`, если он используется. |
| `requirement_groups` | Группы требований из локального `requirements.json`, если они есть. |
| `requirement_projects` | Проекты требований из локального `requirements.json`, если они есть. |
| `index` | Компактный индекс схемы. |
| `stats` | Счетчики объектов схемы. |

`GET /api/data-schema` пересобирает `index.json` перед возвратом ответа.

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

Возвращает локальный файл требований модуля, если он есть.

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
