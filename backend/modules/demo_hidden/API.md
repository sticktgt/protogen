# Demo Hidden backend API

Runtime prefix берется из `modules/demo_hidden/module.yaml`:

```text
/api/hidden
```

## GET /api/hidden/status

Назначение: прочитать статус скрытого UI-модуля и заметку из workspace.

Query params:
- `workspace_id`: идентификатор workspace.

## PUT /api/hidden/note

Назначение: сохранить заметку скрытого модуля в workspace.

Request JSON:

```json
{
  "workspace_id": "ws_demo",
  "note": "text"
}
```

Пишет:
- `demo_hidden/notes.json` или путь из `modules/demo_hidden/config.yaml`.
