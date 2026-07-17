# Создание нового модуля

Документ описывает минимальный порядок добавления нового подключаемого модуля в проект.

В примерах используется модуль `example`.

## 1. Выбрать `module_id`

Требования:

- нижний регистр;
- латиница, цифры, `_`;
- без пробелов;
- совпадает с именами папок модуля.

Пример:

```text
example
```

## 2. Создать каталог описания модуля

```text
modules/example/
  module.yaml
  config.yaml
  api.openapi.yaml
  interop.yaml
  README.md
  init/
```

`init/` нужен только если модуль должен создавать начальные файлы в новом workspace.

## 3. Создать `module.yaml`

Пример модуля с UI, API и init-механизмом:

```yaml
id: "example"
name: "Example Module"
version: "0.1.0"

frontend:
  base_path: "modules/example"
  pages:
    - id: "main"
      title: "Example"
      path: "index.html"
      menu:
        show: true
        title: "Example"
        icon: "E"
        order: 100
      params:
        - "workspace_id"

backend:
  router: "backend.modules.example.api:router"
  api_prefix: "/api/example"

workspace:
  folder: "example"
  init:
    files: "modules/example/init"
    python_hook: "backend.modules.example.init_workspace:init_workspace"

docs:
  api: "modules/example/api.openapi.yaml"
  interop: "modules/example/interop.yaml"
```

Поля `menu`:

- `show: true` — страница попадает в левое меню;
- `show: false` — страница зарегистрирована, но не показывается в левом меню;
- `title` — название пункта меню;
- `icon` — короткая иконка или символ;
- `order` — порядок пункта меню.

Модуль без пункта меню:

```yaml
menu:
  show: false
```

Поля `workspace`:

- `folder` — папка модуля внутри workspace;
- `init.files` — файл или папка, копируемые в `data/workspaces/<workspace_id>/<folder>/`;
- `init.python_hook` — опциональная Python-функция, вызываемая при создании workspace.

Если init не нужен, блок `workspace.init` можно не указывать.

## 4. Создать `config.yaml`

Файл:

```text
modules/example/config.yaml
```

Пример:

```yaml
workspace_folder: "example"
files:
  state: "state.json"
```

Базовое ядро не валидирует этот файл. Модуль сам определяет параметры и читает их через:

```python
state.config.read_module_runtime_config("example")
```

UI может получить конфиг через:

```text
GET /api/config/modules/example
```

## 5. Добавить init-файлы workspace

Если модулю нужны начальные файлы при создании workspace, положить их в:

```text
modules/example/init/
```

Пример:

```text
modules/example/init/state.json
```

При создании workspace файл будет скопирован в:

```text
data/workspaces/<workspace_id>/example/state.json
```

## 6. Добавить Python init hook

Если модулю нужна программная инициализация, создать файл:

```text
backend/modules/example/init_workspace.py
```

Пример:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def init_workspace(
    *,
    username: str,
    workspace_id: str,
    workspace: dict[str, Any],
    workspace_path: Path,
    module: dict[str, Any],
    module_path: Path,
    **_kwargs: Any,
) -> None:
    data = {
        "created_by": username,
        "workspace_id": workspace_id,
        "workspace_name": workspace.get("name", ""),
    }
    (module_path / "generated.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

Зарегистрировать hook в `module.yaml`:

```yaml
workspace:
  init:
    python_hook: "backend.modules.example.init_workspace:init_workspace"
```

Hook выполняется после копирования `workspace.init.files`.

## 7. Зарегистрировать модуль в `config/modules.yaml`

Добавить запись:

```yaml
modules:
  - id: "example"
    enabled: true
    manifest: "modules/example/module.yaml"
```

После изменения списка модулей приложение нужно перезапустить.

## 8. Создать backend-модуль

Создать папку:

```text
backend/modules/example/
```

Рекомендуемая структура:

```text
backend/modules/example/
  __init__.py
  api.py
  schemas.py
  service.py
  files.py
  init_workspace.py
  API.md
```

### `api.py`

Пример:

```python
from fastapi import APIRouter, Depends

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state
from backend.modules.example.service import read_state

router = APIRouter(tags=["example"])


@router.get("/state")
def get_state_data(
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    workspace_id = user.get("current_workspace_id")
    return read_state(state, workspace_id)
```

`api.py` не указывает полный API-префикс. Префикс задается в `module.yaml`:

```yaml
backend:
  api_prefix: "/api/example"
```

Итоговый endpoint:

```text
GET /api/example/state
```

### `API.md`

Краткое описание API рядом с backend-кодом.

Рекомендуемый формат:

```md
# Example Backend API

## GET /api/example/state

Purpose:
Returns module state from current workspace.

Reads:
- example/state.json

Writes:
- none
```

## 9. Создать frontend-модуль

Создать папку:

```text
frontend/modules/example/
```

Рекомендуемая структура:

```text
frontend/modules/example/
  index.html
  css/
    module.css
  js/
    main.js
    api.js
    render.js
    events.js
```

### `index.html`

Пример:

```html
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>Example</title>
  <link rel="stylesheet" href="/base/css/tokens.css" />
  <link rel="stylesheet" href="/base/css/layout.css" />
  <link rel="stylesheet" href="/base/css/components.css" />
  <link rel="stylesheet" href="/modules/example/css/module.css" />
</head>
<body>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="sidebar-title">Модули</div>
      <nav class="sidebar-nav" data-sidebar></nav>
    </aside>
    <main class="main-panel">
      <header class="topbar" data-topbar></header>
      <section class="content">
        <h1>Example</h1>
        <div id="content"></div>
      </section>
    </main>
  </div>
  <script type="module" src="/modules/example/js/main.js"></script>
</body>
</html>
```

### `main.js`

Пример:

```js
import { apiFetch } from "/base/js/api.js";
import { getContext } from "/base/js/context.js";
import { initLayout } from "/base/js/layout.js";

await initLayout("example.main");
const context = await getContext();
const data = await apiFetch("/api/example/state");
document.querySelector("#content").textContent = JSON.stringify(data, null, 2);
```

## 10. Описать API в `api.openapi.yaml`

Файл:

```text
modules/example/api.openapi.yaml
```

Минимальный пример:

```yaml
openapi: 3.1.0
info:
  title: Example API
  version: 0.1.0
paths:
  /api/example/state:
    get:
      summary: Get example state
      responses:
        "200":
          description: Example state
          content:
            application/json:
              schema:
                type: object
```

Правила:

- документируется полный итоговый API path, включая `backend.api_prefix`;
- каждый endpoint модуля должен быть отражен в OpenAPI;
- request body, query parameters и response schema описываются явно;
- OpenAPI хранится рядом с manifest модуля;
- файл доступен через `GET /api/docs/openapi/<module_id>`.

## 11. Описать сопряжение в `interop.yaml`

Файл:

```text
modules/example/interop.yaml
```

Минимальный пример:

```yaml
module: "example"

provides:
  pages:
    - id: "example.main"
      path: "modules/example/index.html"
      params:
        - "workspace_id"

  api:
    - method: "GET"
      path: "/api/example/state"
      description: "Returns example state"

  workspace_files:
    - path: "example/state.json"
      description: "Example state file"

consumes:
  pages: []
  api: []
  workspace_files: []
```

Правила:

- `provides.pages` описывает страницы, на которые могут перейти другие модули;
- `provides.api` описывает API, которое могут использовать другие модули;
- `provides.workspace_files` описывает файлы, которые модуль создает или поддерживает;
- `consumes` описывает зависимости от страниц, API или файлов других модулей;
- файл доступен через `GET /api/docs/interop/<module_id>`.

## 12. Добавить свободную документацию модуля

Файл:

```text
modules/example/README.md
```

Содержит:

- назначение модуля;
- основные страницы;
- основные API;
- основные файлы workspace;
- особенности настройки.

## 13. Создать данные модуля в существующих workspace

Init-механизм выполняется только при создании нового workspace.

Для уже существующих workspace при необходимости создать папку вручную:

```text
data/workspaces/<workspace_id>/example/
```

Или добавить миграционный/служебный API в сам модуль.

## 14. Перезапустить приложение

```bash
python manage.py run
```

## 15. Проверить модуль

Проверить через браузер:

```text
/modules/example/index.html
```

Проверить API:

```text
GET /api/example/state
```

Проверить регистрацию страниц:

```text
GET /api/modules/pages
```

Проверить левое меню:

```text
GET /api/modules/menu
```

Проверить документацию:

```text
GET /api/docs/openapi/example
GET /api/docs/interop/example
```

## 16. Правила размера файлов

- `api.py` содержит только маршруты.
- `service.py` содержит операции модуля.
- `files.py` содержит работу с файлами.
- JS делится на `main.js`, `api.js`, `render.js`, `events.js` и другие малые файлы.
- HTML не содержит крупный inline JS.
- CSS модуля хранится отдельно от HTML.
