# rename-mn

MN candidate segments for the āvuso → товарищ/товарищи task with inversion.

Files:
- `segments_sample.jsonl` — 80 segments (mn5, mn32, mn119 + spread)
- `segments_all.jsonl` — 1506 segments (all MN segments whose Pali contains āvuso)
- `manifest.json` — commits, counts, terms

Each row: id, file, key, pali, ru, pali_prev/next, ru_prev/next, ru_has_source, source_hint, plain_file.
Source data: dhammagift/offline-data (RU) and suttacentral/sc-data (Pali, Mahāsaṅgīti).
