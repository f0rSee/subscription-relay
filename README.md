<div align="center">

<img src="frontend/public/favicon.svg" width="80" alt="Subscription Relay">

# Subscription Relay

**Единая управляемая подписка поверх нескольких VPN-провайдеров**

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141%2B-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=111)
![Bun](https://img.shields.io/badge/Bun-1.4%2B-14151A?style=flat-square&logo=bun&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-ready-4169E1?style=flat-square&logo=postgresql&logoColor=white)

[Возможности](#возможности) · [Быстрый старт](#быстрый-старт) · [Настройка](#настройка) · [Разработка](#разработка)

</div>

Subscription Relay загружает VPN-подписки у провайдеров, разбирает поддерживаемые URI и собирает из них профили с отдельными публичными ссылками. Источники, состав профилей и порядок серверов меняются через веб-дашборд без правки переменных окружения и перезапуска сервиса.

Поддерживаются `vless`, `vmess`, `trojan`, `ss`, `ssr`, `hysteria`, `hysteria2`, `tuic` и `wireguard`.

## Возможности

- Несколько источников в одном профиле подписки.
- Хотсвап источников и ручная синхронизация из дашборда.
- Визуальная сортировка серверов drag-and-drop для каждого профиля.
- Опциональная дедупликация одинаковых узлов без учёта названия после `#`.
- Автообновление устаревших источников при запросе профиля.
- История запросов и список обнаруженных VPN-клиентов.
- Системная, светлая и тёмная темы интерфейса.
- Шифрование исходных URL в базе и маскирование их в API.
- Cookie-сессия администратора с CSRF-защитой.
- SQLite для локального запуска и PostgreSQL/Neon для постоянного хранения.

## Как это работает

```mermaid
flowchart LR
    A[VPN-провайдеры] -->|HTTPS| B[Синхронизация источников]
    B --> C[(SQLite / PostgreSQL)]
    C --> D[Профили и порядок узлов]
    D --> E[/subscription?token=...]
    D --> F[/s/PROFILE_TOKEN]
    E --> G[VPN-клиент]
    F --> G
    H[React-дашборд] -->|Admin API| C
```

URL источника расшифровывается только перед запросом к провайдеру. Полученные URI также хранятся зашифрованными. Публичный endpoint возвращает обычную Base64-подписку, совместимую с распространёнными VPN-клиентами.

## Быстрый старт

Понадобятся Python 3.11+, Bun 1.4+ и Git.

```bash
git clone https://github.com/f0rSee/subscription-relay.git
cd subscription-relay

python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env
cd frontend
bun install --frozen-lockfile
bun run build
cd ..
```

Сгенерируйте секреты и заполните `.env`:

```bash
openssl rand -hex 24  # RELAY_TOKEN
openssl rand -hex 32  # APP_ENCRYPTION_KEY
openssl rand -hex 32  # SESSION_SECRET
```

Минимальная конфигурация для локального запуска:

```dotenv
UPSTREAM_URL=https://provider.example/subscription?token=original-token
RELAY_TOKEN=replace-with-at-least-16-random-characters
ADMIN_USERNAME=admin
ADMIN_PASSWORD=replace-with-a-long-random-password
APP_ENCRYPTION_KEY=replace-with-a-stable-random-key
SESSION_SECRET=replace-with-another-stable-random-key
SECURE_COOKIES=false
```

Запустите приложение:

```bash
fastapi run --host 127.0.0.1 --port 8000
```

Дашборд будет доступен по адресу <http://127.0.0.1:8000/admin/>.

> [!IMPORTANT]
> Не меняйте `APP_ENCRYPTION_KEY` после сохранения источников: без прежнего ключа сервис не сможет расшифровать их URL.

## Ссылки подписок

Основной профиль использует `RELAY_TOKEN`:

```text
https://relay.example/subscription?token=RELAY_TOKEN
```

Каждый дополнительный профиль получает случайный токен и отдельный URL:

```text
https://relay.example/s/PROFILE_TOKEN
```

Проверить статус и размер ответа без вывода самой подписки:

```bash
curl --fail --silent --show-error \
  --output /dev/null \
  --write-out 'HTTP %{http_code}, %{size_download} bytes\n' \
  'http://127.0.0.1:8000/subscription?token=RELAY_TOKEN'
```

> [!NOTE]
> `UPSTREAM_URL` нужен только для первоначального импорта источника в пустую базу. После этого источниками можно полностью управлять через дашборд.

## Настройка

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `UPSTREAM_URL` | — | Исходная подписка для автоматического импорта в пустую базу |
| `RELAY_TOKEN` | обязательна | Токен основного публичного профиля, минимум 16 символов |
| `ADMIN_USERNAME` | `admin` | Имя администратора дашборда |
| `ADMIN_PASSWORD` | — | Пароль администратора; без него вход отключён |
| `APP_ENCRYPTION_KEY` | `RELAY_TOKEN` | Стабильный ключ шифрования URL и URI |
| `SESSION_SECRET` | `RELAY_TOKEN` | Ключ подписи admin-сессий и идентификаторов устройств |
| `DATABASE_URL` | локальная SQLite | URL SQLite либо PostgreSQL/Neon |
| `SECURE_COOKIES` | `true` | Передавать admin cookie только по HTTPS |
| `SUBSCRIPTION_REFRESH_SECONDS` | `900` | Возраст данных, после которого источник обновляется автоматически |
| `UPSTREAM_TIMEOUT_SECONDS` | `20` | Таймаут запроса к провайдеру, 1–120 секунд |
| `MAX_RESPONSE_BYTES` | `5242880` | Максимальный размер upstream-ответа, 1 КиБ–50 МиБ |
| `ALLOW_INSECURE_HTTP` | `false` | Разрешить источники по незашифрованному HTTP |
| `FRONTEND_DIST` | `frontend/dist` | Каталог production-сборки дашборда |

Для постоянного хранения укажите PostgreSQL URL:

```dotenv
DATABASE_URL=postgresql://user:password@host/database?sslmode=require&channel_binding=require
```

Сервис автоматически переводит `postgres://` и `postgresql://` на асинхронный драйвер и адаптирует TLS-параметры Neon. Таблицы создаются при старте.

Настройки дедупликации, журналирования запросов, учёта устройств и автообновления хранятся в базе и применяются сразу, без перезапуска.

## Архитектура проекта

```text
backend/app/
├── api/              # публичные и защищённые APIRouter-модули
├── services/         # синхронизация, профили, bootstrap и observability
├── asgi.py           # production entrypoint
├── main.py           # фабрика FastAPI-приложения и lifespan
├── dependencies.py   # типизированные Depends-зависимости
├── models.py         # SQLAlchemy ORM
├── schemas.py        # Pydantic-контракты API
└── security.py       # шифрование, сессии и CSRF

frontend/src/         # React 19, TypeScript, ReUI и Vite
tests/                # parser, auth, CSRF, API и сборка профилей
```

Все admin-маршруты объединены под `/api` и защищены общей зависимостью авторизации. Публичные `/healthz`, `/subscription` и `/s/{token}` изолированы в отдельном роутере. FastAPI также раздаёт production-сборку SPA под `/admin/`.

## Разработка

Backend с автообновлением:

```bash
source .venv/bin/activate
fastapi dev --host 127.0.0.1 --port 8000
```

Frontend с HMR запускается в другом терминале:

```bash
cd frontend
bun run dev
```

Откройте <http://127.0.0.1:5173/admin/>. Vite проксирует `/api`, `/healthz`, `/subscription` и `/s` на backend.

Проверки перед коммитом:

```bash
ruff check backend tests
pytest -q

cd frontend
bun run lint
bun run build
```

## Docker

```bash
docker build -t subscription-relay .
docker run --rm -p 8000:10000 --env-file .env subscription-relay
```

После запуска проверьте `GET /healthz`; при доступной базе endpoint вернёт `200` и тип хранилища.

## Безопасность

> [!WARNING]
> Не публикуйте `.env`, исходные URL подписок, `RELAY_TOKEN`, пароль администратора и ключи приложения. Любой, кто знает токен публичного профиля, может получить его подписку.

- Используйте HTTPS и оставляйте `SECURE_COOKIES=true` вне локальной разработки.
- Задавайте отдельные случайные значения для `APP_ENCRYPTION_KEY` и `SESSION_SECRET`.
- Храните production-данные в постоянной PostgreSQL-базе.
- При компрометации ссылки создайте новый профиль и удалите старый.
- Отключите журналирование или учёт устройств, если метаданные запросов не нужны.

## Диагностика

| Симптом | Что проверить |
| --- | --- |
| `Upstream response does not contain supported nodes` | Провайдер вернул не URI-подписку; проверьте исходный URL, статус аккаунта и содержимое ответа |
| `Dashboard assets are not built` | Выполните `cd frontend && bun run build` либо используйте Vite dev server |
| `Stored secret cannot be decrypted` | Приложение запущено с другим `APP_ENCRYPTION_KEY` |
| Данные исчезают после перезапуска | Подключите постоянный `DATABASE_URL` вместо локальной SQLite |
| Вход работает локально, но не по HTTP | Для локального HTTP задайте `SECURE_COOKIES=false`; в production используйте HTTPS |
