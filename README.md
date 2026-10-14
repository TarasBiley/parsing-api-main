# Сервис получения квот с сайтов

Сервис предоставляет API для запуска задач по получению квот с сайтов и их дальнейшей передачи в основной сервис

### Локальный запуск

Для локального запуска необходимо:

1. Иметь запущенный локальный запущенный сервис или использовать дев стенд

2. Склонировать репозиторий

3. Скопировать настройки переменных окружения из .env.example в .env и настроить их:
```shell
cp .env.example .env
```

4. Создать файл [whitelist.conf](src/nginx_config/whitelist.conf) по пути "src/nginx_config/whitelist.conf"

5. Запустить проект через docker-compose
```shell
docker compose up docker-compose.yml
```

6. После запуска сервиса необходимо вручную добавить куки для cайта DASI 
(через swagger /api/openapi#/orders/dasi_cookies_api_v1_orders_dasi_cookies__post или 
api POST /api/v1/orders/dasi_cookies/)

Основной сервис отправляет парт-номера для поиска при создании новых RFQ

## Переменные окружения

| Переменная              | Описание                                             | Пример                   | Обязательность|
|-------------------------|------------------------------------------------------|--------------------------|---------------|
| `MAIN_SERVER`           | Адрес основного сервиса                              | http://localhost:8000    | +             |
| `REDIS`                 | Адрес для подключения к redis                        | redis://parse_redis:6379 | +             |
| `REDIS_HOST`            | Хост для подключения к redis                         | parse_redis              | +             |
| `REDIS_PORT`            | Порт для подключения к redis                         | 6379                     | +             |
| `AVIATOR_USER_NAME`     | Логин для аутентификации на основном сервисе         | user_name                | +             |
| `AVIATOR_PASSWORD`      | Пароль для аутентификации на основном сервисе        | password                 | +             |
| `AVIATOR_CODE`          | Секретный код для аутентификации на основном сервисе | 123456                   | +             |
| `AEROBAY_USER_NAME`     | Логин для сервиса                                    | user_name                | +             |
| `AEROBAY_PASSWORD`      | Пароль для сервиса                                   | password                 | +             |
| `AVIOSUPPORT_USER_NAME` | Логин для сервиса                                    | user_name                | +             |
| `AVIOSUPPORT_PASSWORD`  | Пароль для сервиса                                   | password                 | +             |
| `ECSAT_USER_NAME`       | Логин для сервиса                                    | user_name                | +             |
| `ECSAT_PASSWORD`        | Пароль для сервиса                                   | password                 | +             |
| `DASI_USER_NAME`        | Логин для сервиса                                    | user_name                | +             |
| `DASI_PASSWORD`         | Пароль для сервиса                                   | password                 | +             |
| `PROPONENT_USER_NAME`   | Логин для сервиса                                    | user_name                | +             |
| `PROPONENT_PASSWORD`    | Пароль для сервиса                                   | password                 | +             |
| `SATAIR_USER_NAME`      | Логин для сервиса                                    | user_name                | +             |
| `SATAIR_PASSWORD`       | Пароль для сервиса                                   | password                 | +             |
| `WENCOR_USER_NAME`      | Логин для сервиса                                    | user_name                | +             |
| `WENCOR_PASSWORD`       | Пароль для сервиса                                   | password                 | +             |
| `AVIALL_USER_NAME`      | Логин для сервиса                                    | user_name                | +             |
| `AVIALL_PASSWORD`       | Пароль для сервиса                                   | password                 | +             |
| `BDSI_USER_NAME`        | Логин для сервиса                                    | user_name                | +             |
| `BDSI_PASSWORD`         | Пароль для сервиса                                   | password                 | +             |
| `LOG_LEVEL`             | Уровень логирования                                  | INFO                     | -             |
| `AIRPORTS`              | Место расположения файла с аэропортами               | parsers/airports.json    | -             |
