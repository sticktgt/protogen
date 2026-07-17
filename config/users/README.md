# config/users

Файлы пользователей приложения.

Один пользователь — один YAML-файл:

```text
config/users/<username>.yaml
```

Основные поля:
- `username` — логин;
- `display_name` — отображаемое имя;
- `is_admin` — системный пользователь, которому доступны функции администрирования;
- `password_hash` — хеш пароля;
- `current_workspace_id` — активный workspace;
- `settings` — персональные настройки пользователя;
- `workspaces.owned` — собственные workspace;
- `workspaces.shared` — доступные shared workspace.

Пароли в открытом виде здесь не хранятся.
