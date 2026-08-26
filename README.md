# Subscription Relay

Relay с веб-дашбордом для нескольких VPN-подписок. Сервис забирает подписки у
провайдеров, извлекает поддерживаемые серверы, при необходимости удаляет
дубликаты и выдаёт их как одну подписку. Дедупликация настраивается и по
умолчанию выключена. В дашборде
можно добавлять источники без перезапуска, создавать отдельные профили, менять
порядок серверов перетаскиванием, просматривать запросы и устройства.

Поддерживаются URI `vless`, `vmess`, `trojan`, `ss`, `ssr`, `hysteria`,
`hysteria2`, `tuic` и `wireguard`. URL источников зашифрованы в базе и после
сохранения возвращаются браузеру только в замаскированном виде.

## Структура

```text
backend/app/        FastAPI, SQLAlchemy, синхронизация и сборка подписок
frontend/src/       React-дашборд на Bun/Vite и компонентах ReUI
tests/              API, parser, auth/CSRF и порядок серверов
app.py              ASGI entrypoint для обратной совместимости
```

## Локальный запуск

Нужны Python 3.11+ и Bun. Подготовьте окружение:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
cd frontend
bun install
bun run build
cd ..
```

Заполните `.env`. Для первого запуска достаточно SQLite:

```dotenv
UPSTREAM_URL=https://provider.example/subscription?token=original-token
RELAY_TOKEN=результат-openssl-rand-hex-24
ADMIN_USERNAME=admin
ADMIN_PASSWORD=длинный-случайный-пароль
APP_ENCRYPTION_KEY=результат-openssl-rand-hex-32
SESSION_SECRET=другой-результат-openssl-rand-hex-32
SECURE_COOKIES=false
```

`UPSTREAM_URL` нужен только для автоматического импорта существующей подписки.
После первого запуска источники добавляются через дашборд, поэтому менять env для
хотсвапа не требуется. Ключ `APP_ENCRYPTION_KEY` после заполнения базы менять
нельзя: без него ранее сохранённые URL не расшифруются.

Запустите приложение:

```sh
uvicorn app:app --env-file .env --host 127.0.0.1 --port 8000 --no-access-log
```

Дашборд откроется по адресу `http://127.0.0.1:8000/admin`. Для разработки
фронтенда с HMR запустите `bun run dev` в каталоге `frontend`; Vite проксирует API
на порт 8000.

## Ссылки подписок

Существующая ссылка остаётся совместимой:

```text
http://127.0.0.1:8000/subscription?token=RELAY_TOKEN
```

Каждый созданный в дашборде профиль получает собственную ссылку вида
`/s/СЛУЧАЙНЫЙ_ТОКЕН`. Она объединяет выбранные источники и сохраняет заданный
порядок серверов. Если включить дедупликацию в настройках, повторы определяются
без учёта названия после `#`.

В разделе «Настройки» без перезапуска управляются дедупликация, логи запросов,
учёт устройств и автообновление устаревших источников. Логи не содержат токены
профилей; устройство определяется по комбинации IP-адреса и User-Agent.

Проверить ответ без вывода содержимого:

```sh
set -a
. ./.env
set +a
curl --fail --silent --show-error \
  --header "X-Relay-Token: $RELAY_TOKEN" \
  --output /dev/null \
  --write-out 'HTTP %{http_code}, %{size_download} bytes\n' \
  http://127.0.0.1:8000/subscription
```

## Постоянная база

По умолчанию используется `subscription_relay.db`. Для постоянного хранения
подключите PostgreSQL, например Neon:

```dotenv
DATABASE_URL=postgresql://user:password@host/database?sslmode=require&channel_binding=require
```

Обычные URL `postgres://` и `postgresql://` автоматически переводятся на
асинхронный драйвер. Таблицы создаются при старте. Если база временная, дашборд
явно показывает предупреждение.

## Проверки

```sh
python -m pytest -q
cd frontend
bun run build
bun run lint
```

Основные настройки:

| Переменная | По умолчанию | Назначение |
|---|---:|---|
| `DATABASE_URL` | SQLite | PostgreSQL/Neon или локальная база |
| `SUBSCRIPTION_REFRESH_SECONDS` | `900` | Интервал фонового обновления при запросе профиля |
| `UPSTREAM_TIMEOUT_SECONDS` | `20` | Таймаут запроса, от 1 до 120 секунд |
| `MAX_RESPONSE_BYTES` | `5242880` | Максимальный ответ, от 1 КиБ до 50 МиБ |
| `ALLOW_INSECURE_HTTP` | `false` | Разрешить источник по незашифрованному HTTP |
| `SECURE_COOKIES` | `true` | Передавать admin cookie только по HTTPS |

Не публикуйте `.env`, исходные URL, пароль администратора и relay-токены.
Настоящие значения уже исключены через `.gitignore`.
