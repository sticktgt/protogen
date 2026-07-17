# modules

Каталог описания подключаемых модулей.

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

`module.yaml` регистрирует UI, backend API, документацию и init-механизм workspace.

`config.yaml` содержит runtime-конфиг модуля. Ядро читает этот файл, но не валидирует бизнес-параметры.

`api.openapi.yaml` содержит машинно-читаемое описание API модуля.

`interop.yaml` содержит машинно-читаемое описание точек сопряжения с другими модулями.

`init/` содержит файлы, копируемые в папку модуля при создании нового workspace.
