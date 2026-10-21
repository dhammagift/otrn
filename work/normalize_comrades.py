#!/usr/bin/env python3
"""Normalize 'товарищ' style in MN translations.

Rules:
  * <Name> товарищ        -> <Name>, товарищ
  * Товарищи монахи       -> Монахи, товарищи
  * Товарищ <Name>        -> <Name>, товарищ   (if no comma)
  * already <Name>, товарищ stays

Dry-run by default; --apply writes files. Report is TSV.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

T = r"товарищ(?:а|у|ем|е|и|ей|ам|ами|ах)?"
POST = re.compile(r"(?<![\w-])([А-ЯЁ][а-яё-]+)([ \t]+)(" + T + r")(?![\w-])")
GROUP = re.compile(r"(?<![\w-])Товарищи[ \t]+(монахи|монахов|монахам|монахами|монахах)(?![\w-])", re.I)
PRE = re.compile(r"(?<![\w-])(Товарищ(?:а|у|ем|е|и|ей|ам|ами|ах)?)[ \t]+([А-ЯЁ][а-яё-]+)")
# Common nouns/determiners that are not addresses.
SKIP = {"Наши", "Мои", "Его", "Её", "Их", "Ваши", "Все", "Эти", "Те", "Другие", "Близкие", "Родные", "Такие"}


def find_value_span(raw: str, key: str) -> tuple[int, int]:
    key_lit = json.dumps(key, ensure_ascii=False)
    i = raw.index(key_lit)
    j = i + len(key_lit)
    while raw[j] in " \t":
        j += 1
    if raw[j] != ":":
        raise ValueError("expected ':'")
    j += 1
    while raw[j] in " \t":
        j += 1
    value, end = json.JSONDecoder().raw_decode(raw, j)
    return j, end


def normalize(text: str) -> tuple[str, list[tuple[str, str, str]]]:
    changes: list[tuple[str, str, str]] = []

    def post(m: re.Match) -> str:
        name, ws, tgt = m.group(1), m.group(2), m.group(3)
        if name in SKIP:
            return m.group(0)
        changes.append(("post", m.group(0), f"{name}, {tgt}"))
        return f"{name}, {tgt}"

    text = POST.sub(post, text)

    def group(m: re.Match) -> str:
        noun = m.group(1)
        new_noun = noun[0].upper() + noun[1:]
        changes.append(("group", m.group(0), f"{new_noun}, товарищи"))
        return f"{new_noun}, товарищи"

    text = GROUP.sub(group, text)

    def pre(m: re.Match) -> str:
        tgt, name = m.group(1), m.group(2)
        changes.append(("pre", m.group(0), f"{name}, {tgt.lower()}"))
        return f"{name}, {tgt.lower()}"

    text = PRE.sub(pre, text)
    return text, changes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(ROOT / "offline-data"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", default=str(ROOT / "out-normalize.tsv"))
    args = ap.parse_args()

    base = Path(args.repo) / "dhammagift/translation/ru/sutta/mn"
    rows: list[dict] = []
    for path in sorted(base.glob("*.json")):
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        spans = []
        for key, value in data.items():
            if not isinstance(value, str) or "товарищ" not in value.lower():
                continue
            new, changes = normalize(value)
            if not changes:
                continue
            rows.append(
                {
                    "file": str(path.relative_to(args.repo)),
                    "key": key,
                    "rules": ",".join(c[0] for c in changes),
                    "before": value,
                    "after": new,
                }
            )
            s, e = find_value_span(raw, key)
            spans.append((s, e, json.dumps(new, ensure_ascii=False)))
        for s, e, lit in sorted(spans, reverse=True):
            raw = raw[:s] + lit + raw[e:]
        if spans and args.apply:
            json.loads(raw)
            path.write_text(raw, encoding="utf-8")

    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8") as f:
        f.write("file\tkey\trules\tbefore\tafter\n")
        for r in rows:
            f.write(
                "\t".join(
                    str(r[k]).replace("\t", " ").replace("\n", " ")
                    for k in ("file", "key", "rules", "before", "after")
                )
                + "\n"
            )
    counts = Counter()
    for r in rows:
        for rule in r["rules"].split(","):
            counts[rule] += 1
    print(f"{'applied' if args.apply else 'dry-run'}: {len(rows)} values, {dict(counts)}")
    print(f"report: {report}")
    for r in rows[:10]:
        print(r["key"], "|", r["rules"], "|", r["before"][:80], "=>", r["after"][:80])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
