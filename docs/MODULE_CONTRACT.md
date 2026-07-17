# Контракт модуля

Модуль — независимая часть приложения, подключаемая через конфигурацию.

## Обязательные файлы

```text
modules/<module_id>/module.yaml
```

## Рекомендуемые файлы

```text
modules/<module_id>/config.yaml
modules/<module_id>/api.openapi.yaml
modules/<module_id>/interop.yaml
modules/<module_id>/README.md
modules/<module_id>/init/
backend/modules/<module_id>/API.md
```

## Frontend

Если у модуля есть UI:

```text
frontend/modules/<module_id>/
```

Страницы описываются в `modules/<module_id>/module.yaml`.

## Backend

Если у модуля есть API:

```text
backend/modules/<module_id>/
```

FastAPI router указывается в `modules/<module_id>/module.yaml`.

## Workspace

Рабочие данные модуля размещаются внутри текущего workspace.

Рекомендуемая папка:

```text
data/workspaces/<workspace_id>/<module_id>/
```

Папка задается в `module.yaml`:

```yaml
workspace:
  folder: "example"
```

## Init нового workspace

Модуль может определить начальную структуру для нового workspace:

```yaml
workspace:
  init:
    files: "modules/example/init"
    python_hook: "backend.modules.example.init_workspace:init_workspace"
```

- `files` копируется в папку модуля внутри workspace.
- `python_hook` вызывается после копирования файлов.
- Если init не нужен, блок можно не указывать.

## Регистрация

Модуль подключается записью в `config/modules.yaml`.

```yaml
modules:
  - id: "example"
    enabled: true
    manifest: "modules/example/module.yaml"
```

## Правила

- Состав модулей не хардкодится в UI.
- Пункты левого меню задаются в `module.yaml`.
- Страница может быть зарегистрирована без пункта меню.
- Настройки поведения модуля хранятся в `modules/<module_id>/config.yaml`.
- Ядро не валидирует бизнес-настройки модуля.
- Модуль сам отвечает за свое API, конфиг, данные и агентов.
- API модуля документируется в `modules/<module_id>/api.openapi.yaml`.
- Сопряжение с другими модулями документируется в `modules/<module_id>/interop.yaml`.
- Большие JS/Python-файлы делятся на малые файлы по функционалу.
