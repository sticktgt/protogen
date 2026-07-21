# UI Schema API

API модуля работает с UI-схемой текущего workspace.
Все пути внутри workspace относительные, данные модуля лежат в папке `ui_schema/`.

## Endpoints

- `GET /api/ui-schema?workspace_id=...` — получить сводку схемы, страниц, требований и связей.

- `GET /api/ui-schema/app?workspace_id=...` — получить корневые элементы приложения, включая главное меню.
- `POST /api/ui-schema/app/elements` — добавить корневой элемент приложения или элемент меню.
- `PUT /api/ui-schema/app/elements/{element_id}` — изменить элемент приложения или меню.
- `DELETE /api/ui-schema/app/elements/{element_id}?workspace_id=...` — удалить элемент приложения или меню.
- `GET /api/ui-schema/pages?workspace_id=...` — получить список страниц.
- `GET /api/ui-schema/pages/{page_id}?workspace_id=...` — получить страницу.
- `POST /api/ui-schema/pages` — создать страницу.
- `PUT /api/ui-schema/pages/{page_id}` — изменить страницу.
- `DELETE /api/ui-schema/pages/{page_id}?workspace_id=...` — удалить страницу.
- `POST /api/ui-schema/pages/{page_id}/elements` — добавить элемент.
- `PUT /api/ui-schema/pages/{page_id}/elements/{element_id}` — изменить элемент.
- `DELETE /api/ui-schema/pages/{page_id}/elements/{element_id}?workspace_id=...` — удалить элемент.
- `GET /api/ui-schema/requirement-links?workspace_id=...` — получить связи требований с UI.
- `POST /api/ui-schema/requirement-links` — создать связь требования с UI.
- `DELETE /api/ui-schema/requirement-links/{link_id}?workspace_id=...` — удалить связь.
- `GET /api/ui-schema/requirements?workspace_id=...` — получить демонстрационный набор требований.

- `GET /api/ui-schema/ui-links?workspace_id=...` — получить связи между UI-объектами.
- `POST /api/ui-schema/ui-links` — добавить связь между UI-объектами, например пункт меню → страница.
- `DELETE /api/ui-schema/ui-links/{link_id}?workspace_id=...` — удалить связь между UI-объектами.
