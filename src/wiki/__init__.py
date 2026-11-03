"""Чтение вики: дамп MediaWiki -> страницы -> секции/абзацы; клиенты Ollama и эмбеддингов.

Перенесено из extract_v3/external (сам extract_v3 — в legacy/). Атомарные модули без бизнес-логики.
Зависимости: mwparserfromhell (cleaner), httpx + pydantic (ollama), fastembed + numpy (embedder).
"""
