# Lumi — пакет для передачи в Claude Code

Этот архив содержит техническое задание и промпты для реализации локального MVP Telegram AI-ассистента **Lumi**.

## Как использовать

1. Создай пустую директорию проекта, например `lumi-assistant`.
2. Распакуй этот архив рядом или внутрь рабочей директории.
3. Открой файл `LUMI_FULL_PROMPT_SINGLE_FILE.md`.
4. Скопируй его целиком в Claude Code.
5. Разреши Claude Code создавать файлы, запускать команды, ставить зависимости, писать Docker Compose, миграции, тесты и документацию.
6. После реализации Claude Code должен попросить у тебя секреты: Telegram bot token, MiniMax API key, Telegram user id, Google OAuth credentials при необходимости.
7. После запуска проекта используй файл `12_POST_IMPLEMENTATION_DOC_PROMPT.md` как отдельный второй промпт: он заставит Claude Code сгенерировать понятную архитектурную документацию уже по фактически написанному коду.

## Главный файл

`LUMI_FULL_PROMPT_SINGLE_FILE.md` — один большой промпт, который можно передать агенту целиком.

## Структура пакета

- `01_MASTER_PROMPT_FOR_CLAUDE_CODE.md` — основной промпт для реализации проекта.
- `02_PRODUCT_SPEC.md` — продуктовый scope MVP.
- `03_ARCHITECTURE_SPEC.md` — архитектура сервисов и потоков.
- `04_BACKEND_SPEC.md` — backend-модули, API, сервисы.
- `05_DATABASE_SCHEMA.md` — схема БД, таблицы, связи.
- `06_LLM_CONTEXT_MEMORY_SPEC.md` — управление контекстом, memory, compaction, промпты.
- `07_CONNECTORS_SPEC.md` — Google Gmail/Calendar, новости, коннекторы.
- `08_FRONTEND_MINI_APP_UI_SPEC.md` — Mini App UI, дизайн, экраны.
- `09_LOCAL_DEPLOYMENT_DOCKER_SPEC.md` — локальный запуск, Docker, Makefile, tunnel.
- `10_SECURITY_PRIVACY_SPEC.md` — безопасность, allowlist, secrets, permissions.
- `11_TESTING_ACCEPTANCE_CHECKLIST.md` — тесты и definition of done.
- `12_POST_IMPLEMENTATION_DOC_PROMPT.md` — второй промпт для генерации архитектурного документа после реализации.
- `13_ENV_TEMPLATE.md` — шаблон `.env.example`.
- `99_SOURCES.md` — официальные источники, на которые опирается задание.
