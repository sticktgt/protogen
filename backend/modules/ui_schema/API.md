# UI Schema API

API работает с UI-схемой текущего workspace. Все пути внутри workspace относительные. При активной AI-синхронизации операции ручной записи в `ui_schema/` возвращают `409`, чтение остаётся доступным.

## Основная схема

- `GET /api/ui-schema?workspace_id=...` — сводка схемы, страниц, требований и связей. Необязательный `preview_run_id` возвращает временную схему.
- `GET/PUT /api/ui-schema/app` — приложение и корневые элементы.
- `POST /api/ui-schema/app/elements` — добавить элемент приложения.
- `PUT/DELETE /api/ui-schema/app/elements/{element_id}` — изменить или удалить элемент приложения.
- `GET/POST /api/ui-schema/pages` — список или создание страниц.
- `GET/PUT/DELETE /api/ui-schema/pages/{page_id}` — работа со страницей.
- `POST /api/ui-schema/pages/{page_id}/elements` — добавить элемент страницы.
- `PUT/DELETE /api/ui-schema/pages/{page_id}/elements/{element_id}` — изменить или удалить элемент.
- `GET/POST /api/ui-schema/requirement-links` — связи требований с UI.
- `DELETE /api/ui-schema/requirement-links/{link_id}` — удалить requirement-связь.
- `GET /api/ui-schema/requirements` — требования, разрешённые по `requirements_source.json`.
- `GET/POST /api/ui-schema/ui-links` — связи между UI-объектами.
- `DELETE /api/ui-schema/ui-links/{link_id}` — удалить UI-связь.
- `POST /api/ui-schema/code-links` и `DELETE /api/ui-schema/code-links/{link_id}` — кодовые связи.

## AI-синхронизация

### Настройки и проверка LLM

Provider, model, base URL и API key читаются из `user.settings.llm` текущего пользователя. Credentials в ответы и диагностику не записываются.

- `POST /api/ui-schema/agent/llm/test` — проверить соединение и обязательный structured-output вызов. Принимает `workspace_id`.

### Создание запуска

`POST /api/ui-schema/agent-runs`, `application/json`:

- `workspace_id`;
- `requirements_path` — относительный путь к JSON-файлу с массивом `requirements`;
- `user_request` — необязательное указание аналитика;
- `base_mode` — `current` или `initial`.

Backend проверяет путь, читает полный текущий набор требований, создаёт `base/ui_schema/` и `working/ui_schema/`, сохраняет диагностические снимки входа и запускает управляемый pipeline v2. В канонической схеме хранится только `requirements_source.json` со ссылкой и контрольной суммой.

В workspace допускается одна активная задача.

### Управляемый pipeline v2

Модель не управляет workflow и не выбирает инструменты. Backend вызывает фиксированные изолированные стадии с одним обязательным structured-output контрактом.

1. Требования механически делятся на группы анализа.
2. Planning-группы последовательно сопоставляются с текущей схемой. Каждая группа возвращает канонические решения и один транзакционный пакет. Успешные пакеты сразу становятся частью `working/ui_schema/`, поэтому следующие группы могут переиспользовать и расширять существующие объекты.
3. Технически отклонённый пакет полностью откатывается и может быть исправлен в пределах настроенного числа попыток в том же ограниченном контексте.
4. Независимый аудит проверяет только `direct_ui` по компактным структурам фактических целей и возвращает только найденные дефекты.
5. Дефекты и отсутствующие цели исправляются ограниченными correction-группами; после единственного correction-раунда повторный аудит проверяет только исправлявшиеся требования, а оставшиеся смысловые замечания становятся предупреждениями.
6. Backend сравнивает base/working и собирает структурные кандидаты среди изменённых объектов и связей. На этом этапе модель не вызывается, схема не меняется, а высокосигнальные кандидаты выводятся как предупреждения для ручной проверки.
7. Backend формирует совместимые requirement links и `agent_report.json`, выполняет общую structural validation и создаёт preview.

Размеры групп, попытки стадий, имена prompt-файлов и output tools задаются в `modules/ui_schema/config.yaml -> agent.pipeline`. Prompt-текст хранится только в `modules/ui_schema/agent/prompts/`.

Backend не анализирует смысл требований и не выбирает классификацию, цель, состав UI или статус реализации. Его проверки ограничены форматом, полнотой ID, типами, scope, родителями, ссылками и транзакционностью.

### Синхронизация текущего набора

Входной файл считается полным авторитетным набором на момент запуска. Для каждого текущего ID pipeline формирует прямую UI-трассировку либо одну из классификаций `cross_cutting_ui`, `no_ui`, `unclear`.

Planning получает текущую схему и прежние requirement links. Модель может переиспользовать существующую цель, обновить метаданные страницы, расширить существующую структуру или создать отсутствующую. Пакеты предыдущих групп не повторяются.

Прежние requirement links для ID, отсутствующих в новом наборе, удаляются только из временного результата. Сами страницы и элементы автоматически не удаляются; прежние связи попадают в `changes.manual_review.inherited_requirement_links`.

### Статус и результат

- `GET /api/ui-schema/agent-runs/active?workspace_id=...` — активная задача.
- `GET /api/ui-schema/agent-runs/{run_id}?workspace_id=...` — статус, этап, статистика и отчёт.
- `GET /api/ui-schema/agent-runs/{run_id}/events?workspace_id=...&after=0&limit=200` — журнал и метрики.
- `GET /api/ui-schema/agent-runs/{run_id}/changes?workspace_id=...` — статистика, объектный diff, file diff и ручная проверка.
- `GET /api/ui-schema/agent-runs/{run_id}/requirements-ui-result?workspace_id=...` — итог по каждому входному требованию.
- `GET /api/ui-schema/agent-runs/{run_id}/diagnostics?workspace_id=...` — диагностический ZIP.

Статусы: `running`, `cancelling`, `preview_ready`, `applying`, `completed`, `rejected`, `failed`, `cancelled`.

Этапы активного запуска отражают текущую стадию pipeline: анализ, planning, audit, correction, структурная проверка, запись трассировки и validation.

### Решение аналитика

- `POST /api/ui-schema/agent-runs/{run_id}/apply` — применить результат целиком. Операция блокируется, если внешний файл требований изменился после preview.
- `POST /api/ui-schema/agent-runs/{run_id}/reject` — отклонить результат.
- `POST /api/ui-schema/agent-runs/{run_id}/regenerate` — повторить от той же базовой схемы с новым комментарием.
- `POST /api/ui-schema/agent-runs/{run_id}/cancel` — мягко отменить активную задачу.

Все запросы принимают `workspace_id`; `regenerate` также принимает `comment`.

## Preview, diff и ручная проверка

Ответ `changes` содержит:

- `file_diff` — детерминированный unified diff `base/ui_schema/` и `working/ui_schema/`;
- изменения страниц, элементов и связей с полями до/после;
- `manual_review.inherited_requirement_links` — прежние связи отсутствующих requirement ID для ручной оценки связанных объектов.

## Наблюдение и лимиты

Метрики включают число LLM-вызовов, токены, длительность и настроенные пределы. Domain tool calls могут отсутствовать: pipeline использует structured output как контракт ответа, а техническое применение выполняет backend напрямую.

Журнал не хранит prompt, полные требования, полные ответы модели или chain of thought. Диагностический ZIP, напротив, является внутренним проектным артефактом и содержит вход, base/working-схему, снимки prompt/reference-файлов, результаты стадий, validation, события, метрики и версии библиотек.

Лимиты задаются в `modules/ui_schema/config.yaml -> agent.execution`. При их достижении запуск переводится в `failed` с `phase: stopped_by_limit`. Отмена применяется на ближайшей границе LLM-вызова или стадии.

## Транзакционные изменения

Planning и correction возвращают:

- `create_pages`;
- `update_pages` для метаданных существующих страниц;
- `upsert_elements` для `app.json` и страниц;
- явные `move_elements`;
- `ui_links`;
- либо `no_changes_reason` при отсутствии операций.

Один пакет применяется атомарно. При ошибке `working/ui_schema/` восстанавливается до состояния перед текущим пакетом. Ранее успешные группы сохраняются.

Структурная проверка не применяет change bundle и не удаляет элементы или UI-связи. Кандидаты сохраняются в `structural_review.json` и отражаются в предупреждениях результата.

Backend проверяет точные ID, scope, `root_allowed`, `allowed_children`, `allowed_parents`, уникальные app-корни, родителей существующих элементов и допустимые UI-связи. Смысл и содержимое операций выбирает модель.

## Снимки и экспорт

- `GET /api/ui-schema/history/latest?workspace_id=...` — последний ZIP-снимок и наличие initial snapshot.
- `POST /api/ui-schema/history/restore-latest` — восстановить последний снимок.
- `GET /api/ui-schema/exports/requirements-ui/{run_id}?workspace_id=...` — принятый экспорт требований с UI-компонентами.

После `apply`, `reject` или окончательной отмены тяжёлая папка запуска удаляется. Сохраняются диагностический ZIP и компактная итоговая запись запуска.
