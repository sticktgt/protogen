# ProtoArchitect: инструкция для разработки нового модуля

Документ предназначен для передачи в LLM-модель, которая должна разработать новый модуль для **ProtoArchitect** или встроить существующее приложение `HTML + JS + Python REST API` в виде модуля. Описаны только правила интеграции с общим приложением; бизнес-логика конкретного модуля сюда не входит.

---

## 1. Краткая модель приложения

ProtoArchitect — модульное web-приложение:

- backend: одно FastAPI-приложение;
- frontend: независимые HTML-страницы с нативным JS, без обязательной сборки;
- данные хранятся в `JSON`/`YAML` внутри workspace;
- пользователь работает с одним текущим workspace, но может переключаться между доступными;
- ядро авторизует пользователя, создает/открывает workspace, читает список модулей, строит меню, отдает страницы и дает helper-ы;
- модуль сам отвечает за свой API, UI, конфиг, данные, агентов и внутренние правила.

Ядро не валидирует бизнес-конфиг модуля, не управляет агентами модуля и не проверяет права внутри workspace. Модуль должен сам корректно работать с файлами своего workspace.

---

## 2. Папки, важные для нового модуля

```text
protoarchitect/
  backend/app/core/              # ядро: auth, users, workspaces, config, module catalog
  backend/modules/<module_id>/   # Python backend-код модуля

  frontend/base/                 # общий UI, CSS и JS helper-ы ядра
  frontend/modules/<module_id>/  # HTML/JS/CSS модуля

  modules/<module_id>/           # manifest, runtime-конфиг, OpenAPI, interop, init-файлы

  config/app.yaml                # настройки приложения
  config/modules.yaml            # список включенных модулей
  config/users/<username>.yaml   # пользователи и пользовательские настройки

  data/workspaces/<workspace_id>/ # данные конкретного workspace
```

Для нового модуля обычно создаются:

```text
backend/modules/<module_id>/
frontend/modules/<module_id>/
modules/<module_id>/
```

и добавляется запись в `config/modules.yaml`.

---

## 3. Правила для `module_id`

`module_id` — технический идентификатор модуля. Используй латинские буквы в нижнем регистре, цифры и `_`. Не используй пробелы и русские буквы.

Примеры: `requirements_editor`, `schema_mapper`, `llm_chat`, `data_sources`.

`module_id` может встречаться в коде как идентификатор интеграции. Но бизнес-настройки, пункты меню, модели LLM и пути файлов, которые должны настраиваться, не нужно хардкодить в JS/Python.

---

## 4. Минимальный состав модуля

```text
modules/<module_id>/
  module.yaml           # manifest модуля
  config.yaml           # runtime-конфиг модуля; ядро не валидирует его бизнес-поля
  api.openapi.yaml      # машинно-читаемое описание API модуля
  interop.yaml          # машинно-читаемое описание связей с другими модулями
  README.md             # краткое описание модуля
  init/                 # опционально: файлы для нового workspace

backend/modules/<module_id>/
  __init__.py
  api.py                # APIRouter модуля
  schemas.py            # Pydantic-схемы, если нужны
  service.py            # бизнес-операции
  files.py              # работа с файлами, если нужна
  API.md                # краткое описание backend API для разработчика UI

frontend/modules/<module_id>/
  index.html
  css/module.css
  js/main.js
  js/api.js             # желательно отделить вызовы API
  js/render.js          # опционально
  js/events.js          # опционально
  js/state.js           # опционально
```

Не делай большие JS/Python-файлы. Разделяй код по функциям: маршруты, схемы, сервисы, файлы, рендеринг, события, состояние.

---

## 5. Подключение модуля в `config/modules.yaml`

```yaml
modules:
  - id: "my_module"
    enabled: true
    manifest: "modules/my_module/module.yaml"
```

`enabled: false` отключает модуль. После изменения списка модулей приложение нужно перезапустить.

---

## 6. Manifest модуля: `modules/<module_id>/module.yaml`

Пример:

```yaml
id: "my_module"
name: "My Module"
version: "0.1.0"

frontend:
  base_path: "modules/my_module"
  pages:
    - id: "main"
      title: "My Module"
      path: "index.html"
      menu:
        show: true
        title: "My Module"
        icon: "◎"
        order: 100
      params:
        - "workspace_id"

backend:
  router: "backend.modules.my_module.api:router"
  api_prefix: "/api/my-module"

workspace:
  folder: "my_module"
  init:
    files: "modules/my_module/init"
    python_hook: "backend.modules.my_module.init_workspace:init_workspace"

docs:
  api: "modules/my_module/api.openapi.yaml"
  interop: "modules/my_module/interop.yaml"
```

Ключевые поля:

- `frontend.base_path` — URL-путь к папке `frontend/modules/<module_id>/`, обычно `modules/<module_id>`;
- `frontend.pages` — страницы модуля;
- `backend.router` — ссылка на Python `APIRouter`;
- `backend.api_prefix` — API-префикс модуля;
- `workspace.folder` — папка модуля внутри workspace;
- `workspace.init` — init-файлы и/или Python hook для нового workspace;
- `docs.api`, `docs.interop` — машинно-читаемая документация.

---

## 7. Отображение страниц в меню

Левое меню строится из `module.yaml`, а не из JS-кода.

Страница отображается в меню:

```yaml
menu:
  show: true
  title: "My Module"
  icon: "◎"
  order: 100
```

Страница зарегистрирована, но скрыта из меню:

```yaml
menu:
  show: false
```

Скрытая страница может открываться из другого модуля через `navigateToPage()`.

Полный `page_id` имеет вид:

```text
<module_id>.<page_id>
```

Например: `my_module.main`, `my_module.details`.

---

## 8. Frontend модуля

HTML подключает общий CSS ядра и CSS модуля:

```html
<link rel="stylesheet" href="/base/css/tokens.css">
<link rel="stylesheet" href="/base/css/layout.css">
<link rel="stylesheet" href="/base/css/components.css">
<link rel="stylesheet" href="css/module.css">
<script type="module" src="js/main.js"></script>
```

Основные helper-ы:

```js
import { apiFetch } from '/base/js/api.js';
import { getContext, currentWorkspaceId } from '/base/js/context.js';
import { initLayout } from '/base/js/layout.js';
import { navigateToPage } from '/base/js/navigation.js';
import { showToast } from '/base/js/ui.js';
```

Минимальный `main.js`:

```js
import { apiFetch } from '/base/js/api.js';
import { getContext, currentWorkspaceId } from '/base/js/context.js';
import { initLayout } from '/base/js/layout.js';

await initLayout('my_module.main');
const context = await getContext();
const workspaceId = currentWorkspaceId(context);

const data = await apiFetch(`/api/my-module/items?workspace_id=${encodeURIComponent(workspaceId)}`);
console.log(data);
```

Переход на страницу своего или другого модуля:

```js
import { navigateToPage } from '/base/js/navigation.js';

navigateToPage('other_module.main', { item_id: 'item_123' });
```

`workspace_id` будет добавлен автоматически из текущего контекста, если не передан явно.

---

## 9. Backend API модуля

Префикс API задается в `module.yaml`, поэтому в `api.py` маршруты задаются относительно префикса.

Пример `backend/modules/my_module/api.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.core.auth.dependencies import require_user
from backend.app.state import AppState, get_state

router = APIRouter(tags=["my-module"])


@router.get("/items")
def list_items(
    workspace_id: str = Query(...),
    user: dict = Depends(require_user),
    state: AppState = Depends(get_state),
):
    if not state.workspaces.user_can_access(user, workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace unavailable")

    module = state.modules.get_module("my_module")
    module_path = state.workspaces.get_module_path_for_manifest(workspace_id, module)
    return {"items": [], "module_path": str(module_path)}
```

Правила:

- используй `require_user` для защищенных endpoints;
- принимай `workspace_id`, если endpoint работает с workspace;
- проверяй `state.workspaces.user_can_access(user, workspace_id)`;
- не принимай абсолютные пути от frontend;
- возвращай JSON;
- описывай endpoint в `api.openapi.yaml` и в `backend/modules/<module_id>/API.md`.

---

## 10. Относительные пути workspace

Физическая структура:

```text
data/workspaces/<workspace_id>/
  workspace.yaml
  settings.yaml
  <module_folder>/
    ...файлы модуля...
```

Если в manifest указано:

```yaml
workspace:
  folder: "my_module"
```

то файлы модуля должны лежать в:

```text
data/workspaces/<workspace_id>/my_module/
```

Получение своей папки:

```python
module = state.modules.get_module("my_module")
module_path = state.workspaces.get_module_path_for_manifest(workspace_id, module)
```

Получение папки другого модуля:

```python
other = state.modules.get_module("other_module")
other_path = state.workspaces.get_module_path_for_manifest(workspace_id, other)
source_file = other_path / "items.json"
```

Если модуль читает файлы другого модуля, укажи это в `interop.yaml`.

Frontend не должен передавать абсолютные пути. Если endpoint принимает путь, он должен быть относительным внутри workspace или внутри папки модуля.

---

## 11. Инициализация при создании нового workspace

При создании нового workspace ядро запускает init для каждого включенного модуля.

### Вариант 1: копирование файлов

`module.yaml`:

```yaml
workspace:
  folder: "my_module"
  init:
    files: "modules/my_module/init"
```

Все файлы из `modules/my_module/init/` копируются в:

```text
data/workspaces/<workspace_id>/my_module/
```

### Вариант 2: Python hook

`module.yaml`:

```yaml
workspace:
  init:
    python_hook: "backend.modules.my_module.init_workspace:init_workspace"
```

`backend/modules/my_module/init_workspace.py`:

```python
from __future__ import annotations

import json


def init_workspace(*, config, username, workspace_id, workspace, workspace_path, module, module_path) -> None:
    module_path.mkdir(parents=True, exist_ok=True)
    target = module_path / "state.json"
    target.write_text(
        json.dumps({"created_for": username, "workspace_id": workspace_id}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

Используй `init/` для статичных шаблонов файлов. Используй hook, если файл нужно создать программно.

---

## 12. Конфигурация модуля

Runtime-конфиг модуля хранится в:

```text
modules/<module_id>/config.yaml
```

Пример:

```yaml
workspace_folder: "my_module"
files:
  items: "items.json"
ui:
  title: "My Module"
llm:
  prompt_template: "default"
```

Ядро читает файл, но не валидирует бизнес-поля.

Frontend может получить конфиг:

```js
const config = await apiFetch('/api/config/modules/my_module');
```

Backend может получить конфиг:

```python
module_config = state.config.read_module_runtime_config("my_module")
```

---

## 13. Настройки пользователя и LLM

Пользовательские настройки доступны через:

```text
GET /api/users/me/settings
PUT /api/users/me/settings
```

Текущая структура LLM-настроек:

```yaml
settings:
  llm:
    provider: "ollama-cloud"
    model: "qwen3.5:397b"
    base_url: "https://ollama.com"
    api_key: "..."
```

Значения `provider`:

```text
ollama-cloud, ollama, lmstudio, openai, anthropic, gemini, openrouter, opencode, openai-compatible
```

Во frontend:

```js
const data = await apiFetch('/api/users/me/settings');
const llm = data.settings?.llm || {};
console.log(llm.provider, llm.model);
```

Если `api_key` отображается в UI, показывай его только замаскированным или не показывай совсем.

В backend:

```python
llm = user.get("settings", {}).get("llm", {})
provider = llm.get("provider")
model = llm.get("model")
base_url = llm.get("base_url")
api_key = llm.get("api_key")
```

Модуль сам решает, как вызывать LLM с этими параметрами.

---

## 14. Документация API модуля

У модуля должно быть машинно-читаемое описание API:

```text
modules/<module_id>/api.openapi.yaml
```

Пример:

```yaml
openapi: "3.1.0"
info:
  title: "My Module API"
  version: "0.1.0"
paths:
  /api/my-module/items:
    get:
      summary: "List items"
      parameters:
        - name: "workspace_id"
          in: "query"
          required: true
          schema:
            type: "string"
      responses:
        "200":
          description: "Items list"
```

Также сделай краткий файл:

```text
backend/modules/<module_id>/API.md
```

В нем перечисли endpoints, назначение, параметры, пример ответа и файлы workspace, которые endpoint читает или пишет. Не делай этот файл большим.

---

## 15. Использование API или данных другого модуля

Frontend может вызвать чужой API через `apiFetch`:

```js
const data = await apiFetch(`/api/other-module/items?workspace_id=${encodeURIComponent(workspaceId)}`);
```

Backend может импортировать сервис другого модуля или читать его файлы из того же workspace. Если используешь чужие страницы, API или файлы, обязательно отрази это в `interop.yaml`.

---

## 16. `interop.yaml`

`interop.yaml` описывает, что модуль предоставляет и что использует.

```yaml
module: "my_module"

provides:
  pages:
    - id: "my_module.main"
      path: "modules/my_module/index.html"
      params: ["workspace_id"]
  api:
    - method: "GET"
      path: "api/my-module/items"
  workspace_files:
    - path: "my_module/items.json"
      format: "json"

consumes:
  pages:
    - "other_module.main"
  api:
    - method: "GET"
      path: "api/other-module/items"
  workspace_files:
    - path: "other_module/items.json"
      format: "json"
```

OpenAPI описывает API. `interop.yaml` описывает связи между модулями.

---

## 17. Конвертация существующего JS + Python API приложения в модуль

1. Выбери `module_id`.
2. Перенеси HTML/JS/CSS в `frontend/modules/<module_id>/`.
3. Перенеси Python API в `backend/modules/<module_id>/` и оформи через `APIRouter`.
4. Создай `modules/<module_id>/module.yaml`, `config.yaml`, `api.openapi.yaml`, `interop.yaml`, `README.md`.
5. Добавь модуль в `config/modules.yaml`.
6. Замени хранение рабочих данных в `localStorage` на REST API + файлы workspace. `localStorage` допустим только для временного UI-состояния.
7. Замени абсолютные пути на относительные пути workspace.
8. Добавь `workspace_id` в API, которые работают с workspace-данными.
9. Проверь `require_user` и `user_can_access` в backend endpoints.
10. Если нужны начальные файлы workspace, добавь `modules/<module_id>/init/` и/или Python hook.
11. Если модуль использует другой модуль, опиши это в `interop.yaml`.
12. Перезапусти приложение и проверь страницу, API, меню, workspace-файлы и документацию.

---

## 18. Что нельзя делать при разработке модуля

Не нужно:

- добавлять пункты меню вручную в базовый JS;
- хранить настраиваемые бизнес-параметры в коде;
- принимать абсолютные пути от frontend;
- хранить workspace-данные только в `localStorage`;
- делать свой механизм логина;
- обходить `workspace_id` в API, работающем с workspace;
- делать один большой JS-файл или один большой Python-файл;
- менять ядро без явной необходимости.

---

## 19. Чек-лист

Перед завершением модуля проверь:

- [ ] создан `modules/<module_id>/module.yaml`;
- [ ] создан `modules/<module_id>/config.yaml`;
- [ ] создан `modules/<module_id>/api.openapi.yaml`;
- [ ] создан `modules/<module_id>/interop.yaml`;
- [ ] создан backend `APIRouter`;
- [ ] создан frontend `index.html` и `js/main.js`;
- [ ] модуль добавлен в `config/modules.yaml`;
- [ ] меню настроено через `menu.show`;
- [ ] API принимает `workspace_id` и проверяет доступ;
- [ ] данные пишутся только внутрь workspace;
- [ ] init workspace настроен, если нужны стартовые файлы;
- [ ] пользовательские LLM-настройки берутся из `/api/users/me/settings` или из `user.settings.llm` в backend;
- [ ] API описан в OpenAPI и кратком `API.md`;
- [ ] связи с другими модулями описаны в `interop.yaml`.

---

## 20. Рабочий порядок для LLM

Сначала создай интеграционный каркас:

```text
module.yaml
config.yaml
api.openapi.yaml
interop.yaml
backend api.py
frontend index.html + js/main.js
запись в config/modules.yaml
```

После проверки каркаса добавляй бизнес-логику, дополнительные страницы, endpoints, работу с файлами и LLM-агентов.
