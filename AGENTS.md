# AGENTS.md — контекст для ИИ-агента

## Роль

Ты работаешь с репозиторием **otrn** — пайплайном замены/вставки обращения `āvuso`
в русских переводах MN. LLM-часть идёт через Kaggle Benchmarks, применение —
детерминированный Python без ИИ.

## Источник истины

- Код и данные: этот репозиторий (`otrn`).
- Переводы: `dhammagift/offline-data`, ветка `main`, рабочая ветка `rename`.
- Пали: `suttacentral/sc-data`, `sc_bilara_data/root/pli/ms` (Mahāsaṅgīti).
- Kaggle dataset: `dhammagift/rename-mn`.
- Kaggle tasks: `mn-avuso-full-0` … `mn-avuso-full-7`.

## Карта

```
bench/task_full.py      replace + insert (основная задача)
bench/task_sample.py    пример на 80 сегментах
bench/task_insert.py    только вставки
work/build_dataset.py   сборка segments_*.jsonl
work/run_shard.py       запуск шарда в Benchmarks
work/run_full.py        один длинный прогон
work/merge_shards.py    слияние shard-*/edits.jsonl
work/apply_edits.py     валидация, splice, rename/archive, отчёт, push
work/insertions.yaml    ручные overrides вставок
dataset/                segments_*.jsonl + manifest
examples/sample-run/    пример отчёта
.github/workflows/      run-mn.yml (8 шардов + apply), run-shard.yml
```

## Текущее состояние (2026-10-21)

- Шард `mn-avuso-full-0`: **Completed**, скачан в
  `/root/rename/results/full/shard-0/.../edits.jsonl`
  (189 строк: 92 replace, 26 insert, 71 keep).
- Шарды `1..7`: на момент записи **Running**; локальные `run_shard.py`
  скачают их сами. Всегда проверяй статус, а не доверяй этому файлу:
  ```bash
  kaggle b t status mn-avuso-full-N
  ```
- Ветка `rename` в `offline-data` пока содержит **пробный** результат
  (80 сегментов: 42 replace + 22 insert, коммит `e381cef`).
  Полный MN ещё **не применён**.
- `main` — `8e1e69f`; не трогать.
- Полный прогон = 1506 строк, 8 шардов.

## Секреты

- Локально: `/root/.secrets/tools.env` (вне репозитория).
- GitHub Actions secrets:
  - `KAGGLE_API_TOKEN` — Kaggle API.
  - `OFFLINE_DATA_TOKEN` — fine-grained PAT, Contents: Read and write на `offline-data`.
- Никогда не коммитить `.env`, `bench/.env`, токены.
- В workflow токены только через `${{ secrets.* }}`.

## Команды

Проверка:

```bash
python work/run_shard.py --index 0 --count 8 --check
```

Шард:

```bash
python work/run_shard.py --index 0 --count 8
```

Параллельно (screen/локально):

```bash
mkdir -p logs
for i in 0 1 2 3 4 5 6 7; do
  python work/run_shard.py --index $i --count 8 > logs/shard-$i.log 2>&1 &
done
wait
```

Слить/применить:

```bash
python work/merge_shards.py --count 8
python work/apply_edits.py \
  --edits work/edits_full.jsonl \
  --config work/insertions.yaml \
  --push
```

Скачать конкретный шард:

```bash
kaggle b t download mn-avuso-full-0 -o results/full/shard-0 -f
```

## Схема edits.jsonl

```json
{"id":"mn32:9.10","file":"dhammagift/...json","key":"mn32:9.10",
 "pali":"...","ru":"...","action":"insert",
 "anchor_before":"Это как","anchor_after":"если бы","insert":"Моггаллана товарищ",
 "source":"","target":"","old":"","new":"","reason":"","confidence":0.95}
```

`action`: `replace` | `insert` | `keep`.

## Валидация (apply_edits.py)

- `replace`: `old` есть в RU; `source` — форма «друг»; `target` — форма «товарищ»;
  после удаления source/target остальные слова совпадают (порядок может меняться);
  пунктуация та же; `confidence >= 0.75`; `old` уникален.
- `insert`: `anchor_before + anchor_after` есть в RU; `insert` содержит «товарищ»;
  итог = `anchor_before, insert, anchor_after`.
- Всё невалидное → `disputed`, в ветку не идёт.
- Plain-файл с правками: оригинал → `dhammagift/svEtc/automatic/<basename>`,
  файл → `...+edited+o.json`.

## Git-инварианты

- `apply_edits.py` делает `fetch origin main`, `reset --hard origin/main`,
  `checkout -B rename` — **незакоммиченные изменения в `offline-data` теряются**.
- Ветка `rename` — одноразовая, force-push, один коммит.
- `main` не трогать.
- Коммит от `dhamma-gift-bot`; compare:
  `https://github.com/dhammagift/offline-data/compare/main...rename`.

## Веб-режим

`run-mn.yml`: 8 shard-jobs (matrix) + apply-job.
Секреты: `KAGGLE_API_TOKEN`, `OFFLINE_DATA_TOKEN` (fine-grained PAT).
`run-shard.yml`: один шард.

`apply_edits.py` поддерживает HTTPS PAT и SSH deploy key.

## Подводные камни

- `kaggle` на локальной машине — в `.venv`; без активации используйте
  `.venv/bin/kaggle` или `uvx`.
- Ручным командам `kaggle` нужен `KAGGLE_API_TOKEN` в env.
- `kaggle b t push` **сам запускает** задачу на дефолтной модели;
  `--wait` только ждёт. Не запускайте `run` повторно без нужды.
- Первый батч может долго ждать очередь; смотрите `b t log`.
- 8 параллельных задач могут встать в очередь.
- `merge_shards.py` предупреждает о пропущенных шардах; перед apply
  убедитесь, что скачаны все 8.
- `bench/shards/` генерируется и в `.gitignore`.
- `apply_edits.py` без `--push` только готовит локальный коммит/отчёт.

## Проверка перед финалом

1. Все 8 шардов Completed и скачаны.
2. `merge_shards.py` даёт 1506 ключей.
3. `apply_edits.py` не показывает ошибок; отчёт содержит applied/disputed.
4. Ветка `rename` на GitHub обновилась; `main` не изменён.
5. Секреты не попали в `git status`.

## Бесплатные варианты

- Kaggle AI quota: $10/день, $100/мес.
- GitHub Actions: минуты (private 2 000/мес, public без лимита), не AI-доллары.
- Локальный GPU/CPU.
- Любой OpenAI-совместимый endpoint — через адаптер, сохраняя `edits.jsonl`.

## Не делать

- Не коммитить токены, `.env`, `offline-data/`, `sc-data/`, `results/`, `logs/`.
- Не пушить в `main`.
- Не применять edits, пока не скачаны все шарды.
- Не удалять `rename` без согласования с пользователем.
- Не менять `work/insertions.yaml` без понимания, что overrides важнее модели.
