# Subscription Relay

Небольшой relay для VPN-подписки. Сервис запрашивает один заранее заданный URL
подписки и возвращает ответ клиенту без изменения содержимого. Пользователь не
может подставить другой upstream URL, поэтому сервис не становится открытым
HTTP-прокси.

## Развёртывание на Render

1. Создайте закрытый репозиторий GitHub/GitLab и загрузите в него эти файлы.
2. В Render выберите **New → Blueprint**, подключите репозиторий и примените
   найденный `render.yaml`.
3. При создании Render попросит значения двух секретных переменных:
   - `UPSTREAM_URL` — полная исходная ссылка подписки, включая её token/query;
   - `RELAY_TOKEN` — отдельный случайный секрет длиной от 16 символов.
4. Сгенерировать секрет можно локально:

   ```sh
   openssl rand -hex 24
   ```

5. После успешного деплоя добавьте в VPN-клиент новую ссылку:

   ```text
   https://subscription-relay.onrender.com/subscription?token=ВАШ_RELAY_TOKEN
   ```

   Замените домен на адрес, который Render назначил вашему сервису. Если в
   секрете есть `+`, `/`, `=` или другие специальные символы, URL-кодируйте его;
   hex-секрет из команды выше кодировать не нужно.

Проверка состояния сервиса доступна без секрета:

```text
https://subscription-relay.onrender.com/healthz
```

## Локальный запуск

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Заполните в `.env` полный исходный URL и отдельный случайный токен:

```dotenv
UPSTREAM_URL=https://provider.example/subscription?token=original-token
RELAY_TOKEN=вставьте-сюда-результат-openssl
```

Сгенерировать `RELAY_TOKEN` можно командой `openssl rand -hex 24`. Не используйте
для него токен из исходной ссылки подписки. Запустите relay:

```sh
uvicorn app:app --env-file .env --host 127.0.0.1 --port 8000 --no-access-log
```

В другом терминале загрузите переменные и проверьте ответ, не печатая саму
подписку:

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

Если `UPSTREAM_URL` содержит `&` или другие shell-символы, заключите всё
значение в одинарные кавычки в `.env`. Для VPN-клиента используйте обычную ссылку
`http://127.0.0.1:8000/subscription?token=ВАШ_RELAY_TOKEN`.

Автоматические тесты запускаются командой:

```sh
python -m pytest -q
```

## Авторизация и настройки

Для обычного VPN-клиента проще всего передавать `RELAY_TOKEN` в query-параметре
`token`. Также поддерживаются заголовки `X-Relay-Token` и
`Authorization: Bearer ...`.

Опциональные переменные:

| Переменная | По умолчанию | Назначение |
|---|---:|---|
| `UPSTREAM_TIMEOUT_SECONDS` | `20` | Таймаут запроса, от 1 до 120 секунд |
| `MAX_RESPONSE_BYTES` | `5242880` | Максимальный ответ, от 1 КиБ до 50 МиБ |
| `ALLOW_INSECURE_HTTP` | `false` | Разрешить upstream по незашифрованному HTTP |

Relay передаёт upstream-запросу только `User-Agent` и `Accept` клиента. Он не
передаёт IP-адрес пользователя, cookies или заголовки Render. Из ответа
сохраняются содержимое, HTTP-статус и заголовки, используемые VPN-клиентами
(`Subscription-Userinfo`, `Profile-Update-Interval` и другие). Кэширование
принудительно отключено.

Не публикуйте `.env`, исходный URL и relay-токен. Если relay-ссылка утекла,
замените `RELAY_TOKEN` в Render и обновите ссылку в VPN-клиенте.

> Важно: `.env.example` — только публичный шаблон. Настоящие значения должны
> находиться в `.env`, который уже добавлен в `.gitignore`. Перед первым коммитом
> проверьте это командой `git check-ignore .env`.

Актуальная документация: [Render Blueprints](https://render.com/docs/blueprint-spec)
и [Docker on Render](https://render.com/docs/docker).
