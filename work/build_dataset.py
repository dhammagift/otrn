#!/usr/bin/env python3
"""Build the MN avuso/товарищ candidate dataset for Kaggle Benchmarks."""
from __future__ import annotations

import json
import re
import statistics
import unicodedata
from pathlib import Path

import pymorphy3

ROOT = Path(__file__).resolve().parents[1]
RU_DIR = ROOT / "offline-data/dhammagift/translation/ru/sutta/mn"
SC_DIR = ROOT / "sc-data/sc_bilara_data/root/pli/ms/sutta/mn"
OUT = ROOT / "dataset"

MORPH = pymorphy3.MorphAnalyzer()
RU_WORD = re.compile(r"[А-Яа-яЁё-]+")
NAME_AFTER = re.compile(r"(?i)\bдруг(?:а|у|ом|е)?\s+[А-ЯЁ][а-яё]+")
PLURAL_AFTER = re.compile(r"(?i)\bдрузь(?:я|ев|ям|ями|ях)\s+[а-яё]+")


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def ru_source(text: str) -> str:
    """Return the matched Russian token if the text contains a form of 'друг'."""
    for token in RU_WORD.findall(text):
        if MORPH.parse(token)[0].normal_form == "друг":
            return token
    return ""


def sc_paths() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for p in SC_DIR.glob("*_root-pli-ms.json"):
        out[p.name.removesuffix("_root-pli-ms.json")] = p
    return out


def main() -> None:
    sc = sc_paths()
    rows: list[dict] = []
    files = 0
    missing_sc = 0
    for ru_path in sorted(RU_DIR.glob("*.json")):
        stem = ru_path.name.split("_translation-", 1)[0]
        sc_file = sc.get(stem)
        if not sc_file:
            missing_sc += 1
            continue
        files += 1
        ru = json.loads(ru_path.read_text(encoding="utf-8"))
        pali = json.loads(sc_file.read_text(encoding="utf-8"))
        keys = list(ru)
        rel = str(ru_path.relative_to(ROOT / "offline-data"))
        for idx, key in enumerate(keys):
            pv = pali.get(key)
            rv = ru.get(key)
            if not isinstance(pv, str) or not isinstance(rv, str):
                continue
            if "avuso" not in fold(pv):
                continue
            prev_key = keys[idx - 1] if idx else None
            next_key = keys[idx + 1] if idx + 1 < len(keys) else None
            rows.append(
                {
                    "id": key,
                    "stem": stem,
                    "file": rel,
                    "key": key,
                    "pali": pv,
                    "ru": rv,
                    "pali_prev": pali.get(prev_key, "") if prev_key else "",
                    "pali_next": pali.get(next_key, "") if next_key else "",
                    "ru_prev": ru.get(prev_key, "") if prev_key else "",
                    "ru_next": ru.get(next_key, "") if next_key else "",
                    "ru_has_source": bool(ru_source(rv)),
                    "source_hint": ru_source(rv),
                    "plain_file": "+edited+o" not in ru_path.name,
                }
            )

    # sample: all rows from the key files, plus a spread from the rest
    sample_stems = {"mn5", "mn32", "mn119"}
    sample = [r for r in rows if r["stem"] in sample_stems]
    rest = [r for r in rows if r["stem"] not in sample_stems]
    name_rows = [r for r in rest if NAME_AFTER.search(r["ru"]) or PLURAL_AFTER.search(r["ru"])]
    src_rows = [r for r in rest if r["ru_has_source"]]
    keep_rows = [r for r in rest if not r["ru_has_source"]]
    for group, n in ((name_rows, 12), (src_rows, 12), (keep_rows, 10)):
        for r in group:
            if len(sample) >= 80:
                break
            if r not in sample:
                sample.append(r)
    sample = sample[:80]

    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in (("segments_all.jsonl", rows), ("segments_sample.jsonl", sample)):
        with (OUT / name).open("w", encoding="utf-8") as f:
            for r in data:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def commit(repo: Path) -> str:
        import subprocess

        return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    manifest = {
        "offline_data_commit": commit(ROOT / "offline-data"),
        "sc_commit": commit(ROOT / "sc-data"),
        "terms": {"pali": "āvuso", "from_ru": ["друг", "друзья"], "to_ru": "товарищ", "invert": True},
        "files": files,
        "missing_sc": missing_sc,
        "total_rows": len(rows),
        "source_rows": sum(r["ru_has_source"] for r in rows),
        "sample_rows": len(sample),
        "sample_ids": [r["id"] for r in sample],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "sample_ids"}, ensure_ascii=False, indent=2))
    print("sample files:", sorted({r["stem"] for r in sample}))
    print("median pali len:", statistics.median(len(r["pali"]) for r in rows))


if __name__ == "__main__":
    main()
