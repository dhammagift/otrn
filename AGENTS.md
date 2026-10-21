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
work/insertions.yaml    ручные overrides: insert / replace / keep / skip
work/edits_full.jsonl   замороженный полный результат (1506)
work/manual-fixes.yaml  ручные post-фиксы после прогона (пунктуация/артефакты)
work/normalize_comrades.py  постпозиция «товарищ» + запятые (сканирует все MN)
docs/avuso-rules.md       канонические правила āvuso → товарищ
dataset/                segments_*.jsonl + manifest
examples/sample-run/    пример отчёта
.github/workflows/      run-mn.yml, apply-only.yml, run-shard.yml
```

## Текущее состояние (2026-10-21, после полного прогона)

- Все 8 шардов Completed; `results/full/shard-*/.../edits.jsonl` скачаны.
- Слито в `work/edits_full.jsonl`: 1506 строк.
- Применено: **1020** (567 replace + 453 insert), **486 disputed**, 0 errors, 0 renamed.
- Ветка `rename` в `offline-data`: `7506736`, 48 файлов, +1030/−1030, 4 коммита.
- Поверх модели применены 12 ручных post-фиксов (`work/manual-fixes.yaml`): mn103/136/144/15/28.
- `normalize_comrades.py`: 228 значений в 29 файлах — «Имя товарищ» → «Имя, товарищ», «Товарищи монахи» → «Монахи, товарищи».
- 16 точечных фиксов числа/места обращения: MN101 11.2/11.5; MN112 3.3/3.6/5.3/5.6/7.3/7.6 (мн. ч.); MN133 12.6/13.10/14.10/15.10 (мн. ч.), 17.2/17.5/18.2/18.5 (порядок слов).
- `mn103:15.5`, `16.2`, `16.4` проверены — уже корректны, не менялись.
- Осталось: 16 anchors not found, 3 lowercase name additions, 1 target count, 1 punctuation.
- `main` — `8e1e69f`; не трогать.
- Ручные правки — через `work/insertions.yaml` + workflow `apply-only`.
- Для replace разрешено добавлять одно имя с заглавной (`allow_name_addition`).
- `run-mn` — для нового прогона модели (новые `edits`).

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

Нормализация стиля (dry-run по умолчанию):

```bash
python work/normalize_comrades.py \
  --repo offline-data \
  --report out-normalize.tsv \
  --apply
```

Скачать конкретный шард:

```bash
kaggle b t download mn-avuso-full-0 -o results/full/shard-0 -f
```

## Схема edits.jsonl

```json
{"id":"mn32:9.10","file":"dhammagift/...json","key":"mn32:9.10",
 "pali":"...","ru":"...","action":"insert",
 "anchor_before":"Это как","anchor_after":"если бы","insert":"Моггаллана, товарищ",
 "source":"","target":"","old":"","new":"","reason":"","confidence":0.95}
```

`action`: `replace` | `insert` | `keep`.

## Валидация (apply_edits.py)

- `replace`: `old` есть в RU; `source` — форма «друг»; `target` — форма «товарищ»;
  после удаления source/target остальные слова совпадают (порядок может меняться);
  пунктуация, кроме запятых, та же; `confidence >= 0.75`; `old` уникален.
- `insert`: `anchor_before + anchor_after` есть в RU; `insert` содержит «товарищ»;
  итог = `anchor_before, insert, anchor_after` (в `insert` запятая уже стоит).
- Подробно: `docs/avuso-rules.md`.
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
`apply-only.yml`: применяет `work/edits_full.jsonl` + `work/insertions.yaml` без ИИ и без шардов.

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
