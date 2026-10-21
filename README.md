# otrn — āvuso → товарищ для MN

Пайплайн для интеллектуальной замены обращения `āvuso` в русских переводах MN:
- где стоит «друг/друзья» — заменить на «товарищ/товарищи» с инверсией
  (`друг Сарипутта` → `Сарипутта товарищ`);
- где обращение пропущено — вставить в позицию, соответствующую пали
  (`Это как если бы…` → `Это как, Моггаллана товарищ, если бы…`);
- где уже стоит «товарищи» или RU пустой — оставить и показать в «Спорных».

LLM-часть выполняется в **Kaggle Benchmarks** (AI-квота), применение — детерминированным
скриптом без ИИ.

## Структура

```
bench/task_full.py      # Benchmarks-задача: replace + insert
bench/task_sample.py    # пример на 80 сегментах
bench/task_insert.py    # только вставки
work/build_dataset.py   # сборка segments_*.jsonl из offline-data + SC Bilara
work/run_shard.py       # запуск одного шарда в Kaggle Benchmarks
work/run_full.py        # один длинный прогон (4 ч)
work/merge_shards.py    # слияние shard-*/edits.jsonl
work/apply_edits.py     # валидация, JSON-splice, rename/archive, отчёт, git push
work/insertions.yaml    # ручные правки вставок (без ИИ)
dataset/                # готовые segments_*.jsonl и manifest
examples/sample-run/    # HTML-отчёт и TSV пробного прогона
```

## Данные

- `dhammagift/offline-data` — русские переводы (`dhammagift/translation/ru`).
- `suttacentral/sc-data` — пали `sc_bilara_data/root/pli/ms` (Mahāsaṅgīti).
- `forAI/Dhamma definitions.csv` — локальный глоссарий.

Палийские тексты: SuttaCentral, Mahāsaṅgīti. Атрибуция обязательна.

## Быстрый старт

```bash
git clone git@github.com:dhammagift/otrn.git
cd otrn
python3 -m venv .venv
. .venv/bin/activate
pip install pymorphy3 pyyaml kaggle==2.2.4 kaggle-benchmarks
```

Клонировать данные:

```bash
git clone --filter=blob:none --sparse --depth 1 https://github.com/dhammagift/offline-data.git
git -C offline-data sparse-checkout set dhammagift/translation/ru forAI dhammagift/svEtc/automatic

git clone --filter=blob:none --sparse --depth 1 https://github.com/suttacentral/sc-data.git
git -C sc-data sparse-checkout set sc_bilara_data/root/pli/ms
```

Токены — только через env (никогда в git):

```bash
export KAGGLE_API_TOKEN=...
export GITHUB_TOKEN=...
export HF_TOKEN=...          # опционально
```

## Dataset

```bash
python work/build_dataset.py
kaggle datasets create -p dataset --dir-mode zip
# обновить: kaggle datasets version -p dataset -m "update" --dir-mode zip
```

## Запуск в Kaggle Benchmarks

Проверить команды:

```bash
python work/run_shard.py --index 0 --count 8 --check
```

Один шард (~189 сегментов, ~30 мин):

```bash
python work/run_shard.py --index 0 --count 8
```

8 шардов параллельно:

```bash
mkdir -p logs
for i in 0 1 2 3 4 5 6 7; do
  python work/run_shard.py --index $i --count 8 > logs/shard-$i.log 2>&1 &
done
wait
```

Модель по умолчанию — `gemini-3.8-flash`; `push` сам запускает задачу.

## Слить и применить

```bash
python work/merge_shards.py --count 8
# при необходимости поправить work/insertions.yaml
python work/apply_edits.py \
  --edits work/edits_full.jsonl \
  --config work/insertions.yaml \
  --push
```

`apply_edits.py` без ИИ: валидация, splice, rename/archive, отчёт, ветка `rename`.

## Ручные вставки без ИИ

`work/insertions.yaml`:

```yaml
use_model_insertions: true   # false = только overrides
overrides:
  "mn32:9.10":
    insert: "Моггаллана товарищ"
    anchor_before: "Это как"
    anchor_after: "если бы"
skip: []
```

Итог: `anchor_before, insert, anchor_after`.
Override работает для любого ключа из `edits_full.jsonl`.

## GitHub Actions и лимиты ИИ

GitHub Actions:
- **не даёт** AI-долларовую квоту;
- private repo — 2 000 минут/мес, public — без лимита, job до 6 ч;
- workflow `.github/workflows/run-shard.yml` только оркестрирует Kaggle.

GitHub Models — отдельный продукт с бесплатными rate-лимитами и платным usage.

Kaggle Benchmarks (наш случай):
- **$10/день, $100/мес** на hosted-модели;
- полный MN ≈ $1.9;
- GPU-квота не тратится.

То есть запускать job с GitHub можно, но расход модели остаётся на AI-квоте Kaggle
(или на ключах провайдера, если вызывать их напрямую).

## Безопасность

- `bench/.env`, `.env`, токены — в `.gitignore`.
- `KAGGLE_API_TOKEN` в GitHub Actions — через Secrets.
- Не коммитить `offline-data/`, `sc-data/`, `results/`, `logs/`.

## Лицензии

Код — MIT. Данные — по лицензиям `offline-data` / SuttaCentral Bilara;
палийские root-тексты — Mahāsaṅgīti, атрибуция SuttaCentral.
