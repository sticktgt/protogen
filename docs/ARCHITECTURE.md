# Архитектура

## Назначение

Проект является костяком модульного web-приложения.

Состав приложения:

- JS UI без frontend-сборщика;
- Python/FastAPI backend;
- JSON/YAML-файлы для настроек и данных;
- workspace как папка с рабочими данными;
- подключаемые модули с отдельными frontend/backend частями;
- конфигурационная регистрация модулей.

## Роль ядра

Ядро выполняет следующие функции:

- авторизация пользователя;
- хранение текущего пользователя в сессии;
- создание workspace;
- открытие доступного workspace;
- хранение текущего workspace пользователя;
- чтение списка подключенных модулей;
- подключение backend-router модулей при старте;
- отдача базового UI;
- отдача static-файлов frontend-модулей;
- построение левого меню из manifest-файлов модулей;
- выдача общего session/workspace/module контекста;
- выдача OpenAPI/interop-документации модулей;
- выполнение init-механизма модулей при создании workspace;
- минимальное администрирование для системного пользователя.

Ядро не выполняет следующие функции:

- бизнес-валидация конфигов модулей;
- управление LLM-агентами модулей;
- проверка прав на API конкретных модулей;
- проверка прав на отдельные папки внутри workspace;
- fallback/merge логика настроек модулей;
- интерпретация бизнес-данных модулей.

## Структура проекта

```text
protoarchitect/
  backend/
    app/
      core/
      main.py
      state.py
    modules/

  frontend/
    base/
    modules/

  modules/
    demo_hello/
    demo_links/
    demo_hidden/

  config/
    app.yaml
    modules.yaml
    users/

  data/
    workspaces/

  docs/

  manage.py
  requirements.txt
  pyproject.toml
  README.md
```

## Папки и ключевые файлы

### `backend/app/main.py`

Точка создания FastAPI-приложения.

Функции файла:

- загрузка `config/app.yaml`;
- создание core-сервисов;
- регистрация core API;
- регистрация backend-router модулей;
- подключение static-папок frontend;
- выдача стартовой страницы и страницы логина.

### `backend/app/state.py`

Общий контейнер runtime-сервисов приложения.

Используется core API и backend-модулями для доступа к:

- конфигурации;
- пользователям;
- workspace;
- каталогу модулей.

### `backend/app/core/`

Тонкое ядро backend-приложения.

Основные подпапки:

- `auth/` — логин, logout, сессия, текущий пользователь;
- `admin/` — минимальное системное администрирование;
- `users/` — чтение/запись пользователей и пользовательских настроек;
- `workspaces/` — создание, открытие и получение пути workspace;
- `config/` — чтение YAML-конфигов;
- `modules/` — загрузка manifest-файлов, меню, страницы, документация модулей;
- `history/` — заготовка helper-ов истории.

### `backend/modules/`

Python-код backend-модулей.

Один модуль — одна подпапка:

```text
backend/modules/<module_id>/
  api.py
  schemas.py
  service.py
  files.py
  API.md
```

Назначение:

- `api.py` — FastAPI routes модуля;
- `schemas.py` — схемы запросов/ответов;
- `service.py` — операции модуля;
- `files.py` — работа с файлами workspace;
- `API.md` — краткое описание API рядом с backend-кодом;
- дополнительные файлы делятся по функционалу.

### `frontend/base/`

Базовый UI приложения.

Ключевые страницы:

- `login.html` — вход;
- `index.html` — стартовая страница после входа;
- `workspace-open.html` — открытие доступного workspace;
- `workspace-create.html` — создание нового workspace;
- `workspaces.html` — совместимая страница-ссылка на открытие/создание;
- `settings.html` — пользовательские настройки; форма редактирует фиксированные разделы настроек, в текущей версии это параметры LLM-соединения: `provider`, `model`, `base_url`, `api_key`;
- `admin.html` — системное администрирование.

Ключевые JS-файлы:

- `js/api.js` — HTTP helper;
- `js/context.js` — session/workspace/module context;
- `js/navigation.js` — переходы по зарегистрированным страницам;
- `js/layout.js` — верхняя панель и левое меню;
- `js/ui.js` — общие UI helper-ы.

Ключевые CSS-файлы:

- `css/tokens.css` — переменные, цвета, базовые значения;
- `css/layout.css` — общий layout;
- `css/components.css` — кнопки, карточки, формы и базовые компоненты.

### `frontend/modules/`

Frontend-страницы подключаемых модулей.

Один модуль — одна подпапка:

```text
frontend/modules/<module_id>/
  index.html
  js/
  css/
```

Страницы используют общий CSS/JS из `frontend/base/` и могут добавлять свои файлы.

### `modules/`

Каталог описания модулей.

Один модуль — одна подпапка:

```text
modules/<module_id>/
  module.yaml
  config.yaml
  api.openapi.yaml
  interop.yaml
  README.md
  init/
```

Назначение:

- `module.yaml` — manifest модуля;
- `config.yaml` — runtime-конфиг модуля;
- `api.openapi.yaml` — машинно-читаемое описание API модуля;
- `interop.yaml` — машинно-читаемое описание сопряжения с другими модулями;
- `README.md` — свободное описание модуля;
- `init/` — файлы, копируемые в папку модуля при создании workspace.

### `config/app.yaml`

Главный runtime-конфиг приложения.

Содержит:

- имя приложения;
- параметры запуска сервера;
- относительные пути;
- параметры базового UI;
- параметры сессии;
- настройки history-helper.

### `config/modules.yaml`

Список подключенных модулей.

Содержит:

- `id` модуля;
- признак `enabled`;
- путь к `module.yaml`.

### `config/users/`

Файлы пользователей.

Один пользователь — один YAML-файл.

Содержит:

- логин;
- отображаемое имя;
- признак системного пользователя;
- хеш пароля;
- текущий workspace;
- пользовательские настройки;
- список owned/shared workspace.

### `data/workspaces/`

Рабочие данные workspace.

Один workspace — одна подпапка:

```text
data/workspaces/<workspace_id>/
  workspace.yaml
  settings.yaml
  <module_id>/
```

`workspace.yaml` содержит:

- `id`;
- `name`;
- `owner`;
- `created_at`;
- `description`.

### `docs/`

Общая документация проекта.

Ключевые документы:

- `ARCHITECTURE.md` — архитектура и структура проекта;
- `CREATING_MODULES.md` — инструкция по созданию нового модуля;
- `MODULE_CONTRACT.md` — краткий контракт модуля.

### `manage.py`

Кроссплатформенный CLI.

Команды:

- запуск приложения;
- создание пользователя;
- создание системного пользователя;
- создание workspace.

### `requirements.txt`

Python-зависимости приложения.

### `pyproject.toml`

Минимальная метаинформация Python-проекта.

## UI-соглашения

- Верхняя панель содержит системные действия.
- Верхняя панель не содержит пункты бизнес-модулей.
- Системные действия: открыть workspace, создать workspace, настройки, выход.
- Левое меню содержит страницы модулей с `menu.show: true`.
- Страницы модулей без пункта меню доступны через `App.navigateToPage(pageId, params)` или прямую ссылку.
- Страницы модулей подключают общий CSS из `/base/css/*`.
- Страницы модулей могут подключать собственный CSS.
- JS модулей использует helper-ы из `/base/js/*`.
- Состав меню не хардкодится в JS.
- Крупные JS/Python-файлы делятся на файлы по функционалу.

## Принципы

- Ядро остается тонким.
- Состав модулей задается конфигурацией.
- Базовое меню модулей строится из manifest-файлов.
- Настройки поведения модулей не хранятся в JS/Python-коде.
- Модуль сам отвечает за свой API, конфиг, данные и агентов.
- Рабочие данные лежат внутри workspace.
- Один пользователь работает с одним активным workspace в текущей сессии.
- Доступ к workspace определяется списками `owned` и `shared` в файле пользователя.
- Ядро не проверяет права на отдельные папки внутри workspace.
- Docker не является обязательным для разработки.
- Приложение запускается на Windows и Linux.

## Правила путей

### Общие правила

- Все проектные пути в конфигурации относительные.
- Пути разрешаются относительно корня проекта.
- Пути внутри workspace относительные.
- URL страниц модулей относительные к web-корню приложения.
- API-префиксы модулей относительные к корню приложения.

### URL страниц

Frontend-страницы модулей задаются через `frontend.base_path` и `frontend.pages[].path` в `module.yaml`.

Пример:

```yaml
frontend:
  base_path: "modules/demo_hello"
  pages:
    - path: "index.html"
```

Итоговый URL:

```text
/modules/demo_hello/index.html
```

### API

API-префикс модуля задается в `backend.api_prefix`.

Пример:

```yaml
backend:
  api_prefix: "/api/hello"
```

Endpoint внутри `api.py`:

```text
/message
```

Итоговый API path:

```text
/api/hello/message
```

### Project paths

Пути в `config/app.yaml` задаются относительно корня проекта.

Пример:

```yaml
workspace_root: "data/workspaces"
```

### Workspace paths

Рабочие файлы модуля задаются относительно корня workspace.

Пример:

```text
demo_hello/message.json
```

Рекомендуемая папка данных модуля внутри workspace:

```text
<module_id>/...
```

Модуль может читать другие папки того же workspace, если это нужно для сопряжения модулей.

## Core API

Core API ядра:

```text
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
GET  /api/session/context
GET  /api/users/me/settings
PUT  /api/users/me/settings
GET  /api/workspaces
POST /api/workspaces
POST /api/workspaces/{workspace_id}/open
GET  /api/workspaces/{workspace_id}/path
GET  /api/modules
GET  /api/modules/menu
GET  /api/modules/pages
GET  /api/config/app
GET  /api/config/modules/{module_id}
GET  /api/docs/openapi/{module_id}
GET  /api/docs/interop/{module_id}
GET  /api/admin/users
POST /api/admin/users
GET  /api/admin/app-config
PUT  /api/admin/app-config
```

API подключаемых модулей описывается отдельно в `modules/<module_id>/api.openapi.yaml` и рядом с backend-кодом модуля в `backend/modules/<module_id>/API.md`.

## Инициализация workspace для модулей

При создании нового workspace ядро выполняет init для каждого включенного модуля.

Поддерживаются два механизма:

1. `workspace.init.files` — копирование папки или файла в папку модуля внутри workspace.
2. `workspace.init.python_hook` — вызов Python-функции модуля.

Пример:

```yaml
workspace:
  folder: "demo_links"
  init:
    files: "modules/demo_links/init"
    python_hook: "backend.modules.demo_links.init_workspace:init_workspace"
```

Порядок выполнения:

1. создается папка workspace;
2. создаются `workspace.yaml` и `settings.yaml`;
3. создается папка каждого включенного модуля;
4. копируются init-файлы модуля;
5. вызывается Python hook модуля, если он указан;
6. workspace добавляется пользователю и становится текущим.
