# ProtoArchitect

Костяк модульного web-приложения: JS UI + Python/FastAPI backend + JSON/YAML-файлы в workspace.

## Состав текущей версии

- локальная авторизация пользователей;
- обычный и системный пользователь;
- открытие и создание workspace;
- автоматическое создание `workspace_id`;
- инициализация workspace для каждого подключенного модуля;
- верхнее системное меню;
- левое меню подключаемых модулей;
- подключение модулей через `config/modules.yaml` и `modules/<module_id>/module.yaml`;
- общий session/workspace/module context;
- отдельные frontend/backend части модулей;
- runtime-конфиг модуля в `modules/<module_id>/config.yaml`;
- машинно-читаемая OpenAPI/interop-документация модулей;
- запуск без Docker на Windows/Linux.

## Документы

- [Архитектура](docs/ARCHITECTURE.md)
- [Создание нового модуля](docs/CREATING_MODULES.md)
- [Контракт модуля](docs/MODULE_CONTRACT.md)

## Демо-пользователи

Обычный пользователь:

```text
login: demo
password: demo
```

Системный пользователь:

```text
login: admin
password: admin
```

## Запуск

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py run
```

Linux / Ubuntu WSL:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py run
```

Открыть приложение:

```text
http://127.0.0.1:8000
```

## Команды

Запуск приложения:

```bash
python manage.py run
```

Создание пользователя:

```bash
python manage.py create-user alice --display-name "Alice" --password "secret"
```

Создание системного пользователя:

```bash
python manage.py create-user admin2 --display-name "Admin 2" --password "secret" --admin
```

Создание workspace для пользователя:

```bash
python manage.py create-workspace alice "Alice Workspace" --description "Workspace comment"
```

ID workspace создается автоматически. После создания через CLI workspace становится текущим для пользователя.

## Создание git-репозитория

```bash
git init
git add .
git commit -m "Initial ProtoArchitect skeleton"
```

`.gitignore` уже добавлен. Runtime workspace, создаваемые пользователями, игнорируются, демо-workspace `data/workspaces/ws_demo/` оставлен в проекте.

## Основные конфигурационные файлы

### `config/app.yaml`

Главный runtime-конфиг приложения.

Параметры:

- `app.name` — имя приложения в UI и FastAPI metadata.
- `app.config_version` — версия формата конфигурации.
- `server.host` — адрес запуска uvicorn.
- `server.port` — порт запуска uvicorn.
- `paths.frontend_dir` — каталог frontend-файлов.
- `paths.modules_dir` — каталог manifest/config/docs модулей.
- `paths.config_dir` — каталог общей runtime-конфигурации.
- `paths.users_dir` — каталог файлов пользователей.
- `paths.module_list` — файл списка подключенных модулей.
- `paths.data_dir` — каталог рабочих данных.
- `paths.workspace_root` — каталог workspace.
- `ui.default_page` — стартовая страница.
- `ui.login_page` — страница логина.
- `ui.root_css` — базовая CSS-точка входа.
- `auth.session_cookie_name` — имя cookie сессии.
- `auth.session_ttl_minutes` — срок жизни сессии.
- `auth.secret_key` — ключ подписи cookie.
- `history.enabled` — включает helper-ы истории.
- `history.provider` — провайдер истории.
- `history.auto_commit` — флаг будущей автозаписи изменений в историю.

### `config/modules.yaml`

Список подключенных модулей.

```yaml
modules:
  - id: "demo_hello"
    enabled: true
    manifest: "modules/demo_hello/module.yaml"
```

Параметры:

- `id` — идентификатор модуля.
- `enabled` — подключать модуль при старте приложения.
- `manifest` — путь к manifest-файлу модуля относительно корня проекта.

### `config/users/<username>.yaml`

Файл пользователя.

Параметры:

- `username` — логин.
- `display_name` — имя в UI.
- `is_admin` — доступ к системному администрированию.
- `password_hash` — хеш пароля.
- `current_workspace_id` — активный workspace.
- `settings` — пользовательские настройки.
  - `settings.llm.provider` — провайдер LLM-соединения: `ollama-cloud`, `ollama`, `lmstudio`, `openai`, `anthropic`, `gemini`, `openrouter`, `opencode`, `openai-compatible`.
  - `settings.llm.model` — имя модели LLM.
  - `settings.llm.base_url` — опциональный URL совместимого сервиса.
  - `settings.llm.api_key` — опциональный ключ API.
- `workspaces.owned` — workspace пользователя.
- `workspaces.shared` — workspace, доступные пользователю.

### `modules/<module_id>/module.yaml`

Manifest модуля.

Параметры:

- `id` — идентификатор модуля.
- `name` — отображаемое имя модуля.
- `version` — версия модуля.
- `frontend.base_path` — путь frontend-модуля относительно web-корня.
- `frontend.pages[].id` — ID страницы внутри модуля.
- `frontend.pages[].title` — заголовок страницы.
- `frontend.pages[].path` — HTML-файл страницы относительно `frontend.base_path`.
- `frontend.pages[].menu.show` — показывать страницу в левом меню.
- `frontend.pages[].menu.title` — название пункта меню.
- `frontend.pages[].menu.icon` — иконка пункта меню.
- `frontend.pages[].menu.order` — порядок пункта меню.
- `frontend.pages[].params` — параметры, которые страница ожидает в URL.
- `backend.router` — import path FastAPI router.
- `backend.api_prefix` — API-префикс модуля.
- `workspace.folder` — папка модуля внутри workspace.
- `workspace.init.files` — папка или файл, копируемый в папку модуля при создании workspace.
- `workspace.init.python_hook` — опциональный Python hook, выполняемый при создании workspace.
- `docs.api` — путь к OpenAPI YAML модуля.
- `docs.interop` — путь к interop YAML модуля.

### `modules/<module_id>/config.yaml`

Runtime-конфиг конкретного модуля. Ядро читает файл и отдает его через API, но не валидирует бизнес-параметры модуля.

### `data/workspaces/<workspace_id>/workspace.yaml`

Metadata workspace.

Параметры:

- `id` — ID workspace.
- `name` — название.
- `owner` — владелец.
- `created_at` — дата создания.
- `description` — комментарий/описание.
