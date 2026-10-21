#!/usr/bin/env python3
"""Apply Benchmarks edits to offline-data, insert omitted addresses, rename/archive, report, push."""
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pymorphy3
import yaml

ROOT = Path(__file__).resolve().parents[1]
MORPH = pymorphy3.MorphAnalyzer()
WORD = re.compile(r"[А-Яа-яЁёA-Za-z]+(?:-[А-Яа-яЁёA-Za-z]+)*")
PUNCT = re.compile(r"[^\w\s]")
REPO_URL = os.environ.get("REPO_URL", "https://github.com/dhammagift/offline-data")
ARCHIVE = "dhammagift/svEtc/automatic"
CONF_MIN = 0.75
MAX_WORDS = 12


def lemma(word: str) -> str:
    return MORPH.parse(word)[0].normal_form if word else ""


def words(text: str) -> list[str]:
    return WORD.findall(text)


def punct(text: str) -> list[str]:
    return PUNCT.findall(text)


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


def remove_ci(text: str, sub: str) -> str | None:
    i = text.casefold().find(sub.casefold())
    if i < 0:
        return None
    return text[:i] + text[i + len(sub) :]


def validate_replace(edit: dict, allow_name_addition: bool = True) -> tuple[bool, str]:
    if edit.get("action") != "replace":
        return False, "not replace"
    source = edit.get("source") or ""
    target = edit.get("target") or ""
    old = edit.get("old") or ""
    new = edit.get("new") or ""
    ru = edit.get("ru") or ""
    if not old or not new:
        return False, "empty old/new"
    if not ru:
        return False, "empty RU segment"
    if old not in ru:
        return False, "old not found in RU"
    # The model sometimes returns only old/new (no source/target).
    # Infer them, then replace ALL occurrences so "друг … друг" -> "товарищ … товарищ" works.
    if not source:
        source = next((w for w in words(old) if lemma(w) == "друг"), "")
    if not target:
        target = next((w for w in words(new) if lemma(w) == "товарищ"), "")
    if not source or source.casefold() not in old.casefold():
        return False, "source not in old"
    if not target or target.casefold() not in new.casefold():
        return False, "target not in new"
    old_count = len(re.findall(re.escape(source), old, flags=re.IGNORECASE))
    new_count = len(re.findall(re.escape(target), new, flags=re.IGNORECASE))
    if old_count != new_count:
        return False, "target count changed"
    old_wo = re.sub(re.escape(source), "", old, flags=re.IGNORECASE)
    new_wo = re.sub(re.escape(target), "", new, flags=re.IGNORECASE)
    if ru.count(old) != 1:
        return False, "old is not unique"
    if lemma(source) != "друг":
        return False, f"source lemma is {lemma(source)!r}, not 'друг'"
    if lemma(target) != "товарищ":
        return False, f"target lemma is {lemma(target)!r}, not 'товарищ'"
    if len(words(old)) > MAX_WORDS:
        return False, "span too long"
    co = Counter(w.casefold() for w in words(old_wo))
    cn = Counter(w.casefold() for w in words(new_wo))
    if list((co - cn).elements()):
        return False, "other words changed"
    extra = list((cn - co).elements())
    if extra:
        if not allow_name_addition or len(extra) != 1:
            return False, "other words changed"
        extra_word = next((w for w in words(new_wo) if w.casefold() == extra[0]), "")
        if not extra_word or not extra_word[0].isupper():
            return False, "other words changed"
    if punct(old) != punct(new):
        return False, "punctuation changed"
    if float(edit.get("confidence") or 0) < CONF_MIN:
        return False, "low confidence"
    if old == new:
        return False, "old == new"
    return True, "ok"


def normalize_insert(edit: dict, cfg: dict) -> tuple[dict | None, str]:
    key = edit.get("key", "")
    overrides = cfg.get("overrides") or {}
    ov = overrides.get(key) or {}
    if not cfg.get("enabled", True):
        return None, "insertions disabled"
    if key in (cfg.get("skip") or []):
        return None, "skip list"
    if ov.get("action") == "keep":
        return None, "override keep"
    if key not in overrides and not cfg.get("use_model_insertions", True):
        return None, "model insertions disabled"

    def pick(name: str, default: str = "") -> str:
        if name in ov:
            return str(ov.get(name) or "")
        return str(edit.get(name) or default)

    insert_text = pick("insert").strip(" ,")
    before_raw = pick("anchor_before")
    after_raw = pick("anchor_after")
    before = before_raw.rstrip(" ,")
    after = after_raw.lstrip(" ,")
    ru = edit.get("ru") or ""
    if not ru:
        return None, "empty RU segment"
    if not insert_text:
        return None, "empty insert"
    if not any(lemma(w) == "товарищ" for w in words(insert_text)):
        return None, "insert has no 'товарищ'"
    if not before and not after:
        before_raw, after_raw = "", ru.rstrip()
        before, after = "", ru.rstrip()
    # Build the exact old substring from the raw anchors. If the user's
    # override omits the boundary space, add it.
    if before_raw and after_raw:
        left, right = before_raw[-1], after_raw[0]
        opening = "“«„("
        closing = "”»).,;:!?…"
        if left.isspace() or right.isspace() or left in opening or right in closing:
            # “ + По, же, + монах, давно + . Три — без лишнего пробела
            combined = before_raw + after_raw
        else:
            # же, + монах -> "же, монах"
            combined = before_raw + " " + after_raw
    else:
        combined = before_raw + after_raw
    combined = combined.strip()
    if combined not in ru:
        return None, "anchors not found"
    if ru.count(combined) != 1:
        return None, "anchors not unique"
    sep = cfg.get("separator", ", ")
    if before and after:
        new = f"{before}{sep}{insert_text}{sep}{after}"
    elif before:
        new = f"{before}{sep}{insert_text}"
    elif after:
        new = f"{insert_text}{sep}{after}"
    else:
        new = insert_text
    new = re.sub(r"\s*,\s*,+", ",", new)
    if new == ru:
        return None, "insert is a no-op"
    norm = {
        **edit,
        "action": "insert",
        "source": "",
        "target": insert_text,
        "old": combined,
        "new": new,
        "insert": insert_text,
        "anchor_before": before,
        "anchor_after": after,
        "insert_source": "override" if key in overrides else "model",
    }
    return norm, "ok"


def classify(edit: dict, cfg: dict) -> tuple[str, str, dict]:
    key = edit.get("key", "")
    if key in (cfg.get("skip") or []):
        return "disputed", "skip list", edit
    ov = (cfg.get("overrides") or {}).get(key) or {}
    if ov.get("action") == "keep":
        return "disputed", "override keep", edit
    # Manual replace: override old/new (and optionally source/target).
    if ov.get("action") == "replace":
        e = {**edit, "action": "replace"}
        for field in ("source", "target", "old", "new"):
            if field in ov:
                e[field] = ov[field]
        ok, why = validate_replace(e, cfg.get("allow_name_addition", True))
        return ("applied", "ok", e) if ok else ("disputed", why, e)
    # A manual override can turn any row (even a model "keep") into an insert.
    if ov and (ov.get("insert") or ov.get("anchor_before") or ov.get("anchor_after")):
        norm, why = normalize_insert({**edit, "action": "insert"}, cfg)
        if norm:
            return "applied", "ok", norm
        return "disputed", why, edit
    action = edit.get("action")
    if action == "insert":
        norm, why = normalize_insert(edit, cfg)
        if norm:
            return "applied", "ok", norm
        return "disputed", why, edit
    if action == "replace":
        ok, why = validate_replace(edit, cfg.get("allow_name_addition", True))
        if ok:
            return "applied", "ok", edit
        return "disputed", why, edit
    return "disputed", f"keep: {edit.get('reason') or 'model kept'}", edit


def load_segments(edits_path: Path) -> list[dict]:
    return [json.loads(line) for line in edits_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_config(path: Path | None) -> dict:
    cfg = {
        "enabled": True,
        "use_model_insertions": True,
        "allow_name_addition": True,
        "separator": ", ",
        "overrides": {},
        "skip": [],
    }
    if path and path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cfg.update(data)
    return cfg


def apply_file(repo: Path, rel: str, edits: list[dict]) -> None:
    path = repo / rel
    if not path.exists():
        raise FileNotFoundError(rel)
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    updates: dict[str, str] = {}
    for e in edits:
        key = e["key"]
        if key not in data:
            raise KeyError(f"{rel}: key {key} not found")
        current = updates.get(key, data[key])
        if e["old"] not in current:
            raise ValueError(f"{rel}: old not in current value for {key}")
        updates[key] = current.replace(e["old"], e["new"], 1)
    spans = []
    for key, new_value in updates.items():
        start, end = find_value_span(raw, key)
        spans.append((start, end, json.dumps(new_value, ensure_ascii=False)))
    for start, end, new_lit in sorted(spans, key=lambda x: x[0], reverse=True):
        raw = raw[:start] + new_lit + raw[end:]
    json.loads(raw)
    path.write_text(raw, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("OFFLINE_DATA_DIR", str(ROOT / "offline-data")))
    ap.add_argument("--edits", required=True)
    ap.add_argument("--out", default=str(ROOT / "out"))
    ap.add_argument("--config", default=str(ROOT / "work/insertions.yaml"))
    ap.add_argument("--branch", default="rename")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--model", default="")
    args = ap.parse_args()

    repo = Path(args.repo)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config(Path(args.config) if args.config else None)
    edits = load_segments(Path(args.edits))
    rows: list[dict] = []
    for e in edits:
        status, why, norm = classify(e, cfg)
        rows.append({**norm, "status": status, "disputed_reason": why})
    applied = [r for r in rows if r["status"] == "applied"]
    disputed = [r for r in rows if r["status"] == "disputed"]
    inserts = [r for r in applied if r.get("action") == "insert"]
    replaces = [r for r in applied if r.get("action") == "replace"]
    print(f"edits={len(rows)} applied={len(applied)} (replace={len(replaces)}, insert={len(inserts)}) disputed={len(disputed)}")

    subprocess.run(["git", "-C", str(repo), "fetch", "--depth", "1", "origin", "main"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-B", args.branch, "origin/main"], check=True)
    subprocess.run(["git", "-C", str(repo), "reset", "--hard", "origin/main"], check=True)

    by_file: dict[str, list[dict]] = defaultdict(list)
    for e in applied:
        by_file[e["file"]].append(e)

    renamed: list[tuple[str, str]] = []
    errors: list[dict] = []
    for rel, file_edits in sorted(by_file.items()):
        try:
            path = repo / rel
            if not path.exists():
                raise FileNotFoundError(rel)
            name = path.name
            if "+edited+o" not in name:
                new_name = name[: -len(".json")] + "+edited+o.json"
                new_rel = str(Path(rel).with_name(new_name))
                counterpart = repo / new_rel
                if counterpart.exists():
                    raise RuntimeError(f"counterpart exists: {new_rel}")
                archive_rel = f"{ARCHIVE}/{name}"
                archive = repo / archive_rel
                archive.parent.mkdir(parents=True, exist_ok=True)
                if archive.exists() and archive.read_bytes() != path.read_bytes():
                    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    archive = archive.with_name(archive.stem + f".{stamp}.json")
                    archive_rel = str(archive.relative_to(repo))
                if not archive.exists():
                    shutil.copy2(path, archive)
                subprocess.run(["git", "-C", str(repo), "mv", rel, new_rel], check=True)
                rel = new_rel
                renamed.append((rel, archive_rel))
            apply_file(repo, rel, file_edits)
        except Exception as exc:  # noqa: BLE001
            errors.append({"file": rel, "error": f"{type(exc).__name__}: {exc}"})
            print(f"ERROR {rel}: {exc}")

    def esc(x: object) -> str:
        return html.escape(str(x or ""))

    applied_html = "\n".join(
        f"<tr><td>{esc(r.get('action','replace'))}</td><td>{esc(r['file'])}</td><td>{esc(r['key'])}</td><td>{esc(r['old'])}</td><td>{esc(r['new'])}</td><td>{esc(r.get('reason',''))}</td><td>{r['confidence']:.2f}</td></tr>"
        for r in applied
    )
    inserts_html = "\n".join(
        f"<tr><td>{esc(r['key'])}</td><td>{esc(r.get('ru',''))}</td><td>{esc(r.get('anchor_before',''))}</td><td>{esc(r.get('insert',''))}</td><td>{esc(r.get('anchor_after',''))}</td><td>{esc(r['new'])}</td><td>{esc(r.get('insert_source',''))}</td><td>{r['confidence']:.2f}</td></tr>"
        for r in inserts
    )
    def proposal(r: dict) -> str:
        if r.get("action") == "insert":
            return f"{r.get('anchor_before','')} + «{r.get('insert','')}» + {r.get('anchor_after','')}"
        return f"{r.get('old','')} → {r.get('new','')}"

    disputed_html = "\n".join(
        f"<tr><td>{esc(r['file'])}</td><td>{esc(r['key'])}</td><td>{esc(r.get('pali',''))}</td><td>{esc(r.get('ru',''))}</td><td>{esc(proposal(r))}</td><td>{esc(r['disputed_reason'])}</td><td>{r['confidence']:.2f}</td></tr>"
        for r in disputed
    )
    html_doc = f"""<!doctype html><html lang="ru"><meta charset="utf-8">
<title>MN āvuso → товарищ: отчёт</title>
<style>
body{{font:14px/1.45 system-ui,sans-serif;margin:24px;color:#111}}
h1{{font-size:20px}} h2{{margin-top:32px;font-size:17px}}
table{{border-collapse:collapse;width:100%;margin-top:8px}}
th,td{{border:1px solid #ddd;padding:6px;vertical-align:top;text-align:left}}
th{{background:#f6f6f6;position:sticky;top:0}}
tr:nth-child(even){{background:#fafafa}}
.card{{display:inline-block;border:1px solid #ddd;border-radius:8px;padding:10px 14px;margin:4px 8px 4px 0}}
input[type=search]{{padding:6px;width:320px;margin:8px 0}}
.small{{color:#666;font-size:12px}}
</style>
<h1>MN: āvuso → товарищ / товарищи</h1>
<p class="small">model: {esc(args.model)} · replace {len(replaces)} · insert {len(inserts)} · disputed {len(disputed)} · renamed {len(renamed)} · errors {len(errors)}</p>
<div>
<span class="card">replace <b>{len(replaces)}</b></span>
<span class="card">insert <b>{len(inserts)}</b></span>
<span class="card">disputed <b>{len(disputed)}</b></span>
<span class="card">renamed <b>{len(renamed)}</b></span>
<span class="card">errors <b>{len(errors)}</b></span>
</div>
<h2>Применено</h2>
<input type="search" placeholder="фильтр..." oninput="for(const r of document.querySelectorAll('#applied tbody tr')) r.style.display=r.innerText.toLowerCase().includes(this.value.toLowerCase())?'':'none'">
<table id="applied"><thead><tr><th>Тип</th><th>Файл</th><th>Ключ</th><th>Было</th><th>Стало</th><th>Причина</th><th>Conf</th></tr></thead><tbody>{applied_html}</tbody></table>
<h2>Вставки (пропуски)</h2>
<p class="small">Позицию можно поправить в <code>{esc(args.config)}</code> и перезапустить apply без ИИ.</p>
<table id="inserts"><thead><tr><th>Ключ</th><th>Сейчас</th><th>anchor_before</th><th>insert</th><th>anchor_after</th><th>Итог</th><th>Источник</th><th>Conf</th></tr></thead><tbody>{inserts_html}</tbody></table>
<h2>Спорные моменты</h2>
<input type="search" placeholder="фильтр..." oninput="for(const r of document.querySelectorAll('#disputed tbody tr')) r.style.display=r.innerText.toLowerCase().includes(this.value.toLowerCase())?'':'none'">
<table id="disputed"><thead><tr><th>Файл</th><th>Ключ</th><th>Пали</th><th>Сейчас</th><th>Предложено</th><th>Почему спорно</th><th>Conf</th></tr></thead><tbody>{disputed_html}</tbody></table>
<h2>Переименования</h2>
<table><thead><tr><th>Новый файл</th><th>Архив</th></tr></thead><tbody>{''.join(f'<tr><td>{esc(a)}</td><td>{esc(b)}</td></tr>' for a,b in renamed)}</tbody></table>
<h2>Ошибки</h2>
<table><tbody>{''.join(f'<tr><td>{esc(x)}</td></tr>' for x in errors)}</tbody></table>
</html>"""
    (out / "report.html").write_text(html_doc, encoding="utf-8")
    (out / "changes.tsv").write_text(
        "status\taction\tfile\tkey\told\tnew\treason\tconfidence\n"
        + "\n".join(
            f"{r['status']}\t{r.get('action','')}\t{r['file']}\t{r['key']}\t{r['old']}\t{r['new']}\t{r.get('reason','')}\t{r['confidence']}"
            for r in applied
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "insertions.tsv").write_text(
        "key\tfile\tsource\tanchor_before\tinsert\tanchor_after\tnew\tconfidence\n"
        + "\n".join(
            f"{r['key']}\t{r['file']}\t{r.get('insert_source','')}\t{r.get('anchor_before','')}\t{r.get('insert','')}\t{r.get('anchor_after','')}\t{r['new']}\t{r['confidence']}"
            for r in inserts
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "disputed.tsv").write_text(
        "file\tkey\tpali\tru\told\tnew\taction\treason\tconfidence\tanchor_before\tinsert\tanchor_after\n"
        + "\n".join(
            f"{r['file']}\t{r['key']}\t{r.get('pali','')}\t{r.get('ru','')}\t{r.get('old','')}\t{r.get('new','')}\t{r.get('action','')}\t{r['disputed_reason']}\t{r['confidence']}\t{r.get('anchor_before','')}\t{r.get('insert','')}\t{r.get('anchor_after','')}"
            for r in disputed
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "run.json").write_text(
        json.dumps(
            {
                "model": args.model,
                "edits": len(rows),
                "replace": len(replaces),
                "insert": len(inserts),
                "disputed": len(disputed),
                "renamed": renamed,
                "errors": errors,
                "config": str(args.config),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    diff = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--stat"], capture_output=True, text=True)
    print(diff.stdout)
    if applied:
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                "user.name=dhamma-gift-bot",
                "-c",
                "user.email=bot@dhamma.gift",
                "commit",
                "-m",
                f"rename: āvuso → товарищ (MN, replace {len(replaces)}, insert {len(inserts)}, renamed {len(renamed)})",
            ],
            check=True,
        )
    if args.push and applied:
        remote = subprocess.check_output(
            ["git", "-C", str(repo), "remote", "get-url", "origin"], text=True
        ).strip()
        if remote.startswith(("git@", "ssh://")):
            # SSH deploy key (no PAT)
            subprocess.run(
                ["git", "-C", str(repo), "push", "--force", "origin", f"HEAD:{args.branch}"],
                check=True,
            )
        else:
            token = os.environ.get("GITHUB_TOKEN", "")
            if not token:
                secrets = Path("/root/.secrets/tools.env")
                if secrets.exists():
                    text = secrets.read_text(encoding="utf-8")
                    m = re.search(r"^GITHUB_TOKEN=['\"]?([^'\"\n]+)", text, re.M)
                    token = m.group(1) if m else ""
            if not token:
                raise SystemExit("GITHUB_TOKEN not found (set env or /root/.secrets/tools.env)")
            auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "-c",
                    f"http.extraHeader=Authorization: Basic {auth}",
                    "push",
                    "--force",
                    "origin",
                    f"HEAD:{args.branch}",
                ],
                check=True,
            )
    print(f"report: {out/'report.html'}")
    if args.push and applied:
        print(f"compare: {REPO_URL}/compare/main...{args.branch}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
