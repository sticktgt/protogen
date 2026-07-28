# Промпт для DeepSeek Chat: создание минимального модуля `demo_notes`

Файл содержит два сообщения для публичного чата DeepSeek.

Первое сообщение передает общую инструкцию по разработке модулей ProtoArchitect. Второе сообщение ставит задачу на создание конкретного минимального модуля.

## Сообщение 1. Контекст и правила ProtoArchitect

```text
Ты — разработчик модуля для приложения ProtoArchitect.

Сначала прочитай инструкцию ниже. Не генерируй код и не создавай файлы, пока я не дам отдельную задачу.

После чтения кратко подтверди, что понял правила разработки модулей ProtoArchitect.

Ключевые правила:
- ядро приложения не менять;
- модуль должен быть самостоятельным;
- все пути должны быть относительными;
- данные workspace хранить в JSON/YAML внутри папки модуля;
- backend писать на Python/FastAPI через APIRouter;
- frontend писать как простые HTML + JS + CSS, без SPA и без сборки;
- не делать большие JS/Python-файлы;
- настройки и manifest хранить в YAML/JSON;
- обязательно подготовить module.yaml, config.yaml, api.openapi.yaml, interop.yaml, README.md;
- если нужны стартовые файлы workspace, положить их в modules/<module_id>/init/;
- endpoints, работающие с workspace, должны принимать workspace_id и проверять доступ пользователя;
- workspace_id нельзя заменять абсолютными путями;
- результат нужно будет вывести по файлам с относительными путями от корня проекта.

Ниже инструкция ProtoArchitect:

[ВСТАВИТЬ СЮДА ПОЛНЫЙ ТЕКСТ docs/LLM_MODULE_DEVELOPMENT_GUIDE.md]
```

## Сообщение 2. Задача на модуль

```text
Создай минимально работающий модуль ProtoArchitect с module_id = demo_notes.

Русское название модуля: Заметки.
Техническое название: Demo Notes.

Назначение:
Модуль позволяет пользователю вести простые заметки внутри активного workspace.

Функциональность:
1. Модуль отображается в левом меню как "Заметки".
2. На странице модуля показывается список заметок текущего workspace.
3. Пользователь может создать заметку.
4. Пользователь может удалить заметку.
5. После создания или удаления список заметок обновляется.
6. Данные заметок хранятся в JSON-файле workspace.

Поля заметки:
- id — формируется backend автоматически;
- title — заголовок заметки, обязательное поле;
- text — текст заметки, необязательное поле;
- created_at — дата и время создания, формируется backend автоматически;
- updated_at — дата и время последнего изменения, для первой версии может совпадать с created_at.

Файл данных workspace:
- demo_notes/notes.json

Стартовое содержимое notes.json для нового workspace:
{
  "notes": []
}

Backend API:
1. GET /api/demo-notes/notes?workspace_id=<workspace_id>
   Назначение: получить список заметок workspace.

2. POST /api/demo-notes/notes
   Назначение: создать заметку.
   Body:
   {
     "workspace_id": "ws_demo",
     "title": "Текст заголовка",
     "text": "Текст заметки"
   }

3. DELETE /api/demo-notes/notes/{note_id}?workspace_id=<workspace_id>
   Назначение: удалить заметку.

Backend-правила:
- использовать require_user;
- проверять state.workspaces.user_can_access(user, workspace_id);
- получать папку модуля через state.modules.get_module("demo_notes") и state.workspaces.get_module_path_for_manifest(...);
- использовать pathlib для работы с путями;
- возвращать JSON;
- не принимать абсолютные пути от frontend.

Frontend:
- одна страница frontend/modules/demo_notes/index.html;
- CSS в frontend/modules/demo_notes/css/module.css;
- JS разделить минимум на:
  - frontend/modules/demo_notes/js/api.js;
  - frontend/modules/demo_notes/js/main.js;
- использовать apiFetch из /base/js/api.js;
- использовать getContext/currentWorkspaceId из /base/js/context.js;
- использовать initLayout из /base/js/layout.js;
- URL к API должны быть относительными к корню приложения.

Конфигурационные и документационные файлы:
Создай:
- modules/demo_notes/module.yaml;
- modules/demo_notes/config.yaml;
- modules/demo_notes/api.openapi.yaml;
- modules/demo_notes/interop.yaml;
- modules/demo_notes/README.md;
- modules/demo_notes/init/notes.json;
- backend/modules/demo_notes/API.md.

Backend-файлы:
Создай:
- backend/modules/demo_notes/__init__.py;
- backend/modules/demo_notes/api.py;
- backend/modules/demo_notes/schemas.py;
- backend/modules/demo_notes/service.py;
- backend/modules/demo_notes/files.py.

Frontend-файлы:
Создай:
- frontend/modules/demo_notes/index.html;
- frontend/modules/demo_notes/css/module.css;
- frontend/modules/demo_notes/js/api.js;
- frontend/modules/demo_notes/js/main.js.

Также покажи фрагмент, который нужно добавить в config/modules.yaml, но не переписывай весь файл целиком.

Формат ответа:
Для каждого файла сначала строка:
FILE: <relative path from project root>

Затем полный код файла в markdown-блоке.

В конце отдельно выведи:
1. Новые файлы.
2. Измененные файлы.
3. Фрагмент для config/modules.yaml.
4. Инструкции по подключению.
5. Команды проверки.

Команды проверки должны включать:
python -m compileall backend/modules/demo_notes
node --check frontend/modules/demo_notes/js/*.js

Не меняй ядро приложения.
Не добавляй зависимости.
Не используй React/Vue/Angular.
Не используй localStorage для хранения заметок.
```

## Дополнительное сообщение для исправления ошибок

Использовать только если после переноса файлов появилась ошибка.

```text
В сгенерированном модуле есть ошибка. Исправь только затронутые файлы. Не меняй ядро приложения и не переписывай остальные файлы.

Ошибка:
<вставить полный текст ошибки>

Верни ответ в формате:
FILE: <relative path>
```language
<full corrected file content>
```
```
