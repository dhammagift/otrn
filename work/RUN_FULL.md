# Полный MN по частям

Из корня репозитория:

```bash
python work/run_shard.py --index 0 --count 8 --check
```

## 8 шардов по ~30 минут

```bash
for i in 0 1 2 3 4 5 6 7; do
  python work/run_shard.py --index $i --count 8
done
```

Параллельно:

```bash
mkdir -p logs
for i in 0 1 2 3 4 5 6 7; do
  python work/run_shard.py --index $i --count 8 > logs/shard-$i.log 2>&1 &
done
wait
```

Для часовых кусков: `--count 4`, индексы `0..3`.

## Мониторинг

```bash
kaggle b t status mn-avuso-full-0
kaggle b t log mn-avuso-full-0 -m gemini-3.8-flash
```

## Слить и применить

```bash
python work/merge_shards.py --count 8
# при необходимости: nano work/insertions.yaml
python work/apply_edits.py \
  --edits work/edits_full.jsonl \
  --config work/insertions.yaml \
  --push
```

## Стоимость

- 8 шардов: ~30 минут каждый, ~$0.24 за шард, ~$1.9 за весь MN.
- GPU-квота не тратится.
- Упавший шард — повторите тот же `--index`, merge подхватит остальные.
