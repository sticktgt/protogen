# План синхронизации UI-схемы

## 1. Текущая структура UI-схемы

### Страницы (schema.json):
1. auth.login - Вход в систему
2. home - Главная
3. products.overview - Банковские продукты
4. accounts.list - Список счетов
5. payments.transfer - Перевод между своими счетами
6. deposits.open - Открытие депозита
7. credits.apply - Заявка на кредит
8. analytics.spending - Аналитика трат
9. cards.block - Блокировка карты

### Меню (app.json):
- app.main_menu.products (Продукты)
  - products.overview
  - accounts
  - deposits
  - credits
- app.main_menu.payments (Платежи)
  - transfer
- app.main_menu.cards (Карты)
  - block
- app.main_menu.analytics (Аналитика)
  - spending

## 2. Анализ требований (REQ-0001 — REQ-0108)

### Группы требований:

**GRP-AUTH (Авторизация): REQ-0001 — REQ-0007**
- REQ-0001: Вход клиента — UI: auth.login страница, форма входа
- REQ-0002: Страница входа — UI: auth.login страница
- REQ-0003: Проверка обязательности полей — UI: auth.login.form
- REQ-0004: Сообщение об ошибке — UI: auth.login
- REQ-0005: Выход — UI: верхняя панель (нужно добавить)
- REQ-0006: Данные клиента — no_ui (данные)
- REQ-0007: Профиль в верхней панели — UI: нужно добавить верхнюю панель

**GRP-NAV (Навигация): REQ-0008 — REQ-0018**
- REQ-0008: Главная страница — UI: home
- REQ-0009: Главное меню — UI: app.main_menu
- REQ-0010: Корневой layout — UI: общая структура
- REQ-0011: Приветствие — UI: home.header.greeting
- REQ-0012: Сводка по счетам — UI: home.summary_grid
- REQ-0013: Быстрые действия — UI: home.quick_actions
- REQ-0014: Последние операции — UI: home (нужно добавить список операций)
- REQ-0015: Ошибки загрузки — no_ui (общее поведение)
- REQ-0016: Пустые состояния — no_ui (общее поведение)
- REQ-0017: Формат сумм — no_ui (общее поведение)
- REQ-0018: Формат дат — no_ui (общее поведение)

**GRP-PRODUCTS (Продукты): REQ-0019 — REQ-0024**
- REQ-0019: Каталог продуктов — UI: products.overview
- REQ-0020: Карточка "Счета" — UI: products.overview.accounts_card
- REQ-0021: Карточка "Вклады" — UI: products.overview.deposits_card
- REQ-0022: Карточка "Кредиты" — UI: products.overview.credits_card
- REQ-0023: Карточка "Карты" — UI: products.overview.cards_card
- REQ-0024: Данные продукта — no_ui (данные)

**GRP-ACCOUNTS (Счета): REQ-0025 — REQ-0036**
- REQ-0025: Список счетов — UI: accounts.list
- REQ-0026: Таблица счетов — UI: accounts.list.table
- REQ-0027: Панель фильтров — UI: accounts.list.filters
- REQ-0028: Панель деталей — UI: accounts.list.details (нужно проверить)
- REQ-0029: Данные счета — no_ui (данные)
- REQ-0030: Номер счета — no_ui (данные)
- REQ-0031: Баланс и остаток — no_ui (данные)
- REQ-0032: Статус счета — no_ui (данные)
- REQ-0033: Связь клиента и счетов — no_ui (данные)
- REQ-0034: Операции по счету — UI: связано с home, analytics, reports
- REQ-0035: Направление операции — no_ui (данные)
- REQ-0036: Категория операции — no_ui (данные)

**GRP-PAYMENTS (Переводы): REQ-0037 — REQ-0047**
- REQ-0037: Перевод между счетами — UI: payments.transfer
- REQ-0038: Форма перевода — UI: payments.transfer.form
- REQ-0039: Выбор счета списания — UI: payments.transfer.from_account
- REQ-0040: Выбор счета зачисления — UI: payments.transfer.to_account
- REQ-0041: Сумма перевода — UI: payments.transfer.amount
- REQ-0042: Валюта перевода — no_ui (данные)
- REQ-0043: Комментарий — UI: payments.transfer.comment
- REQ-0044: Модальное окно подтверждения — UI: нужно добавить modal
- REQ-0045: Данные перевода — no_ui (данные)
- REQ-0046: Статус перевода — no_ui (данные)
- REQ-0047: Операции после перевода — no_ui (данные)

**GRP-DEPOSITS (Вклады): REQ-0048 — REQ-0058**
- REQ-0048: Открытие вклада — UI: deposits.open
- REQ-0049: Мастер открытия — UI: deposits.open (нужно добавить wizard)
- REQ-0050: Счет списания — UI: deposits.open.source_account
- REQ-0051: Сумма вклада — UI: deposits.open.amount
- REQ-0052: Валюта вклада — UI: deposits.open.currency
- REQ-0053: Срок вклада — UI: deposits.open.term
- REQ-0054: Капитализация — UI: deposits.open.capitalization
- REQ-0055: Ставка вклада — UI: deposits.open.calculator.rate
- REQ-0056: Данные заявки — no_ui (данные)
- REQ-0057: Статус заявки — no_ui (данные)
- REQ-0058: Связь клиента и заявок — no_ui (данные)

**GRP-CREDITS (Кредиты): REQ-0059 — REQ-0067**
- REQ-0059: Подача заявки — UI: credits.apply
- REQ-0060: Форма заявки — UI: credits.apply.wizard
- REQ-0061: Сумма кредита — UI: credits.apply.requested_amount
- REQ-0062: Срок кредита — UI: credits.apply.term
- REQ-0063: Ежемесячный доход — UI: credits.apply.income
- REQ-0064: Страхование — UI: нужно добавить checkbox
- REQ-0065: Данные заявки — no_ui (данные)
- REQ-0066: Статус заявки — no_ui (данные)
- REQ-0067: Связь клиента и заявок — no_ui (данные)

**GRP-CARDS (Карты): REQ-0068 — REQ-0076**
- REQ-0068: Список карт — UI: нужна страница cards.list (отсутствует!)
- REQ-0069: Данные карты — no_ui (данные)
- REQ-0070: Связь счета и карт — no_ui (данные)
- REQ-0071: Блокировка карты — UI: cards.block
- REQ-0072: Форма блокировки — UI: cards.block.form
- REQ-0073: Причина блокировки — UI: cards.block.reason
- REQ-0074: Комментарий — UI: cards.block.comment
- REQ-0075: Модальное окно — UI: cards.block.confirm_modal
- REQ-0076: Сообщение об успехе — UI: нужно добавить

**GRP-ANALYTICS (Аналитика): REQ-0077 — REQ-0083**
- REQ-0077: Аналитика трат — UI: analytics.spending
- REQ-0078: Страница аналитики — UI: analytics.spending
- REQ-0079: Фильтр периода — UI: analytics.spending.filters
- REQ-0080: Фильтр счета — UI: analytics.spending.account
- REQ-0081: Данные категории — no_ui (данные)
- REQ-0082: Список категорий — UI: analytics.spending.by_category
- REQ-0083: Операции для аналитики — no_ui (данные)

**GRP-REPORTS (Отчеты): REQ-0084 — REQ-0087**
- REQ-0084: Выписка по счету — UI: нужна страница reports.statement (отсутствует!)
- REQ-0085: Фильтры выписки — UI: reports.statement (нужно создать)
- REQ-0086: Отображение операций — UI: reports.statement
- REQ-0087: Итоги выписки — UI: reports.statement

**GRP-API (Интеграции): REQ-0088 — REQ-0103**
- REQ-0088: Справочник валют — no_ui (данные/API)
- REQ-0089: Статусы счетов — no_ui (данные)
- REQ-0090: Статусы карт — no_ui (данные)
- REQ-0091: Причины блокировки — no_ui (данные)
- REQ-0092: Статусы заявок — no_ui (данные)
- REQ-0093 — REQ-0103: API endpoints — no_ui (API)

**Навигация: REQ-0104 — REQ-0108**
- REQ-0104: Переход со счета к переводу — UI: accounts.list → payments.transfer
- REQ-0105: Переход с карты к блокировке — UI: нужна cards.list → cards.block
- REQ-0106: Блокировка в меню — UI: app.main_menu.cards.block (есть)
- REQ-0107: Вклады в меню — UI: app.main_menu.products.deposits (есть)
- REQ-0108: Кредиты в меню — UI: app.main_menu.products.credits (есть)

## 3. Необходимые изменения

### Новые страницы:
1. **cards.list** — Список карт (требуется REQ-0068)
2. **reports.statement** — Выписка по счету (требуется REQ-0084)

### Обновления существующих страниц:
1. **home** — добавить список последних операций (REQ-0014)
2. **payments.transfer** — добавить модальное окно подтверждения (REQ-0044)
3. **credits.apply** — добавить checkbox страхования (REQ-0064)
4. **cards.block** — добавить сообщение об успехе (REQ-0076)
5. **deposits.open** — добавить wizard шаги (REQ-0049)

### Обновления меню (app.json):
- Добавить пункт "Счета" → accounts.list
- Добавить пункт "Карты" → cards.list (новый)
- Добавить пункт "Выписки" → reports.statement (новый)

### Обновления связей (links.json):
- Добавить связи для новых страниц
- Обновить связи навигации

### Обновления mappings/requirement_ui_links.json:
- Создать связи для всех 108 требований

## 4. Требования без UI (no_ui)
- REQ-0006, REQ-0015, REQ-0016, REQ-0017, REQ-0018
- REQ-0024, REQ-0029, REQ-0030, REQ-0031, REQ-0032, REQ-0033, REQ-0035, REQ-0036
- REQ-0042, REQ-0045, REQ-0046, REQ-0047
- REQ-0056, REQ-0057, REQ-0058
- REQ-0065, REQ-0066, REQ-0067
- REQ-0069, REQ-0070
- REQ-0081, REQ-0083
- REQ-0088, REQ-0089, REQ-0090, REQ-0091, REQ-0092
- REQ-0093 — REQ-0103 (API)
