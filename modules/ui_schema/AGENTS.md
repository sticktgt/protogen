# AGENTS.md — модуль `ui_schema`

Документ предназначен для разработчиков и LLM-агентов, которые изменяют модуль `ui_schema`.

## Назначение

Модуль хранит логическую UI-схему прототипа:

- приложение и корневые элементы;
- страницы и элементы страниц;
- связи между UI-объектами;
- связи требований с UI;
- ссылки UI на код;
- preview и AI-синхронизацию схемы с полным текущим набором требований.

Модуль не генерирует frontend-код и не реализует бизнес-поведение.

## Основные каталоги

```text
backend/modules/ui_schema/       backend API, хранение, validation и pipeline
frontend/modules/ui_schema/      интерфейс модуля
modules/ui_schema/               manifest, config, prompts, docs и init
```

Перед существенным изменением прочитать:

```text
modules/ui_schema/README.md
modules/ui_schema/docs/STORAGE.md
modules/ui_schema/agent/AGENT_INSTRUCTIONS.md
backend/modules/ui_schema/API.md
modules/ui_schema/api.openapi.yaml
modules/ui_schema/interop.yaml
```

## Каноническое хранение

```text
<workspace>/ui_schema/
  app.json
  schema.json
  index.json
  links.json
  code_links.json
  requirements_source.json
  mappings/requirement_ui_links.json
  pages/<page_id>.json
```

`requirements_source.json` содержит относительную ссылку и контрольную сумму внешнего файла требований. Локальный `requirements.json` поддерживается только при чтении старого workspace.

`index.json` является производным файлом и пересобирается backend-кодом.

Не менять формат хранения без обновления `docs/STORAGE.md`. Не добавлять демонстрационные страницы, связи или требования в `modules/ui_schema/init/`.

## Типы элементов

Единственный runtime-каталог типов находится в `modules/ui_schema/config.yaml -> ui.element_types`. Не дублировать список типов и правила вложенности в Python или JavaScript-константах.

Backend и frontend должны читать один каталог. Проверки scope, `root_allowed`, `allowed_children`, `allowed_parents` и link-source выполняются по этому конфигу.

## Управляемый pipeline v2

Внутренняя архитектура AI-синхронизации описана в `agent/AGENT_INSTRUCTIONS.md`.

Ключевые правила доработки:

1. Backend оркестрирует фиксированные стадии, но не выполняет смысловую работу модели.
2. Prompt-текст хранится только в `modules/ui_schema/agent/prompts/`.
3. Размеры групп, попытки, output tool names и другие параметры находятся только в `config.yaml`.
4. Модель не выбирает stage, tool или batch ID.
5. Каждый LLM-вызов изолирован; состояние хранится в файлах запуска и `working/ui_schema/`.
6. Существующие объекты синхронизируются через точные `reuse`/`extend`, `update_pages` и транзакционный upsert. Не создавать параллельные объекты без необходимости.
7. Technical validation может проверять формат, ID, типы, родителей, scope и ссылки, но не должна анализировать текст требования или выбирать исправление за моделью.
8. Канонические requirement links и `agent_report.json` формируются механически из финальных решений модели.
9. Структурная проверка механически собирает локальные кандидаты после correction, но не вызывает модель и не изменяет схему; кандидаты используются только для диагностики и предупреждений.

Совместимость со старой coverage-plan/traceability-review state machine не требуется. Не добавлять новые recovery-tools поверх старого workflow; изменения должны идти в управляемые стадии v2.

## Backend

Публичные маршруты находятся в `backend/modules/ui_schema/api.py`. Логику разделять по ответственности и не раздувать `api.py`, `service.py` или единый pipeline-файл без необходимости.

Для pipeline использовать отдельные файлы:

```text
agent_pipeline.py             оркестрация стадий
agent_pipeline_models.py      технический structured-output контракт
agent_pipeline_settings.py    чтение параметров config.yaml
agent_pipeline_context.py     механическое формирование контекста
agent_pipeline_llm.py         один изолированный structured-output вызов
agent_pipeline_validation.py  только технические проверки
agent_pipeline_results.py     совместимая запись результата
agent_structural_warnings.py  формирование предупреждений по структурным кандидатам
agent_structural_candidates.py  сбор и ограничение структурных кандидатов
agent_structural_element_candidates.py  кандидаты по элементам
agent_structural_container_candidates.py  кандидаты по опустевшим контейнерам
agent_structural_link_candidates.py  кандидаты по UI-связям
agent_structural_page_candidates.py  кандидаты по доступности новых страниц
agent_structural_navigation_validation.py  ограничения структурных изменений навигации
```

После операций, меняющих каноническую схему, пересобирать `index.json` существующим backend-механизмом.

## Frontend

Frontend должен оставаться модульным. API-вызовы, состояние, карта, структура и редакторы держать в отдельных файлах. Не добавлять JSON-редактор и framework-specific поля без отдельного решения.

Страница или групповой элемент с дочерними объектами не удаляются, пока дочерние объекты существуют.

## Требования и связи

Requirement links хранятся в `mappings/requirement_ui_links.json` и ссылаются на ID внешнего текущего набора требований.

UI-связи хранятся в `links.json`. Поддерживаемые отношения текущей версии:

```text
navigates_to
opens_modal
```

`code_links.json` pipeline синхронизации не изменяет.

## Документация

- изменение хранения → обновить `docs/STORAGE.md`;
- изменение публичного API → обновить `backend/modules/ui_schema/API.md` и при необходимости `api.openapi.yaml`;
- изменение сопряжения модулей → обновить `interop.yaml`;
- изменение runtime pipeline → обновить `README.md` и `agent/AGENT_INSTRUCTIONS.md`.

Документы описывают только текущее состояние. Не вести в них changelog.

## Проверки

После backend-изменений:

```bash
python -m compileall backend/modules/ui_schema
pytest -q tests/test_ui_schema_agent_*.py
```

После frontend-изменений:

```bash
node --check frontend/modules/ui_schema/js/*.js
```
