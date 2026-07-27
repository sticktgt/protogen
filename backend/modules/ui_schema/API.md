# UI Schema API

API работает с UI-схемой текущего workspace. Все пути внутри workspace относительные.
При активной задаче AI-синхронизации операции ручной записи в `ui_schema/` возвращают `409`, чтение остаётся доступным.

## Основная схема

- `GET /api/ui-schema?workspace_id=...` — сводка схемы, страниц, требований и связей.
  Необязательный `preview_run_id` возвращает временную схему агента.
- `GET/PUT /api/ui-schema/app` — чтение и изменение приложения.
- `POST /api/ui-schema/app/elements` — добавить корневой элемент или элемент меню.
- `PUT/DELETE /api/ui-schema/app/elements/{element_id}` — изменить или удалить элемент приложения.
- `GET/POST /api/ui-schema/pages` — список или создание страниц.
- `GET/PUT/DELETE /api/ui-schema/pages/{page_id}` — работа со страницей.
- `POST /api/ui-schema/pages/{page_id}/elements` — добавить элемент.
- `PUT/DELETE /api/ui-schema/pages/{page_id}/elements/{element_id}` — изменить или удалить элемент.
- `GET/POST /api/ui-schema/requirement-links` — связи требований с UI.
- `DELETE /api/ui-schema/requirement-links/{link_id}` — удалить связь требования.
- `GET /api/ui-schema/requirements` — требования, динамически разрешённые по `requirements_source.json`; ответ также содержит состояние источника.
- `GET/POST /api/ui-schema/ui-links` — связи между UI-объектами.
- `DELETE /api/ui-schema/ui-links/{link_id}` — удалить UI-связь.
- `POST /api/ui-schema/code-links` и `DELETE /api/ui-schema/code-links/{link_id}` — кодовые связи.

## AI-синхронизация

### Настройки и проверка LLM

Модель, provider, base URL и API key читаются из `user.settings.llm` текущего пользователя. Значения не дублируются в конфигурации модуля. Для `ollama-cloud` адрес `https://ollama.com` автоматически нормализуется в OpenAI-compatible endpoint `https://ollama.com/v1`.

- `POST /api/ui-schema/agent/llm/test` — проверить соединение и обязательный tool call по настройкам текущего пользователя. Принимает JSON с `workspace_id`. API key в ответ не возвращается.

### Запуск

`POST /api/ui-schema/agent-runs`, `application/json`:

- `workspace_id`;
- `requirements_path` — относительный путь от корня workspace к JSON-файлу с массивом `requirements`;
- `user_request` — необязательное указание аналитика;
- `base_mode` — `current` или `initial`. Вариант `initial` доступен после первого запуска AI-синхронизации и означает схему, зафиксированную до этого первого запуска; непринятый preview не используется как база.

Backend проверяет, что путь остаётся внутри workspace, читает файл и копирует его содержимое только во временную сессию. В рабочей UI-схеме сохраняется `requirements_source.json` со ссылкой и контрольной суммой, а локальная копия требований не создаётся. Для диагностики дополнительно создаются компактные `input/requirements.agent.json`, `input/ui_schema_context.json` и `input/synchronization_context.json`. Создаётся временная копия `ui_schema/`, запускается один ограниченный LangChain-agent только с доменными инструментами и возвращается `run_id`.
Одновременно в workspace допускается одна активная задача.

### Состояние и результат

- `GET /api/ui-schema/agent-runs/active?workspace_id=...` — активная задача.
- `GET /api/ui-schema/agent-runs/{run_id}?workspace_id=...` — статус, этап, статистика и отчёт.
- `GET /api/ui-schema/agent-runs/{run_id}/changes?workspace_id=...` — детерминированные статистика, семантический перечень объектов/связей, поля до/после и список файлов.
- `GET /api/ui-schema/agent-runs/{run_id}/requirements-ui-result?workspace_id=...` — все входные требования с взаимоисключающим результатом `linked`, `cross_cutting_ui`, `no_ui`, `unclear` или аварийным `unclassified`.
- `GET /api/ui-schema/agent-runs/{run_id}/diagnostics?workspace_id=...` — ZIP-отчёт запуска: вход, базовая и временная схемы, reference-файлы, результаты, события, метрики, traceback и версии библиотек. API key не включается.

Статусы: `running`, `preview_ready`, `applying`, `completed`, `rejected`, `failed`, `cancelled`.

### Решение аналитика

- `POST /api/ui-schema/agent-runs/{run_id}/apply` — применить результат целиком; операция блокируется, если внешний файл требований изменился после генерации preview.
- `POST /api/ui-schema/agent-runs/{run_id}/reject` — отклонить результат целиком.
- `POST /api/ui-schema/agent-runs/{run_id}/regenerate` — повторить генерацию от той же исходной схемы с новым комментарием.
- `POST /api/ui-schema/agent-runs/{run_id}/cancel` — мягко отменить выполняющуюся задачу.

`apply`, `reject`, `regenerate`, `cancel` принимают JSON с `workspace_id`; `regenerate` также принимает `comment`.

## Снимки и экспорт

- `GET /api/ui-schema/history/latest?workspace_id=...` — последний ZIP-снимок и признак `initial_snapshot_available`, показывающий наличие базы до первого запуска AI-синхронизации.
- `POST /api/ui-schema/history/restore-latest` — восстановить последний снимок; перед восстановлением текущее состояние тоже архивируется.
- `GET /api/ui-schema/exports/requirements-ui/{run_id}?workspace_id=...` — принятый экспорт требований со связанными UI-компонентами.

При применении агентского результата backend читает и пишет:

```text
<workspace>/ui_schema/**
<workspace>/.protoarchitect/ui_schema_agent/**
```

Ограниченный агент изменяет только временную копию `working/ui_schema/`. Рабочая папка заменяется только после общей структурной проверки и подтверждения аналитика.

## Наблюдение и ограничения агентской задачи

- `GET /api/ui-schema/agent-runs/{run_id}/events?workspace_id=...&after=0&limit=200` — инкрементальный журнал выполнения и агрегированные метрики.

Ответ содержит:

```json
{
  "events": [
    {
      "seq": 12,
      "timestamp": "2026-07-24T12:30:00+00:00",
      "level": "info",
      "type": "tool_start",
      "message": "Запись страницы UI-схемы: pages/home.json",
      "data": {"tool": "write_ui_schema_page", "file_count": 1}
    }
  ],
  "metrics": {
    "llm_calls": 5,
    "tool_calls": 18,
    "last_tool": "write_ui_schema_page",
    "repeat_streak": 1,
    "max_repeat_streak": 2,
    "input_tokens": 120000,
    "output_tokens": 9000,
    "total_tokens": 129000,
    "token_usage_available": true,
    "last_event_at": "2026-07-24T12:30:00+00:00",
    "limits": {
      "max_llm_calls": 24,
      "max_tool_calls": 32,
      "max_total_tokens": 2000000,
      "max_duration_seconds": 1200,
      "recursion_limit": 160,
      "request_timeout_seconds": 300,
      "max_repeated_tool_calls": 3
    }
  },
  "next_after": 12
}
```

Журнал интерфейса не содержит prompt, содержимое требований, ответы модели или chain of thought. Записываются только этапы, имена инструментов, безопасные пути, ошибки и агрегированная usage-статистика. После остановки или подготовки preview формируется диагностический ZIP. Он предназначен для внутреннего анализа и включает исходный файл требований и временные данные запуска, поэтому его следует считать проектным артефактом workspace. API key и другие credentials в архив не записываются.

Пределы задаются в `modules/ui_schema/config.yaml -> agent.execution`. Повторение одного tool call с одинаковыми аргументами также отслеживается и останавливается. При достижении лимита задача переводится в `failed` с `phase: stopped_by_limit`. Увеличение `recursion_limit` не считается исправлением повторяющегося агентского цикла. Отмена сначала переводит задачу в `cancelling`; фактическая остановка происходит на ближайшей границе LLM/tool-вызова, а один сетевой запрос дополнительно ограничен `request_timeout_seconds`.

Статусы: `running`, `cancelling`, `preview_ready`, `applying`, `completed`, `rejected`, `failed`, `cancelled`.

Если backend был перезапущен во время задачи, in-memory worker отсутствует, но запись запуска может остаться активной. В этом случае `POST .../cancel` завершает такую задачу сразу и освобождает workspace.


## Завершение и очистка agent runs

После `apply`, `reject` или окончательной отмены тяжёлая папка временного запуска удаляется. Сохраняются диагностический ZIP и компактная запись о статусе, метриках и последних событиях. Endpoint диагностики продолжает работать по исходному `run_id`.

## Выполнение ограниченного агента

Агенту доступны только доменные инструменты: загрузка текущего контекста, отдельная запись core-документов, пакетная запись изменяемых страниц, запись трассировки требований и отчёта, ограниченное удаление новых объектов и проверка. Универсальные `write_todos`, filesystem, shell и execute-инструменты не подключаются. Tool schema публикует объекты и массивы как native JSON; модель не должна передавать их строками. Нормальный запуск выполняет одну загрузку контекста, не более одного core-вызова, один или два page-вызова, один traceability-вызов и проверку. Перед проверкой backend детерминированно исправляет только однозначные технические ошибки: legacy-колонки `text` внутри `table` переводятся в `table_column`, а пунктуационные опечатки в ссылочных ID исправляются только при единственном совпадении. Все такие действия попадают в `result/normalization.json` и диагностический ZIP. Если лимит достигнут, но локальная нормализация и проверка дают валидную схему, backend формирует preview без дополнительного LLM-вызова.


## Классификация требований и итоговая сводка

Агент определяет семантический класс требования, но каждый ID должен иметь ровно один итоговый статус. Прямые UI-требования задаются requirement links; остальные относятся к `cross_cutting_ui`, `no_ui` или `unclear`. Backend не анализирует текст требований: он проверяет полноту классификации, отсутствие пересечений, запрет links для `no_ui`/`unclear` и наличие links для targeted `cross_cutting_ui`. Основная строка результата формируется backend по фактическим изменениям и счётчикам. Свободный `agent_note` хранится и показывается отдельно как комментарий модели.
