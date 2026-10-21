# Пример пробного прогона

80 сегментов MN (`mn5`, `mn32`, `mn119`), модель `gemini-3.8-flash`.

- 42 replace + 22 insert = 64 правки;
- 16 спорных (пустой RU / уже «товарищи»);
- 0 ошибок.

Файлы:
- `report.html` — отчёт с блоками «Применено», «Вставки (пропуски)», «Спорные моменты»;
- `report.md` — то же в Markdown;
- `changes.tsv`, `disputed.tsv`, `insertions.tsv`;
- `edits_merged.jsonl` — вход для `apply_edits.py`;
- `run.json` — сводка.

Это только пример; полный MN — 1506 сегментов.
