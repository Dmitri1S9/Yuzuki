# samples/ — какие страницы нужны и как их получить

В облачной сессии нет доступа к fandom.com, поэтому в `pages/` лежат только 5 страниц MHA, уже бывшие в репо
(из `legacy/src/experiments/jiro_flags_local/contexts/`). Эталон (`research/gold/`) размечен по ним.

## Что положить дополнительно (для проверки, что метод не переобучен на одну вселенную)

| Персонаж | Вики (дамп) | Тип | Зачем |
|---|---|---|---|
| Kyoka Jiro | bokunoheroacademia | второстепенный, есть /Relationships | эталон, уже есть |
| Izuku Midoriya | bokunoheroacademia | главный герой | длинная страница, много имён — уже есть |
| Tomura Shigaraki / All For One | bokunoheroacademia | злодеи | враждебные связи, бои для ординалов — уже есть |
| Minoru Mineta | bokunoheroacademia | комический второстепенный | негативный affinity, черты — уже есть |
| **Mai Sakurajima** | aobuta (Rascal Does Not Dream) | главная героиня, тайтл средней популярности | ровно тот случай, где провалился сбор «по памяти» |
| **Obi-Wan Kenobi** | starwars (Wookieepedia) | другая вселенная, другой формат: нет подстраниц /Relationships, Canon/Legends | проверка переносимости на не-аниме вики |

Дампы: `https://<wiki>.fandom.com/wiki/Special:Statistics` → «Database dump» (pages_current.xml).

## Команды

```bash
python -m research.samples.extract_pages --dump ~/Загрузки/bokunoheroacademia_pages_current.xml --pages "Kyoka Jiro" "Izuku Midoriya"
python -m research.samples.extract_pages --dump ~/Загрузки/aobuta_pages_current.xml --pages "Mai Sakurajima"
python -m research.samples.extract_pages --dump ~/Загрузки/starwars_pages_current.xml --pages "Obi-Wan Kenobi" --subpages
python -m research.samples.build_roster --dump ~/Загрузки/bokunoheroacademia_pages_current.xml --out research/samples/rosters/mha_auto.yaml
```

`extract_pages` пишет `<Name>.txt` (формат `=== PAGE ===` / `== секция ==` / абзац на строку) и `<Name>.links.json`
(подпись вики-ссылки → страница: готовые алиасы). `build_roster` строит ростер из категорий + редиректов + подписей ссылок —
имена и алиасы кодом, а не моделью. Категории на разных вики называются по-разному (`--char-category`, `--group-category`).
