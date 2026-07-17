# backend/modules

Каталог Python-кода backend-модулей.

Один модуль — одна подпапка:

```text
backend/modules/<module_id>/
  api.py
  schemas.py
  service.py
  files.py
  init_workspace.py
  API.md
```

`api.py` содержит FastAPI routes модуля.

`schemas.py` содержит Pydantic-схемы.

`service.py` содержит операции модуля.

`files.py` содержит функции работы с файлами workspace.

`init_workspace.py` содержит опциональный hook создания начальных файлов workspace.

`API.md` содержит краткое описание backend API рядом с кодом.
