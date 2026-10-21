#!/usr/bin/env python3
"""Run one shard of the full MN task on Kaggle Benchmarks.

Examples:
  python work/run_shard.py --index 0 --count 8   # ~30 min
  python work/run_shard.py --index 1 --count 8
  python work/run_shard.py --index 0 --count 4   # ~1 h
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "bench/task_full.py"
SHARDS = ROOT / "bench/shards"
def kaggle_cmd() -> list[str]:
    if os.environ.get("KAGGLE_CMD"):
        return shlex.split(os.environ["KAGGLE_CMD"])
    uvx = Path("/root/.local/bin/uvx")
    if uvx.exists():
        return [str(uvx), "--python", "3.12", "kaggle@2.2.4"]
    return ["kaggle"]


KAGGLE = kaggle_cmd()
DATASET = os.environ.get("KAGGLE_DATASET", "dhammagift/rename-mn")


def load_env() -> dict[str, str]:
    env = dict(os.environ)
    secrets = Path("/root/.secrets/tools.env")
    if secrets.exists():
        for line in secrets.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env.setdefault(key, value.strip().strip("'\""))
    return env


def make_task(index: int, count: int) -> Path:
    SHARDS.mkdir(parents=True, exist_ok=True)
    src = TEMPLATE.read_text(encoding="utf-8")
    src = src.replace(
        'SEGMENTS_FILE = "segments_all.jsonl"',
        f'SEGMENTS_FILE = "segments_all.jsonl"\nSHARD_INDEX = {index}\nSHARD_COUNT = {count}',
    )
    old = (
        '    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]\n'
        '    print(f"segments: {len(rows)} from {path}", flush=True)\n'
        '    return rows'
    )
    new = (
        '    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]\n'
        '    size = (len(rows) + SHARD_COUNT - 1) // SHARD_COUNT\n'
        '    rows = rows[SHARD_INDEX * size : (SHARD_INDEX + 1) * size]\n'
        '    print(f"shard {SHARD_INDEX + 1}/{SHARD_COUNT}: {len(rows)} rows from {path}", flush=True)\n'
        '    return rows'
    )
    if old not in src:
        raise SystemExit("could not find load_rows block in task_full.py")
    src = src.replace(old, new)
    src = src.replace('name="mn-avuso-full"', f'name="mn-avuso-full-{index}"')
    src = src.replace(
        'description="Full MN: āvuso -> товарищ (replace + insert omissions)"',
        f'description="Full MN shard {index + 1}/{count}: āvuso -> товарищ (replace + insert)"',
    )
    out = SHARDS / f"task_full_{index}.py"
    out.write_text(src, encoding="utf-8")
    subprocess.run([sys.executable, "-m", "py_compile", str(out)], check=True)
    return out


def run(cmd: list[str], env: dict[str, str]) -> None:
    print("+", " ".join(shlex.quote(x) for x in cmd), flush=True)
    subprocess.run(cmd, check=True, env=env)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, required=True)
    ap.add_argument("--count", type=int, default=8)
    ap.add_argument("--out", default=str(ROOT / "results/full"))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--generate-only", action="store_true")
    args = ap.parse_args()
    if not (0 <= args.index < args.count):
        raise SystemExit("index must be 0 <= index < count")

    task = make_task(args.index, args.count)
    slug = f"mn-avuso-full-{args.index}"
    out = Path(args.out) / f"shard-{args.index}"
    push = KAGGLE + ["benchmarks", "tasks", "push", slug, "-f", str(task), "-d", DATASET, "--wait"]
    download = KAGGLE + ["benchmarks", "tasks", "download", slug, "-o", str(out), "-f"]
    if args.check:
        print("push:    ", " ".join(shlex.quote(x) for x in push))
        print("download:", " ".join(shlex.quote(x) for x in download))
        print(f"edits:    {out}/**/edits.jsonl")
        return 0
    if args.generate_only:
        print(task)
        return 0

    env = load_env()
    if not env.get("KAGGLE_API_TOKEN"):
        raise SystemExit("KAGGLE_API_TOKEN not found in /root/.secrets/tools.env")
    print(f"Shard {args.index + 1}/{args.count}: ~30 min, ~$0.24 at 8 shards.", flush=True)
    run(push, env)
    run(download, env)
    print(f"\nshard {args.index} downloaded to {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
