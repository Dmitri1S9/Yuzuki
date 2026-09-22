# Yuzuki

> Speaking about the dataset and the process of its choosing, I wonder if I could choose anything more popular so that the stupid model could give a logical response, but I faced the problem
> I cannot restrain my soul from using stories, which had a great influence on me. Rascal does not dream of bunny girl sempai was my first ever watched anime and it is still one of my favorites. Although I did watch hundreds of them, I did not find anything comparable. That is why this project is not mostly real research but a try to teach a machine how I feel about people's being
>
> To conclude, I want to thank all authors for their time and efforts, which make me a bit happier day by day

![Mai Sakurajima](wp5522224-rascal-does-not-dream-wallpapers.png)

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
   средние/большие группы (медиум/лардж/изоляты, 1 проход), разрешает
   написания и алиасы имён.
2. **Relations** (`src/services/collection/relations`) — попарные отношения
   (`for`/`against`/`want`/`with`) на уровне средних групп и общего пула
   (адаптивное число проходов по фактическому выходу новых пар), плюс
   союзники/соперники/часть-целого между группами. Запускается **до** этапа
   features — его результат (`low_info_characters`) решает, кого пропустить
   на этапе 2.
3. **Features** (`src/services/collection/features`) — ординальные ранги (6
   параметров, 3 прохода) и бинарные флаги (51, 2 прохода), сведение через
   maximin-Cohen's-kappa консенсус для ординалов и отдельный алгоритм с
   удалением расходящихся персонажей для флагов (`src/services/consensus`).
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

---

## Почему Bunny Girl Senpai — один из лучших аниме

Личная заметка, не часть технической документации.

«Seishun Buta Yarou wa Bunny Girl Senpai no Yume wo Minai» решает то, с чем
большинство аниме про сверхъестественное даже не пытается справиться:
«Синдром отрочества» — не просто предлог для фантастики, а последовательная,
работающая метафора конкретного психологического состояния каждого
персонажа. Каэдэ буквально теряет память как прямое следствие травли — это не
магия ради магии, это тело истории, рассказывающее правду о диссоциации.
Каждая арка вводит правило, которое потом не забывается — мир помнит сам
себя, и это редкость даже среди сериалов с куда большим бюджетом.

Сильнее всего это держится на конкретности письма: у Сакуты нет "функции
доброго парня" — у него есть усталость, злость на несправедливость мира по
отношению к сестре и способность оставаться рядом с человеком именно тогда,
когда это неудобно. Май — не декорация в костюме зайки, а актриса, которая
методично учится доверять кому-то за пределами публичного образа. Шоко —
редкий случай, когда тайна личности персонажа работает не как твист ради
твиста, а как последний поворот эмоционального ключа, который был вставлен в
замок с самого первого тома.

Данные, которые собирает этот проект — ординалы, флаги, отношения — здесь
сходятся неслучайно: Май и Нодока стабильно наверху по `social_impact` и
`wealth`, потому что мир вселенной последовательно помнит, кто они такие;
Рио — топ по `intellect`, потому что сериал ей это буквально доказывает
сюжетно, а не декларирует. Проработанность здесь не орнамент — она системная,
и именно поэтому вселенная выдерживает такой анализ, не разваливаясь на
противоречия.

И да — как признаётся автор этого проекта: я как потребитель плакал весь
день.
