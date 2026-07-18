# BotTrade

BotTrade - асинхронный Telegram-сервис для отслеживания инструментов T-Bank Invest.
Сервис хранит watchlist в PostgreSQL, получает рыночные события из T-Bank streams,
считает уровни Donchian/ATR и отправляет торговые уведомления в Telegram.

Архитектура уже подготовлена к нескольким внешним интерфейсам. Сейчас реализован
Telegram-бот; FastAPI или отдельные worker-процессы можно добавлять через тот же
application layer и Redis-шину.

## Назначение

Сервис решает несколько задач:

- подключается к T-Bank Invest API через `t-tech-investments`;
- позволяет добавлять счета и избранные инструменты в отслеживание;
- отфильтровывает денежные инструменты портфеля, например RUB и инструменты хранения денег;
- рассчитывает Donchian 55/20 и ATR(14) по завершенным дневным свечам;
- подписывается на `last_price` stream по активным инструментам;
- отправляет Telegram-уведомления о пробоях и стоп-сигналах;
- хранит счета, инструменты, позиции, уровни, флаги уведомлений, имена и последние цены;
- использует Redis Streams как шину сообщений между producer-ами стримов и обработчиками;
- поддерживает sandbox helpers для проверки выставления заявок.

## Команды Telegram

```text
/start
/help
/add_account_check
/remove_account_check
/add_instruments_for_check
/uncheck_instruments
/info
/check_notify
/instr_info
```

Основные сценарии:

- `/add_account_check` - выбрать инвестиционный счет, загрузить портфель, сохранить торговые
  инструменты, рассчитать уровни и подписаться на последние цены.
- `/add_instruments_for_check` - выбрать инструменты из избранного T-Bank. Инструменты быстро
  сохраняются и сразу показываются в Telegram; загрузка свечей и пересчет уровней идут в фоне.
- `/uncheck_instruments` - отключить отслеживание инструментов, которые не находятся в позициях
  отслеживаемых счетов.
- `/info`, `/check_notify`, `/instr_info` - посмотреть состояние отслеживания, флаги уведомлений
  и расчетные уровни по инструменту.

## Архитектура

Код разделен по слоям:

```text
BotTrade/
├── application/              # Use cases: watchlist, instrument info
├── bots/tg_bot/              # Telegram adapter: handlers, keyboards, messages, middleware
├── clients/tinkoff/          # T-Bank adapter и слой совместимости SDK
├── core/domains/             # MessageBus, Redis Streams bus, event codec
├── core/schemas/             # Обработчики market/portfolio stream events
├── database/pgsql/           # SQLAlchemy models и repository
├── database/redis/           # Redis client и cache helpers
├── domain/                   # Чистые DTO и бизнес-правила
├── services/                 # Индикаторы и scheduler helpers
├── tests/                    # Unit tests
├── config.example.yaml       # Безопасный пример конфига
├── config.py                 # Pydantic-схема конфига
└── main.py                   # Сборка и запуск сервиса
```

Границы слоев:

- `domain/` не зависит от SDK, Telegram, Redis и SQLAlchemy.
- `application/` содержит бизнес-сценарии и работает через ports/protocols.
- `clients/tinkoff/` знает о T-Bank SDK и преобразует SDK-объекты в DTO проекта.
- `bots/tg_bot/` отвечает только за Telegram-интерфейс: команды, callback-и, клавиатуры.
- `core/domains/message_bus.py` задает контракт шины сообщений.
- `RedisStreamBus` используется по умолчанию, а `StreamBus` на `asyncio.Queue` оставлен как
  memory backend для локальной отладки.

## Поток Событий

Путь market/portfolio events:

```text
T-Bank gRPC stream
  -> TinkoffStreamManager
  -> clients/tinkoff/stream_mappers.py
  -> domain/stream_events.py DTO
  -> RedisStreamBus.publish(...)
  -> Redis Streams XADD
  -> Redis consumer group XREADGROUP
  -> MarketDataHandler / PortfolioHandler
  -> XACK
```

SDK-события не отправляются в Redis напрямую. Сначала они мапятся в собственные DTO:

- `ti.MarketDataResponse` -> `LastPriceEvent`, `CandleEvent`, `TradeEvent`,
  `LastPriceSubscriptionEvent`;
- `ti.PortfolioStreamResponse` -> `PortfolioSnapshotEvent`.

Сообщение в Redis хранится как JSON envelope:

```text
event_type = market.last_price
version = 1
payload = {"instrument_id":"UID1","price":"100.25","time":"2026-07-18T00:00:00+03:00"}
```

Такой формат можно читать из FastAPI, отдельных Python worker-ов или другого сервиса без
импорта T-Bank SDK.

Правила Redis consumer groups:

- один `message-bus.group` распределяет события между consumer-ами как очередь задач;
- разные `message-bus.group` позволяют нескольким сервисам получать одни и те же события;
- стабильный `message-bus.consumer` помогает подбирать pending-сообщения после рестарта.

## Конфигурация

Создайте локальный конфиг из примера:

```bash
cp config.example.yaml config.yaml
```

Файлы с реальными токенами игнорируются Git:

- `config.yaml`
- `test_config.yaml`

Не коммитьте реальные токены.

Основные секции:

```yaml
tinkoff-client:
  token: "replace-with-read-token"
  sandbox-token: "replace-with-sandbox-token"
  sandbox: false
  app-name: "bottrade"

tg-bot:
  token: "replace-with-telegram-token"
  chat_id: 123456789
  proxy: null

db-pgsql:
  address: "postgresql+asyncpg://postgres:postgres@db:5432/data_positions"

redis:
  host: redis
  port: 6379
  db: 0
  password: null
  ssl: false
  decode_responses: true
  socket_timeout: 5
  retry_on_timeout: true

message-bus:
  backend: redis
  stream-prefix: bottrade:bus
  group: bottrade
  consumer: telegram-1
  start-id: "$"
  batch-size: 10
  block-ms: 1000
  maxlen: 10000

name-cache:
  ttl: 86400
  namespace: names
```

Для локальной отладки без Redis Streams можно явно включить memory backend:

```yaml
message-bus:
  backend: memory
```

По умолчанию `config.py` выбирает Redis backend.

## Локальный Запуск

Требования:

- Python 3.13;
- PostgreSQL;
- Redis;
- T-Bank Invest token;
- Telegram bot token.

Установка зависимостей:

```bash
python3.13 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Запуск:

```bash
python main.py --config config.yaml
```

При старте сервис создает таблицы PostgreSQL, если они еще не существуют.

## Docker

Dev-окружение:

```bash
docker compose -f docker-compose.dev.yml up --build
```

Разовый прогон тестов в dev-образе:

```bash
docker compose -f docker-compose.dev.yml run --rm --no-deps master_bot python -m pytest -q
```

Production compose:

```bash
docker compose -f docker-compose.yml up -d
```

Оба compose-файла поднимают PostgreSQL и Redis. Dev-compose монтирует локальный проект в
контейнер и использует `test_config.yaml`.

## Sandbox

Sandbox включается в конфиге:

```yaml
tinkoff-client:
  sandbox: true
  sandbox-token: "replace-with-sandbox-token"
```

В sandbox mode:

- чтение счетов и портфеля идет через sandbox services;
- portfolio stream не запускается;
- доступны helpers для открытия sandbox-счета, пополнения и выставления sandbox-заявки;
- production-only операции защищены guard-методами.

## Хранилища

PostgreSQL хранит:

- `accounts` - выбранные инвестиционные счета;
- `instruments` - UID, ticker, флаги отслеживания, Donchian/ATR, expiration date;
- `account_instruments` - связь счета с инструментом и направление позиции.

Redis хранит:

- последние цены с защитой по timestamp;
- кеш имен инструментов;
- кеш метрик портфеля;
- Redis Streams для `RedisStreamBus`.

## Логика Сигналов

Чистые правила находятся в `domain/signals.py`.

Условия:

- нет позиции и цена >= Donchian long 55: breakout long;
- нет позиции и цена <= Donchian short 55: breakout short;
- long-позиция и цена <= Donchian short 20: stop long;
- short-позиция и цена >= Donchian long 20: stop short.

Handlers отвечают за IO: читают БД, обновляют notify-флаги, резолвят имена и отправляют
Telegram-сообщения.

## Тесты

Запуск всех тестов:

```bash
.venv/bin/pytest -q
```

Style check для измененных файлов:

```bash
.venv/bin/flake8 <files>
```

Покрытые зоны:

- принятие торговых сигналов;
- watchlist use cases;
- совместимость с T-Bank SDK и mapper-ы;
- JSON event codec и Redis Streams bus;
- Telegram handlers для счетов и избранного;
- обработка market data events.

Во время тестов могут появляться SDK warnings про deprecated `figi`. Сервис предпочитает UID,
но сохраняет fallback для старых контрактов.

## Операционные Заметки

- `config.yaml` и `test_config.yaml` игнорируются, потому что содержат токены.
- `config.example.yaml` - единственный конфиг, который можно безопасно коммитить.
- Если Telegram callback выглядит как зависший, сначала проверьте логи T-Bank запросов и старт
  Redis bus.
- Добавление избранных разделено на быстрый save и фоновый refresh уровней, чтобы пользователь
  не ждал все запросы свечей.
- Для нескольких API-сервисов используйте разные `message-bus.group`, если каждый сервис должен
  получать все события.
