# Yuzuki — ресёрч и чистка, 2026-11

## Итог (qwen3.5-9b Q4_K_M; 7 персонажей: 5 MHA + 2 Bunny Girl Senpai)

Эталон: связи — 173 абзаца, 253 связи; черты — 32 абзаца Personality, 176 черт. В скобках — 95% bootstrap-интервал.
Проверка гипотез: Shapiro–Wilk на разностях по персонажам → парный t-тест (нормально) или Wilcoxon; McNemar по
решениям «связь есть/нет» на одних и тех же парах (абзац, имя). Детали — `research/runs/qwen3.5-9b-Q4_K_M/stats.md`.

**Связи — M1 `rel_anchored`** (имена находит код, модель выбирает linked/type/affinity из enum):

| способ | строгая P | R | F1 | выдуманные имена |
|---|---|---|---|---|
| M0 свободный список (текущий план) | 0.70 [0.63–0.77] | 0.84 [0.79–0.89] | 0.89 [0.86–0.92] | 13 из 308 (4.2%) |
| **M1 выбор из списка** | **0.77 [0.71–0.82]** | **0.90 [0.86–0.94]** | **0.95 [0.92–0.97]** | **0 из 298** |

M1 против M0: F1 +0.066 (t-тест p=0.0014), полнота +0.088 (p=0.0053), McNemar по 261 решению p=0.0135 —
**M1 значимо лучше**. Строгая точность +0.042 — в ту же сторону, но не значимо (p=0.24).

**Черты — T3 `traits_verify`** (фрагмент — enum из слов абзаца + проверка да/нет):

| способ | P | R | F1 |
|---|---|---|---|
| T2 фрагмент из слов абзаца | 0.68 [0.57–0.80] | 0.77 [0.65–0.90] | 0.72 [0.64–0.81] |
| **T3 = T2 + проверка** | **0.93 [0.89–0.96]** | 0.64 [0.51–0.78] | 0.75 [0.66–0.85] |

T3 против T2: точность +0.25 (t-тест p=0.0018), полнота −0.15 (p=0.029), F1 без разницы (p=0.86).

**Модель «замер = реальное + шум»** (`research/exp/anova.py`, балл персонажа по оси Big Five/HEXACO из черт T3):
ANOVA/Kruskal–Wallis — все 6 осей различают персонажей сильнее шума; надёжнее всего A и H (ICC 0.80–0.84,
r с эталоном 0.89–0.94), хуже всего N — систематически занижен (−0.17, p=0.013), r=0.39. Шум при пересэмплинге
абзацев не нормален (мало абзацев на персонажа), дисперсии не равны — поэтому рядом Alexander–Govern и Kruskal–Wallis.
Повторы с температурой модели — `anova_traits_verify_model.md`.

Прогон — на CPU контейнера через llama.cpp (тот же GGUF и грамматика, что у Ollama): качество переносится, скорость — нет.
В `legacy/src/extract_v3/config.yaml` стоит Q8_0 (9.53 GB) — не помещается в 8 GB VRAM; берите Q4_K_M (5.68 GB).

---

## Что сделано в ветке

| Часть | Где |
|---|---|
| Аудит, перенос мёртвого в `legacy/` с README, 2 бага исправлены | `legacy/README.md`, §Аудит ниже, полный аудит — `research/notes/audit.md` |
| Утилиты вики вынесены в живой пакет; заглушка слоя Neo4j (интерфейс, без реализации) | `src/wiki/`, `src/graph_store/store.py` |
| README, ARCHITECTURE под текущий курс; compose — только Neo4j, пароль из `.env` | корень |
| Эталонная разметка (учитель — Claude, вручную) | `research/gold/kyoka_jiro.relations.yaml`, `research/gold/traits.yaml` |
| Харнесс: 5 методов связей, 2 метода черт, сравнения и BT-рейтинг, метрики | `research/exp/` |
| Скрипты для дампа: вырезать страницы, построить ростер | `research/samples/` |
| Заметки ресёрча с источниками (англ.) | `research/notes/A_*.md`, `B_*.md`, `C_*.md` |
| Тесты: 16 на живой код (`pytest -q tests`) + legacy proto_wiki 36/36 | `tests/` |

Отклонения от задания. Ветка — `claude/new-session-akcnem`, а не `research/2026-11`: сессия может пушить только в свою
ветку. Старые прототипы не удалены, а лежат в `legacy/`. `extract_v3/external` *скопирован* в `src/wiki/`, а не перенесён,
чтобы legacy-код оставался запускаемым.

---

## Эксперименты

### Что меряется

Отношения меряются на эталоне Jiro: страница-владелец, все 19 секций /Relationships, Personality и 4 арки Synopsis.
- **link P/R/F1**: пары (абзац, X). *Lenient* — co-presence («the two along with…») не штрафуется. *Strict* — штрафуется.
- **affinity acc**: доля верных affinity среди найденных связей.
- **halluc.names**: доля выданных имён, которых нет в абзаце.
- **type P/R**: тип связи на уровне страницы.

Черты меряются на Personality Jiro, Mineta и Shigaraki (первые 2 абзаца).
- **P/R** — по совпадению фрагмента.
- **pole_acc** — верный ли полюс.
- **not_trait** — сколько раз выдано то, что не является чертой: «comes off as cold» (видимость), «not a bully» (отрицание).

```bash
python -m research.exp.check_ollama --model qwen3.5:9b                   # 0. соблюдается ли enum при think=false
python -m research.exp.run --methods all --model qwen3.5:9b              # 1. всё (81+16 размеченных абзацев)
python -m research.exp.run --methods rel_anchored --limit 10             # быстрый прогон
python -m research.exp.ordinals --model qwen3.5:9b                        # бои -> рейтинг (без эталона)
```

Результат пишется в `research/runs/<model>/summary.md`. Ошибки каждого метода — FP/FN по абзацам, пропущенные черты —
лежат в `*.errors.txt` рядом с ним.

Без Ollama — тот же прогон через llama.cpp в процессе (`pip install llama-cpp-python`):
`python -m research.exp.run --methods all --model qwen3.5-9b --gguf <путь к .gguf>`.

### Без модели (нижние границы)

| method | P lenient / strict | R | F1 | affinity | halluc. | type P/R | pole_acc | not_trait |
|---|---|---|---|---|---|---|---|---|
| oracle (эталон сам с собой) | 1.00 / 1.00 | 1.00 | 1.00 | 1.00 | 0% | 1.00 / 1.00 | 1.00 | 0 |
| **rel_cooccur** (кандидаты = связи) | **0.94 / 0.54** | **1.00** | 0.97 | 0.30* | 0% | — | | |
| **traits_lexicon** (122 маркера Mini-Markers/Goldberg/HEXACO) | 0.75 | 0.30 | 0.42 | | | | 1.00 | 1 («cold») |

\* affinity у co-occurrence — константа `neutral`.

Выводы:
- Ростер находит **все** имена эталона (тест `test_gold_names_are_detectable_by_roster`), так что у M1–M3 нет потолка по recall.
- Чистый лексикон точен, но находит только 30% черт: в тексте «blunt», «snarky», «freaks out», «lashing out» — не
  психометрические маркеры. Нужен LLM-шаг, который выписывает фрагмент и ставит полюс. Лексикон годится для проверки полюса.
- В лексикон намеренно не добавлены слова из самих страниц эталона, иначе была бы утечка эталона.

### Методы: что даёт и что ломается (время — оценка для RTX 5060)

| Метод | Что даёт | Что ломается | Время на RTX 5060 (оценка¹): страница Jiro / 50 вселенных² | Сложность |
|---|---|---|---|---|
| B0 `rel_cooccur` — код | «связь возможна», recall 1.0 | строгая P 0.54; нет типа и знака | <1 с / минуты | тривиально |
| M0 `rel_free` — текущий план («перечисли связи одним словом») | baseline | модель пишет имена → посторонние имена; свободное слово → синонимы | ~10 мин / ~250 ч | низкая |
| **M1 `rel_anchored`** — кандидаты кодом, объект с ключом на каждого кандидата, enum для type/affinity | 0% посторонних имён по построению; один вызов на абзац; ответ на *каждого* кандидата | может выбрать неверного кандидата из присутствующих; при багe ollama#14645 гарантия пропадает (проверка — `check_ollama`) | ~11 мин (main+Relationships: ~4 мин) / ~100 ч только main+Relationships | низкая |
| M2 `rel_pairwise` — отдельный вопрос на пару, абзац в кэшируемом префиксе | проще каждая задача; лучше на длинных абзацах с многими именами | ×3 вызовов; Conan: попарный режим при *генерации* увеличивает галлюцинации отношений (здесь генерации нет) | ~13 мин / ~120 ч | низкая |
| M3 `rel_verify` — M1 + да/нет на каждую связь (CoVe/NLI-шаблоны) | выше строгая P; верификатор не видит черновик | чуть ниже R; +вызовы | ~12 мин / ~110 ч | средняя |
| NLI DeBERTa-MNLI (Sainz 2021) — не реализован | второе мнение, ~63 F1 zero-shot на TACRED, CPU/GPU | шаблоны на английском; нет знания контекста секции | секунды / часы | средняя |
| Поля инфобокса (relatives, affiliation, master/apprentice) — не реализован | точные родство, членство и наставничество без модели | схема инфобокса своя на каждой вики; у Naruto-вики полей нет | 0 / 0 | средняя (ручная работа под вики) |
| T0 `traits_lexicon` | P 0.75, полюса верны | R 0.30, литерален («comes off as cold» → cold) | 0 | тривиально |
| **T1 `traits_llm`** — фрагмент + полюс(12) + статус(actual/apparent/negated/other_character) | покрытие формулировок не из словаря; буквальность решается классификацией статуса, а не фильтром | полюс спорных черт («proud»: H- или N-?) | ~1 мин / ~25 ч | низкая |
| Дистилляция M1 → Qwen3.5-2B LoRA | ~3× быстрее (оценка), стабильный формат | нужно 1–2k размеченных абзацев и ~150 проверенных руками | ~4 мин / ~35 ч | средняя |
| Сравнения + BT–Davidson (`ordinals.py`) | тиры из текста, а не из памяти модели | разреженный граф боёв; между вселенными нет мостов без внешнего источника | ~5 мин на Synopsis / ~120 ч | средняя |
| API-модель как основной экстрактор | лучшее качество | против ограничений проекта; ≈ $3–6 за 1k абзацев, то есть ≈ $1.5–3k на 50 вселенных | — | низкая |

¹ Оценка, не замер. Llama-2-7B Q4_0 на RTX 5060: ~3.3–3.8k ток/с prompt eval, ~97–100 ток/с генерации (llama.cpp
scoreboard, комментарий пользователя). Для 9B Q4_K_M ×0.6–0.7. Генерация доминирует, поэтому короткие enum-ответы — главный
рычаг скорости. Реальная скорость — в колонке `speed` харнесса.
² 50 вселенных ≈ 1500 персонажей со своей страницей (~30 на вселенную). Страница Jiro — 313 абзацев, из них 260 с
кандидатами: 787 кандидатов. Relationships+main ≈ 30% абзацев, на Synopsis уходит ~70%.

### Посторонние имена: конструктивное решение

Решение — M1. Схема `format` — объект, ключи которого — канонические имена кандидатов, все обязательные,
`additionalProperties: false`:
```json
{"Denki Kaminari": {"evidence": "...", "linked": true, "type": "friend", "affinity": "positive"},
 "Momo Yaoyorozu": {"evidence": "", "linked": false, "type": "unspecified", "affinity": "neutral"}}
```
Грамматика не даёт написать ключ вне списка. Обязательность не даёт пропустить кандидата. Упоминания в тексте размечены
(`[Denki](Denki Kaminari)`), так что модель видит, к кому относится «Denki». На /Relationships кандидатом всегда добавляется
персонаж из заголовка секции: в абзацах там пишут «the two», а не имя. Этого достаточно: в эталоне нет ни одной связи,
которую код не нашёл бы в кандидатах.

---

## Рекомендованный путь

1. **Шаг 0 — окружение.**
   ```bash
   ollama pull qwen3.5:9b
   ollama ps
   python -m research.exp.check_ollama --model qwen3.5:9b
   ```
   В `ollama ps` PROCESSOR должен быть `100% GPU`. `check_ollama` должен вывести «OK: enum enforced». Если нет — обновить
   Ollama, а пока использовать M2 с проверкой ответа по enum в коде.
2. **Шаг 1 — метод выбран (M1 + T2, см. «Итог»); замерить скорость на своей GPU.**
   ```bash
   python -m research.exp.run --methods rel_anchored,traits_anchored --model qwen3.5:9b
   cat research/runs/qwen3.5_9b/summary.md
   ```
   Качество должно совпасть с `research/runs/qwen3.5-9b-Q4_K_M/summary.md` (те же веса, temperature 0); колонка `speed` —
   ваша реальная скорость. Если качество хуже — Ollama не применяет грамматику (см. шаг 0).
3. **Шаг 2 — проверить переносимость.** Вырезать страницы других вселенных и построить авторостер:
   ```bash
   python -m research.samples.extract_pages --dump <aobuta.xml> --pages "Mai Sakurajima"
   python -m research.samples.build_roster --dump <aobuta.xml> --out research/samples/rosters/aobuta.yaml
   ```
   Затем разметить 1–2 страницы так же, как `research/gold/`: учителем (Claude/API) с ручной проверкой. Добавить их в
   `run.py` (константы `REL_GOLD`, `ROSTER`).
4. **Шаг 3 — инфобоксы.** Родство, членство и наставничество брать из полей инфобокса как отдельный источник
   (`method="infobox"`): точнее любой модели. Это ручная работа под каждую вики — она за владельцем.
5. **Шаг 4 — прогон.** M1 по main+Relationships для всех персонажей, T2 по Personality, `comparisons` по Synopsis. Записи —
   в Neo4j через `src/graph_store`; провенанс на каждом ребре.
6. **Шаг 5 — дистилляция.** Учитель размечает 1–2k абзацев по схеме M1 (`research/exp/methods.py:_rel_system` — промпт
   готов), ~150 проверить руками. Обучить Qwen3.5-2B bf16 LoRA (Unsloth), сохранить в GGUF через
   `save_pretrained_gguf(q4_k_m)`, загрузить в Ollama через `FROM` в Modelfile. `ADAPTER` для Qwen не поддерживается.
   Сравнить в том же харнессе (`--model yuzuki-m1-2b`).
7. **Шаг 6 — валидация черт** по Open-Source Psychometrics SWCPQ: 2125 персонажей × 500 биполярных прилагательных,
   CC BY-NC-SA. Пересечение с аниме небольшое: AoT 10, Death Note 10, Naruto 5, Star Wars ~18.
8. **Шаг 7 — тиры.** `ordinals.py`; приор и мосты между вселенными — тир и Notable Matchups с VS Battles Wiki
   (CC-BY-SA, отдельный `source`, не канон).

---

## Прошлые провалы: что объясняется известными ограничениями, а что — промптами

| Провал | Объяснение | Тип |
|---|---|---|
| Сбор «по памяти» не работает на тайтлах средней популярности | Знание LLM о сущности падает с её популярностью; для длинного хвоста нужна опора на текст (Mallen et al. 2023, PopQA) | известное ограничение |
| Kappa шумная (±0.25), сдвиг между провайдерами | Kappa нестабильна при перекошенной доле положительных («kappa paradox», Feinstein & Cicchetti 1990); у разных моделей разные априорные склонности | известное |
| Абстрактные суждения (макиавеллизм, тип отношений) — мусор | Латентные конструкты в тексте вики не названы; их оценка требует вывода по многим ситуациям — низкая надёжность даже у сильных моделей. Конкретные прилагательные и явные связи извлекаются | известное |
| v3 по предложениям: слишком буквально, >1 ч | Отношение часто требует нескольких предложений (DocRED: ≥40.7% фактов межфразовые); пересказ предложения вне абзаца теряет «это тренировка» | известное (выбор единицы текста) |
| Связи по абзацу: модель тащит имена, которых нет | Свободное текстовое поле для имени. Все рабочие системы (KGGen, iText2KG, Graphiti, LightRAG) сначала фиксируют набор сущностей и ограничивают концы рёбер этим набором | **схема/промпт** — исправимо (M1) |
| Вся страница в контексте + вопрос по каждому имени | Длинный контекст у малой модели: «lost in the middle» (Liu et al. 2023); плюс Q8 с выгрузкой на CPU → медленно | известное + конфигурация |
| ~30 мин на Jiro, 14 с на вопрос | Q8_0 9B (~9.5 GB) не помещается в 8 GB VRAM | **конфигурация** |
| GLiNER/GLiREL мало дали | Обучены на энциклопедических/Wikidata-подобных отношениях; социальные отношения в нарративе — другой домен | известное |
| Uncensored хуже | Агрессивные uncensored-тюны обычно платят общим качеством; источника с замером не нашёл — мнение | вероятно известное |
| Частотные пороги убивают редкие черты | Верно. Пороги не нужны, если черта отображается в закрытый полюс: редкая формулировка всё равно попадает в общий узел | дизайн |

---

## Чего делать не стоит

- **Свободных полей для имён и типов** в любой схеме. Только `enum`, построенный кодом или взятый из таксономии.
- **GraphRAG «gleanings»** («MANY entities were missed…»): у 9B модели это прямой запрос на выдумку.
- **Вопросов о латентных конструктах** (Machiavellianism, нарциссизм, октанты циркумплекса). Если слово есть в тексте
  («manipulative»), оно извлекается как черта с цитатой, а не как оценка.
- **Учить Qwen3.5-9B на 8 GB.** QLoRA на Qwen3.5 Unsloth не рекомендует, bf16-LoRA 9B требует 22 GB.
- **Elo/Glicko для тиров**: зависят от порядка партий, а у текстовых сравнений порядка нет.
- **Сравнивать силу между вселенными без мостов**: BT определён с точностью до константы внутри компоненты.
- **BookNLP, RMN, скрейпинг PDB, Kaggle MBTI**: заточены под романы или не о персонажах.
- **Брать эмбеддинги как единственный способ склеить синонимы черт**: антонимы (warm/cold) близки в эмбеддинг-пространстве.
  Для черт — закрытые полюса, для хвоста свободных слов — EDC-канонизация по определениям.

## Позиции владельца, которые я бы оспорил

- **«Сущность/черта нужна, только если есть родственники в ≥2 других вселенных»** — это частотный порог по вселенным,
  он противоречит «без порогов». С закрытыми таксономиями (`taxonomy.py`) каждая черта и каждый тип — общий узел во всех
  вселенных по построению. Правило можно снять.
- **«Тип связи — одно слово»** — да, но знак отношения надо хранить отдельно: rivals бывают дружескими и враждебными.
  Так устроены Massey 2015 (type + affinity) и Wish 1976 (измерение cooperative–hostile). Измерения Wish
  (равные/неравные, интенсивные/поверхностные) выводятся из типа и не спрашиваются.
- **«События/взаимодействия пока выкинуты»** — запись «(абзац, X, linked, affinity, evidence)» *и есть* событие
  взаимодействия, и стоит она ноль дополнительных вызовов. Хранить как слой наблюдений; упорядоченные по аркам Synopsis,
  они дают траекторию отношения (Chaturvedi et al. 2016/2017).
- **«Сильная API-модель как основной экстрактор — нет»** — согласен для прогона. Но как учитель для 1–2k абзацев
  ($3–6) и для эталона она почти обязательна: без проверенного эталона нельзя выбрать метод, а без размеченных данных нельзя
  обучить 2B.

---

## Эталон

- **Связи** — `research/gold/kyoka_jiro.relations.yaml`: 81 абзац, 121 обязательная связь, плюс список `optional`
  (co-presence). 19 целей уровня страницы с типом и affinity. Правила — в шапке файла.
- **Черты** — `research/gold/traits.yaml`: Jiro 18, Mineta 34, Shigaraki 19 (первые 2 абзаца). Для каждой — полюс и
  допустимые альтернативы, плюс список `not_traits` (видимость, отрицание, чужая черта, интерес).
- Ограничения:
  - Один аннотатор (Claude), без межэкспертного согласия.
  - Одна вселенная (MHA), в основном одна страница.
  - Полюса части черт спорны — поэтому есть `also_ok`.
  - Lenient-метрика добра к co-presence; смотрите обе.
  - Список `unmatched` в `*.errors.txt` нужно просмотреть: эталон может быть неполон.

## Аудит

**Исправлено:**
- `legacy/src/extract_v3/neo4j_writer.py` — `canonicalize` строился, но не вызывался: «Jiro», «Kyoka» и «Kyoka Jiro»
  становились тремя узлами.
- `schemas.py` — `target_type` был свободной строкой, «Character» молча превращался в Concept; теперь Literal.
- Пароль Postgres `6713` и дефолтный пароль Neo4j убраны из живого compose (в `legacy/docker-compose.yaml` остались как
  история).
- `.gitignore` больше не игнорирует отслеживаемый `.dockerignore`. Кэши прогонов и выходы `research/runs` игнорируются.
- README ссылался на удалённые PIPELINE.md и ARCHITECTURE.md и на несуществующую картинку — переписан.
  ARCHITECTURE.md создан.

**Не исправлено — решение за владельцем, всё в legacy:**
- `run_jiro.py:61,114` — при resume ошибки не перезапускаются.
- Кэши extract_v3 не учитывают модель и промпт: смена модели молча переиспользует старые ответы.
- `think` из конфига игнорируется: клиент всегда шлёт `false`.
- `neo4j_schema.py` — `name` глобально UNIQUE, имена разных вселенных столкнутся. В ARCHITECTURE.md предложен ключ
  `(universe, name)`.
- Хардкод `/home/Di/Загрузки/...` в `config.yaml` и `jiro_flags_local/run.py`.
- `jiro_flags_local` — нет агрегатора, который строит `result.json`.

Полный список с номерами строк — `research/notes/audit.md`. Пути там указаны до переноса.

---

## Источники

Подробности и сверка — в `research/notes/`. Основное:

**Персонажи и отношения в художественном тексте**
- Massey et al. 2015, Annotating Character Relationships in Literary Texts — https://arxiv.org/abs/1512.00728 · данные https://github.com/dbamman/characterRelations
- Srivastava, Chaturvedi, Mitchell 2016, отношения в сюжетах Wikipedia — https://arxiv.org/abs/1512.00112
- Iyyer et al. 2016, RMN — https://aclanthology.org/N16-1180/
- Chaturvedi et al. 2016/2017 — https://ojs.aaai.org/index.php/AAAI/article/view/10358 · https://ojs.aaai.org/index.php/AAAI/article/view/10982
- DialogRE (Yu et al. 2020) — https://arxiv.org/abs/2004.08056 · https://github.com/nlpdata/dialogre
- Conan (Zhao et al. 2024) — https://arxiv.org/abs/2402.11051
- CHIRON (Gurung & Lapata 2024) — https://arxiv.org/abs/2406.10190
- CREFT (2025) — https://arxiv.org/abs/2505.24553
- Labatut & Bost 2019, обзор сетей персонажей — https://arxiv.org/abs/1907.02704

**LLM → граф знаний**
- KGGen — https://arxiv.org/abs/2502.09956 · код с `Literal[entities]`: https://github.com/stair-lab/kg-gen
- GraphRAG prompt — https://github.com/microsoft/graphrag
- LightRAG — https://arxiv.org/abs/2410.05779
- EDC (Zhang & Soh 2024) — https://arxiv.org/abs/2404.03868
- iText2KG — https://arxiv.org/abs/2409.03284
- Graphiti — https://arxiv.org/abs/2501.13956
- Text2KGBench — https://arxiv.org/abs/2308.02357

**Ограничения малых моделей и методы**
- Ollama structured outputs — https://ollama.com/blog/structured-outputs
- llama.cpp json-schema-to-grammar (enum) — https://github.com/ggml-org/llama.cpp/blob/master/common/json-schema-to-grammar.cpp
- ollama#14645 (format при think=false) — https://github.com/ollama/ollama/issues/14645
- Zhou & Chen 2021, typed entity markers — https://arxiv.org/abs/2102.01373
- Sainz et al. 2021, RE как entailment — https://arxiv.org/abs/2109.03659
- CoVe — https://arxiv.org/abs/2309.11495
- Ma et al. 2023, LLM is a good reranker — https://arxiv.org/abs/2303.08559
- GoLLIE — https://arxiv.org/abs/2310.03668
- NuExtract 2.0 — https://huggingface.co/numind/NuExtract-2.0-8B
- llama.cpp CUDA scoreboard — https://github.com/ggml-org/llama.cpp/discussions/15013
- Mallen et al. 2023, PopQA — https://arxiv.org/abs/2212.10511
- Liu et al. 2023, Lost in the Middle — https://arxiv.org/abs/2307.03172
- DocRED (Yao et al. 2019) — https://arxiv.org/abs/1906.06127

**Дистилляция**
- Distilling step-by-step — https://arxiv.org/abs/2305.02301
- UniversalNER — https://arxiv.org/abs/2308.03279
- NuExtract — https://numind.ai/blog/nuextract-a-foundation-model-for-structured-extraction
- Christou & Tsoumakas 2026, малые модели на литературном RE — https://arxiv.org/abs/2606.22606
- LIMA — https://arxiv.org/abs/2305.11206
- Unsloth: Qwen3.5 fine-tune — https://unsloth.ai/docs/models/qwen3.5/fine-tune · требования к VRAM — https://unsloth.ai/docs/get-started/fine-tuning-for-beginners/unsloth-requirements
- Ollama Modelfile — https://docs.ollama.com/modelfile
- Цены — https://platform.claude.com/docs/en/about-claude/pricing · https://aistudio.google.com/docs/pricing

**Таксономии**
- Goldberg 1992, 100 маркеров — https://personality-project.org/r/psych/help/big5.100.adjectives.html
- Saucier 1994, Mini-Markers — https://psytests.org/big5/minimen-bl.html (воспроизведение)
- HEXACO — https://hexaco.org
- Wiggins IAS — https://www.parinc.com/products/IAS (проприетарно)
- Wish, Deutsch & Kaplan 1976, JPSP 33(4):409
- Fiske 1992, Psych. Rev. 99(4):689
- Bugental 2000 — doi:10.1037/0033-2909.126.2.187
- Paulhus & Williams 2002 (Dark Triad) — doi:10.1016/S0092-6566(02)00505-6
- FrameNet — https://framenet.icsi.berkeley.edu
- VerbNet через NLTK
- WordNet lexnames — https://wordnet.princeton.edu/documentation/lexnames5wn

**Данные**
- Open-Source Psychometrics SWCPQ — https://openpsychometrics.org/tests/characters/data/
- Wikidata (P7047 enemy, P1038 relative, P3373 sibling, P26 spouse, P463 member of)
- VS Battles Wiki Tiering System — https://vsbattles.fandom.com/wiki/Tiering_System

**Ординалы**
- Hunter 2004, MM для Bradley–Terry — https://pure.psu.edu/en/publications/mm-algorithms-for-generalized-bradley-terry-models/
- Davidson 1970 — doi:10.1080/01621459.1970.10481082
- Rank Centrality — https://arxiv.org/abs/1209.1688
- choix — https://github.com/lucasmaystre/choix
- openskill — https://pypi.org/project/openskill/
- Feinstein & Cicchetti 1990, kappa paradox — J Clin Epidemiol 43(6):543
