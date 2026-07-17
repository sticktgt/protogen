# Demo Hello backend API

Runtime prefix берется из `modules/demo_hello/module.yaml`:

```text
/api/hello
```

## GET /api/hello/message

Назначение: прочитать сообщение из текущего workspace.

Query params:
- `workspace_id`: идентификатор workspace.

Читает:
- `demo_hello/message.json` или путь из `modules/demo_hello/config.yaml`.

## PUT /api/hello/message

Назначение: сохранить сообщение в workspace.

Request JSON:

```json
{
  "workspace_id": "ws_demo",
  "message": "text"
}
```

Пишет:
- `demo_hello/message.json` или путь из `modules/demo_hello/config.yaml`.
