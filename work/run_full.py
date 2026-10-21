#!/usr/bin/env python3
"""Run the full MN āvuso task on Kaggle Benchmarks and optionally apply it.

Usage:
  cd /root/rename
  . .venv/bin/activate
  python work/run_full.py --check          # только показать команды
  python work/run_full.py                  # push + run + download (≈4 ч)
  python work/run_full.py --apply          # + применить и запушить ветку rename

The Benchmarks push auto-runs the task on the default model
(google/gemini-3.8-flash).  Full MN = 1506 segments, 189 batches.
"""
from __future__ import annotations

import argparse
import glob
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def kaggle_cmd() -> list[str]:
    if os.environ.get("KAGGLE_CMD"):
        return shlex.split(os.environ["KAGGLE_CMD"])
    uvx = Path("/root/.local/bin/uvx")
    if uvx.exists():
        return [str(uvx), "--python", "3.12", "kaggle@2.2.4"]
    return ["kaggle"]


KAGGLE = kaggle_cmd()
TASK = ROOT / "bench/task_full.py"
DATASET = os.environ.get("KAGGLE_DATASET", "dhammagift/rename-mn")
SLUG = "mn-avuso-full"
CONFIG = ROOT / "work/insertions.yaml"
OUT = ROOT / "results/full"


def load_env() -> dict[str, str]:
    env = dict(os.environ)
    secrets = Path("/root/.secrets/tools.env")
    if secrets.exists():
        for line in secrets.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip("'\"")
            env.setdefault(key, value)
    return env


def run(cmd: list[str], env: dict[str, str]) -> None:
    print("+", " ".join(shlex.quote(x) for x in cmd), flush=True)
    subprocess.run(cmd, check=True, env=env)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="apply downloaded edits and push branch rename")
    ap.add_argument("--check", action="store_true", help="print commands without running")
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    env = load_env()
    if not TASK.exists():
        raise SystemExit(f"missing task file: {TASK}")
    if not env.get("KAGGLE_API_TOKEN"):
        raise SystemExit("KAGGLE_API_TOKEN not found in /root/.secrets/tools.env")

    push = KAGGLE + [
        "benchmarks",
        "tasks",
        "push",
        SLUG,
        "-f",
        str(TASK),
        "-d",
        DATASET,
        "--wait",
    ]
    download = KAGGLE + ["benchmarks", "tasks", "download", SLUG, "-o", args.out, "-f"]

    if args.check:
        print("push:    ", " ".join(shlex.quote(x) for x in push))
        print("download:", " ".join(shlex.quote(x) for x in download))
        print("apply:   ", f"python {ROOT / 'work/apply_edits.py'} --edits <edits.jsonl> --config {args.config} --push")
        return 0

    print("Full MN: 1506 segments, ~189 batches, ≈4 hours on the default model.", flush=True)
    print("Tip: run in tmux/nohup; the Kaggle task keeps running if this shell stops.", flush=True)
    run(push, env)
    run(download, env)

    hits = sorted(glob.glob(str(Path(args.out) / "**" / "edits.jsonl"), recursive=True))
    if not hits:
        raise SystemExit(f"edits.jsonl not found under {args.out}")
    edits = hits[-1]
    print(f"\nedits: {edits}", flush=True)
    print(f"report/apply: python {ROOT / 'work/apply_edits.py'} --edits {shlex.quote(edits)} --config {args.config} --push", flush=True)

    if args.apply:
        run(
            [
                sys.executable,
                str(ROOT / "work/apply_edits.py"),
                "--edits",
                edits,
                "--config",
                args.config,
                "--model",
                "gemini-3.8-flash (full MN)",
                "--push",
            ],
            env,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
