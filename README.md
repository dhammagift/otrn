# otrn — āvuso → товарищ для MN

Пайплайн для интеллектуальной правки обращения `āvuso` в русских переводах MN:

- где стоит «друг/друзья» → «товарищ/товарищи»;
- инверсия при имени/существительном: `друг Сарипутта` → `Сарипутта товарищ`;
- где обращение пропущено → вставка в позицию пали:
  `Это как если бы…` → `Это как, Моггаллана товарищ, если бы…`;
- где уже «товарищи» или пустой RU → «Спорные моменты», без правки.

LLM-часть — **Kaggle Benchmarks** (AI-квота). Применение — детерминированный скрипт без ИИ.

## Бесплатные варианты

- **Kaggle Benchmarks**: $10/день и $100/мес на hosted-модели. Полный MN ≈ $1.9.
- **GitHub Actions**: public repo — без лимита минут; private — 2 000 мин/мес.
  Это минуты, не AI-доллары.
- **Локально**: Qwen3.8-27B на T4×2 или 9B на CPU — без AI-квоты.
- **Свой OpenAI-совместимый endpoint**: замените вызов `llm.prompt` в
  `bench/task_full.py` на адаптер; схему `edits.jsonl` сохраните.

## TL;DR для человека

```bash
git clone git@github.com:dhammagift/otrn.git
cd otrn

python3 -m venv .venv
. .venv/bin/activate
pip install pymorphy3 pyyaml kaggle==2.2.4 kaggle-benchmarks

# данные (один раз)
git clone --filter=blob:none --sparse --depth 1 https://github.com/dhammagift/offline-data.git
git -C offline-data sparse-checkout set dhammagift/translation/ru forAI dhammagift/svEtc/automatic
git clone --filter=blob:none --sparse --depth 1 https://github.com/suttacentral/sc-data.git
git -C sc-data sparse-checkout set sc_bilara_data/root/pli/ms

# токены — только в env
export KAGGLE_API_TOKEN=...
export GITHUB_TOKEN=...

# проверить
python work/run_shard.py --index 0 --count 8 --check

# 8 шардов, ~30 мин каждый
for i in 0 1 2 3 4 5 6 7; do
  python work/run_shard.py --index $i --count 8
done

# слить и применить
python work/merge_shards.py --count 8
# при необходимости: nano work/insertions.yaml
python work/apply_edits.py \
  --edits work/edits_full.jsonl \
  --config work/insertions.yaml \
  --push
```

Результат: ветка `rename` в `dhammagift/offline-data` + HTML-отчёт.

## Подробно

### 1. Данные

- `dhammagift/offline-data` — русские переводы.
- `suttacentral/sc-data` — пали `sc_bilara_data/root/pli/ms` (Mahāsaṅgīti).
- `forAI/Dhamma definitions.csv` — глоссарий.

Пали: SuttaCentral, Mahāsaṅgīti. Атрибуция обязательна.

### 2. Dataset

`dataset/` уже содержит готовые `segments_*.jsonl`. Пересобрать:

```bash
python work/build_dataset.py
kaggle datasets create -p dataset --dir-mode zip
# или: kaggle datasets version -p dataset -m "update" --dir-mode zip
```

Датасет: `dhammagift/rename-mn`.

### 3. Шарды

- 8 шардов — по ~189 сегментов, ~30 мин.
- 4 шарда — по ~377, ~1 ч.

```bash
python work/run_shard.py --index 0 --count 8 --check
python work/run_shard.py --index 0 --count 8
```

Параллельно:

```bash
mkdir -p logs
for i in 0 1 2 3 4 5 6 7; do
  python work/run_shard.py --index $i --count 8 > logs/shard-$i.log 2>&1 &
done
wait
```

Мониторинг:

```bash
kaggle b t status mn-avuso-full-0
kaggle b t log mn-avuso-full-0 -m gemini-3.8-flash
```

### 4. Слить и применить

```bash
python work/merge_shards.py --count 8
python work/apply_edits.py \
  --edits work/edits_full.jsonl \
  --config work/insertions.yaml \
  --push
```

`apply_edits.py`:
- валидирует `replace`/`insert`;
- правит JSON точечным splice;
- plain-файлы с правками → `+edited+o`, оригинал → `dhammagift/svEtc/automatic/`;
- собирает `report.html`/`report.md`/TSV;
- делает один коммит и force-push в `rename`.

## Ручные вставки без ИИ

`work/insertions.yaml`:

```yaml
use_model_insertions: true   # false = только overrides
separator: ", "
overrides:
  "mn32:9.10":
    insert: "Моггаллана товарищ"
    anchor_before: "Это как"
    anchor_after: "если бы"
skip: []
```

- `anchor_before`/`anchor_after` — точные подстроки из RU.
- Итог: `anchor_before, insert, anchor_after`.
- Override работает для любого ключа, даже если модель сказала `keep`.

## Веб-режим: всем рулить из репозитория

Секреты — **только** в GitHub Actions Secrets, не в файлах git:

Settings → Secrets and variables → Actions → New repository secret:

- `KAGGLE_API_TOKEN` — токен Kaggle (тот же, что в `~/.secrets/tools.env`).
- `OFFLINE_DATA_SSH_KEY` — приватный SSH deploy key с write-доступом
  к `dhammagift/offline-data` (нужен, чтобы workflow пушил ветку `rename`).

Секрет шифруется, после сохранения не показывается и в логи не попадает.
**Не коммитить токены в репозиторий.**

### Deploy key без PAT

Обычный `GITHUB_TOKEN` не может пушить в другой репозиторий, поэтому нужен deploy key:

```bash
ssh-keygen -t ed25519 -C "otrn-actions" -f ~/otrn_deploy -N ""
cat ~/otrn_deploy.pub
# offline-data -> Settings -> Deploy keys -> Add deploy key
#   -> вставить публичный ключ -> Allow write access
cat ~/otrn_deploy
# otrn -> Settings -> Secrets and variables -> Actions
#   -> OFFLINE_DATA_SSH_KEY -> вставить приватный ключ
```

Workflow сам добавляет `github.com` в `known_hosts` и клонирует
`git@github.com:dhammagift/offline-data.git`.

### Полный прогон

Actions → **run-mn** → Run workflow:

- 8 шардов запускаются параллельно (matrix 0..7);
- каждый ~30–40 минут;
- job `apply` скачивает артефакты, сливает, применяет и пушит `rename`;
- артефакт `reports` — HTML/MD/TSV.

`apply: false` — только шарды и артефакты, без пуша ветки.

### Один шард

Actions → **kaggle-shard** → Run workflow (index, count).
Артефакт `shard-N` содержит `edits.jsonl`.

GitHub Actions **не даёт AI-квоту**: он только дёргает Kaggle API.
Расход модели — на AI-квоте Kaggle (или на ключах провайдера).

Лимиты GitHub Actions: private — 2 000 минут/мес, public — без лимита.
Один полный прогон (8 шардов) ≈ 320 минут private.

## Лимиты

- Kaggle AI: $10/день, $100/мес; полный MN ≈ $1.9.
- GPU-квота не тратится при Benchmarks.
- GitHub Actions: private 2 000 мин/мес, public без лимита.
- GitHub Models: отдельный продукт, свои rate-лимиты/оплата.

## Если что-то не так

- `kaggle: command not found` — активируйте `.venv` или используйте `.venv/bin/kaggle`.
- `Authentication required` — `set -a; . /root/.secrets/tools.env; set +a` или `export KAGGLE_API_TOKEN`.
- Задача ещё не создана — `status` до первого `run_shard` не найдёт её.
- Шард упал — повторите тот же `--index`; `merge_shards` предупредит о пропуске.
- 8 параллельных задач могут встать в очередь — это нормально.

## Безопасность

- `.env`, `bench/.env`, токены — в `.gitignore`; не коммитить.
- `offline-data/`, `sc-data/`, `results/`, `logs/` — не коммитить.
- `KAGGLE_API_TOKEN` в Actions — только через Secrets.

## Лицензии

Код — MIT. Данные — по лицензиям `offline-data` / SuttaCentral Bilara;
палийские root-тексты — Mahāsaṅgīti, атрибуция SuttaCentral.
