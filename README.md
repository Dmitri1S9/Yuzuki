# Yuzuki

Сервис для автоматической аналитики персонажей из аниме/манги/фантастических вселенных. Использует Grok (xAI) для ранжирования и профилирования персонажей, хранит результаты в PostgreSQL через Celery-воркеры.

---

## Что сделано

### Ядро

- **`UniverseBuilder`** — оркестратор, который принимает вселенную + список персонажей + арку и запускает все задачи параллельно через Celery:
  - 1 задача `profile_task` — базовые данные персонажей
  - 7 задач `rank_task` — ординальные параметры
  - ~52 задачи `flag_task` — бинарные флаги

- **`XClient`** — клиент к xAI API (`grok-4-1-fast-reasoning`), с Redis-кешированием ответов (TTL 24ч). Три метода: `rank`, `flag`, `profile`.

- **Prompts** (`prompts_ordinal_v2/`) — Jinja2-шаблоны для системных и пользовательских промптов ранкера, флаггера и профайлера.

### Параметры

**Ординальные (7)** — каждый персонаж получает позицию в отсортированном списке:
- `combat_potential`, `intellect`, `authority_scope`, `loyalty_command`, `social_impact`, `lawfulness`, `wealth`

**Флаги (52)** — позиция в списке относительно маркеров T0/T1 (до / между / после):

| Категория | Флаги |
|-----------|-------|
| Личность | manipulative, honest, impulsive, secretive, self_sacrificing, adaptable, loyal, empathetic, cruel, arrogant, competitive, ruthless |
| Роль | is_leader, is_strategist, is_mentor, is_villain, is_antihero |
| Внешность | is_physically_attractive, is_intimidating |
| Мотивация | goal_power, goal_love, goal_knowledge, goal_revenge, goal_survival, goal_duty, goal_freedom, goal_recognition, goal_protection |
| Домен | military, politics, science, art, education, crime, commerce |
| Состояние | has_magic, has_tragic_past, is_strong_willed, is_provocative, is_loner, is_unstable, is_fanatical |
| Мировоззрение | is_idealist, is_nihilist, is_pragmatist, is_duty_driven, is_hedonist, is_machiavellian, is_revolutionary, is_fatalist |
| Слабости | has_physical_weakness, has_psychological_weakness |

**Профиль** — `body_age`, `soul_age`, `gender`, `species`

### База данных (плоская схема, 2 таблицы)

- **`universes`** — одна строка на вселенную+арку. Каждый параметр — JSONB-массив с количеством персонажей по сегментам (тирам).
- **`characters`** — одна строка на персонажа. Каждый параметр — INT (позиция в отсортированном списке, NULL = неизвестно).

### Инфраструктура

- **FastAPI** — запущен на порту 8000/8044
- **Celery** — брокер и бэкенд на Redis (`redis://...6379/0`), воркеры с concurrency=3, авторестарт через `watchfiles`
- **Redis** — отдельная БД для кеша ответов xAI (`6379/1`)
- **PostgreSQL 14** — порт 5439 (хост) → 5432 (контейнер), БД `archangel`
- **Docker Compose** — 4 сервиса: `db`, `redis`, `analyse_service`, `celery_worker`

---

## Первый запуск

### Через Docker

```bash
docker-compose up --build
```

БД инициализируется автоматически из `db/init.sql`.

### Локально (Celery-воркер)

```bash
celery -A app.settings.celery_app:celery worker -l INFO
```

БД при этом всё равно поднимается в Docker.

### Запуск сбора вселенной

```python
from app.universe_builder import UniverseBuilder

builder = UniverseBuilder("Classroom of the Elite", COTE_CHARACTERS, arc="Year 1")
builder.collect_universe()
```

---

## Переменные окружения (`.env`)

| Переменная | Описание |
|------------|----------|
| `API_KEY_X` | Ключ xAI API |
| `API_KEY` | Ключ OpenAI (не используется активно) |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL |
| `REDIS_URL_CELERY` | Redis для Celery-брокера |
| `REDIS_URL_CACHE` | Redis для кеша xAI-ответов |
| `DEBUG` | Режим отладки |

---

## Структура проекта

```
app/
  apiClients/
    clientX.py          # xAI клиент (rank / flag / profile)
    schemas/
      ranker_schema.py  # RankingResponse
      profiler_schema.py# ProfileResponse / CharacterProfile
  data/
    data.py             # get_prompt() — рендеринг Jinja2
    flags.json          # определения флагов (definition + sort_axis)
    prompts_ordinal_v2/ # шаблоны промптов
  settings/
    config.py           # Settings (pydantic-settings)
    celery_app.py       # инициализация Celery
    redis.py            # redis_cache
    logger_setup.py
  tasks.py              # rank_task / flag_task / profile_task
  universe_builder.py   # UniverseBuilder + список персонажей COTE
  main.py               # FastAPI app
  tests/
    test_db.py

db/
  init.sql              # DDL — создание таблиц
  service.py            # CRUD: create_universe, save_rank/flag/profile_result, getters
  schema_reference.md   # устаревший референс (предыдущая схема)

docker-compose.yaml
Dockerfile
analyse.yml             # Conda environment
```
