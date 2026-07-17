# data

Каталог рабочих данных приложения.

Workspace хранятся в:

```text
data/workspaces/<workspace_id>/
```

Каждый workspace содержит:

```text
workspace.yaml
settings.yaml
<module_id>/
```

`workspace.yaml` содержит ID, название, владельца, дату создания и описание.

`settings.yaml` содержит настройки workspace.

Папки модулей создаются при создании workspace. Начальные файлы модулей копируются из `modules/<module_id>/init/`, если это указано в `module.yaml`.
