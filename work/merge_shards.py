#!/usr/bin/env python3
"""Merge downloaded shard edits.jsonl files into one edits_full.jsonl."""
from __future__ import annotations

import argparse
import glob
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=8)
    ap.add_argument("--dir", default=str(ROOT / "results/full"))
    ap.add_argument("--out", default=str(ROOT / "work/edits_full.jsonl"))
    args = ap.parse_args()

    rows: dict[str, dict] = {}
    files: list[str] = []
    for i in range(args.count):
        hits = sorted(glob.glob(str(Path(args.dir) / f"shard-{i}" / "**" / "edits.jsonl"), recursive=True))
        if not hits:
            print(f"WARNING: shard {i}: edits.jsonl not found", flush=True)
            continue
        path = hits[-1]
        files.append(path)
        n = 0
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            rows[row["key"]] = row
            n += 1
        print(f"shard {i}: {n} rows from {path}", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for key in rows:
            f.write(json.dumps(rows[key], ensure_ascii=False) + "\n")
    counts = Counter(r.get("action") for r in rows.values())
    print(f"merged {len(rows)} unique keys -> {out}", flush=True)
    print(f"actions: {dict(counts)}", flush=True)
    if len(rows) != 1506:
        print(f"WARNING: expected 1506 keys, got {len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
