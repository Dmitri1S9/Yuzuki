# legacy/ — что это было и почему брошено

Перенесено из корня в ветке research (2026-11). Ничего не удалено; история файлов сохранена (`git log --follow`).
Структура внутри повторяет старую (`legacy/src/...`, `legacy/tests/...`), поэтому относительные пути в коде
работают: legacy-модули запускаются из этой папки (`cd legacy && python -m src.services...`,
`cd legacy && pytest tests/proto_wiki` — 36/36 проходят).

| Что | Что это было | Почему брошено |
|---|---|---|
| `src/api, domain, infra, repository, services, shared` | Март–сентябрь 2026: сбор «по памяти» API-моделей (Grok 4.1 Fast → Gemini). Stage 1 cast/группы, Stage 2 — 51 флаг + 6 ординалов с kappa-консенсусом, Stage 3 — попарные отношения; PostgreSQL `archangel`, Redis-кэш, Celery, FastAPI | Аудит вселенной 74 (Bunny Girl Senpai): на тайтлах средней популярности модель не знает канона — garbage in, garbage out. Поворот к вики-дампам |
| `src/infra/ai_clients/{x,cerebras}_client.py` | Клиенты xAI и Cerebras | Мёртвые уже до переноса (никем не импортировались) |
| `run_pipeline.sh`, `run_stage2.sh`, `Dockerfile`, `analyse.yml`, `docker-compose.yaml` | Запуск старого стека (conda-образ, db/redis/analyse_service/r_analysis) | Вместе со стеком. Актуальный compose в корне — только Neo4j |
| `kappa_analysis.R` | Cohen's kappa между проходами флагов (0.897 → 0.964) | Флаги убраны из курса |
| `src/proto_wiki` + `tests/proto_wiki` | Первый вики-прототип (`yuzuki_proto`): coref → тройки из закрытого словаря → флаги/ординалы с проверкой цитат → pyvis | Полный прогон на Jiro: абстрактные суждения локальной модели — мусор. Флаги убраны. Читает `src/domain/parameters.json` по пути — поэтому лежит рядом с legacy-доменом |
| `src/experiments/jiro_flags_local` | Эксперимент: флаги по контексту страницы на 5 персонажах MHA | Флаги убраны. Сломан: `revalidate.py`/`verify_quotes.py` читают `result.json`, который `run.py` не пишет. Тексты страниц из `contexts/` скопированы в `research/samples/pages/` |
| `src/extract_v3` | v3: каждое предложение → простые предложения → тройка (subject–action–modality–manner–target) → Neo4j. Включает `test_env/` — тестовую среду промптов | Провал: слишком буквально (тренировку прочитала как нападение), >1 ч на персонажа. Утилиты `external/` скопированы в `src/wiki/`. Две очевидные ошибки исправлены перед переносом (см. research/REPORT.md §Аудит) |
| `src/extract_v3/.pass1_jiro-v3.json`, `.checkpoint_jiro-v3.json` | Кэши прогона v3 (pass 2 не завершён: 2166/2813) | Данные прогона, не код; новые такие файлы теперь в .gitignore |
| `tests/yuzuki_local` | Тесты модуля `yuzuki_local`, которого в репозитории никогда не было (ветка `wip-full-snapshot` не опубликована) | Сирота: падает на импорте |
