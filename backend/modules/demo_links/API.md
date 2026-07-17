# Demo Links backend API

Runtime prefix берется из `modules/demo_links/module.yaml`:

```text
/api/links
```

## GET /api/links/info

Назначение: показать, что модуль может читать данные другого модуля в том же workspace.

Query params:
- `workspace_id`: идентификатор workspace.

Читает:
- путь из `modules/demo_links/config.yaml`, по умолчанию `demo_hello/message.json`.
