# Yuzuki

Сервис для автоматической аналитики персонажей из аниме/манги/фантастических
вселенных: ростер, группы, ординальные ранги, бинарные флаги и попарные
отношения — через Gemini, с сохранением в PostgreSQL.

---

## Пайплайн

Четыре независимых этапа, каждый — отдельный процесс (`docker compose run`),
без общей памяти между ними. Подробная логика каждого этапа — в
[PIPELINE.md](PIPELINE.md); архитектура кода (слои, конвенции) — в
[ARCHITECTURE.md](ARCHITECTURE.md).

1. **Cast** (`src/services/collection/cast`) — собирает ростер и
   средние/большие группы (медиум/лардж/изоляты, по 3 прохода), разрешает
   написания и алиасы имён.
2. **Relations** (`src/services/collection/relations`) — попарные отношения
   (`for`/`against`/`want`/`with`) на уровне средних групп и общего пула, плюс
   союзники/соперники между группами. Запускается **до** этапа features —
   его результат (`low_info_characters`) решает, кого пропустить на этапе 2.
3. **Features** (`src/services/collection/features`) — ординальные ранги (6
   параметров) и бинарные флаги (51), 3 прохода каждый, сведение через
   maximin-Cohen's-kappa консенсус (`src/services/consensus`).
4. **Graph** (`src/services/graph`) — интерактивный граф отношений (pyvis),
   запускается вручную, не входит в `run_pipeline.sh`.

Персистентный источник истины — PostgreSQL (ростер/алиасы/группы/отношения
пишутся туда этапами 1 и 3 через `src/repository`). Ординалы/флаги (этап 2)
в БД пока не пишутся — известный, отдельно запланированный пробел, см.
ARCHITECTURE.md. JSON/CSV/HTML-файлы одного прогона (`run/*`) — только
передача данных между этапами внутри одного запуска, не источник истины.

---

## Запуск

```bash
docker compose up -d db redis
./run_pipeline.sh "Classroom of the Elite" "Year 1"
```

БД инициализируется из `src/repository/schema/init.sql` при первом старте
контейнера `db`. Граф — отдельно:

```bash
docker compose run --rm analyse_service \
    conda run --no-capture-output -n analyse_service python -m src.services.graph.main "Classroom of the Elite" "Year 1"
```

---

## Переменные окружения (`.env`)

| Переменная | Описание |
|------------|----------|
| `API_KEY_GIMINI` | Ключ Gemini API (основной клиент) |
| `API_KEY_X` | Ключ xAI API (`XClient`, запасной/неактивный) |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL |
| `REDIS_URL_CELERY` | зарезервировано, не используется активно |
| `REDIS_URL_CACHE` | Redis для кеша ответов модели (TTL 14 дней) |
| `DEBUG` | режим отладки |

---

## Инфраструктура

- **PostgreSQL 14** — порт 5439 (хост) → 5432 (контейнер), БД `archangel`
- **Redis** — кеш ответов модели (`redis://...6379/1`)
- **Docker Compose** — сервисы `db`, `redis`, `analyse_service` (Python/conda,
  запускается только через `docker compose run ... python -m ...`, не как
  постоянный сервер), `r_analysis` (R, kappa-валидация)
