# Yuzuki

> Speaking about the dataset and the process of its choosing, I wonder if I could choose anything more popular so that the stupid model could give a logical response, but I faced the problem
> I cannot restrain my soul from using stories, which had a great influence on me. Rascal does not dream of bunny girl sempai was my first ever watched anime and it is still one of my favorites. Although I did watch hundreds of them, I did not find anything comparable. That is why this project is not mostly real research but a try to teach a machine how I feel about people's being
>
> To conclude, I want to thank all authors for their time and efforts, which make me a bit happier day by day


Граф персонажей из многих вселенных (аниме, манга, Star Wars, …) → GNN, которая предсказывает отношения,
в том числе между вселенными. Данные — из дампов Fandom-вики, извлечение — локальной моделью
(`qwen3.5:9b` через Ollama, RTX 5060 8 GB), хранилище — Neo4j.

**Состояние (2026-11):** идёт выбор метода извлечения. Что пробовали, что сработало и что делать дальше —
[research/REPORT.md](research/REPORT.md). Устройство репозитория — [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Структура

| Путь | Что |
|---|---|
| `src/wiki/` | дамп MediaWiki → страницы → секции/абзацы; клиенты Ollama и эмбеддингов |
| `src/graph_store/` | интерфейс слоя Neo4j (заглушка — пишется руками) |
| `research/` | отчёт, эталонная разметка, эксперименты (`research/exp`), образцы страниц и ростеры |
| `legacy/` | всё брошенное: API-сбор (Grok/Gemini, Postgres, Redis, флаги), proto_wiki, extract_v3 — [legacy/README.md](legacy/README.md) |
| `tests/` | тесты живого кода (`pytest -q tests`) |

## Запуск

```bash
pip install -r requirements.txt
pytest -q tests
python -m research.exp.check_ollama --model qwen3.5:9b
python -m research.exp.run --methods all --model qwen3.5:9b
```

Neo4j (пароль — `NEO4J_PASSWORD` в `.env`):

```bash
docker compose up -d neo4j
```

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
