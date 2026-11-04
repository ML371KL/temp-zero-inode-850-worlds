# -*- coding: utf-8 -*-
"""Пробная версия миров: та же версия-основа, другое окно рыночного снимка мира M.

  python -B tools/trial.py window --base 1.7 --version 1.7-t1 --snapshot 2026-10-27 [--title "…"]

Проба проверяет схему, а не меняет суждение: входы основы остаются, меняется только окно (дни после даты снимка
выпадают, узлы кривой и доходности ОФЗ-ИН — среднее оставшихся дней, `math.fsum`, 0,0001; дата снимка, дата ОФЗ-ИН и
расчётов — по новому последнему дню). Запись — текущим рецептом; надстройка банков — сборщиком черновика основы
(`bank/bank_overlay_build_*.py`) на новой записи, затем `bank/build_overlay.py`; лист сектора — пути надстройки и
происхождение новой записи. Статус версии — `trial`: модели принимают её только сухим прогоном.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import worlds as W  # noqa: E402

DAY_LINE = re.compile(r'^(\s+)"(\d{4}-\d{2}-\d{2})": \{.*\}\s*$')


def next_weekday(day: str) -> str:
    d = dt.date.fromisoformat(day) + dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d.isoformat()


def mean4(per_day: dict) -> dict:
    keys = list(next(iter(per_day.values())))
    return {k: round(math.fsum(float(per_day[d][k]) for d in per_day) / len(per_day), 4) for k in keys}


def window_inputs(text: str, snapshot: str) -> str:
    """Входы основы → входы пробы: дни окна после снимка выпадают, средние и даты — по оставшимся дням."""
    inp = yaml.safe_load(text)
    cw, ow = inp["curve"]["window"]["days"], inp["ofz_in"]["window"]["days"]
    keep = sorted(d for d in cw if d <= snapshot)
    if not keep or keep[-1] != snapshot:
        raise SystemExit(f"дня снимка {snapshot} нет среди дней окна {sorted(cw)}")
    lines = text.split("\n")
    out = [ln for ln in lines if not ((m := DAY_LINE.match(ln)) and m.group(2) > snapshot)]
    nodes = mean4({d: cw[d] for d in keep})
    yields = mean4({d: ow[d] for d in keep})
    text = "\n".join(out)
    root = yaml.compose(text)
    edits = []

    def at(path):
        node = root
        for part in path:
            node = node.value[int(part)] if isinstance(node, yaml.SequenceNode) else \
                next(v for k, v in node.value if str(k.value) == str(part))
        return node

    def put(path, s):
        n = at(path)
        edits.append((n.start_mark.index, n.end_mark.index, s))

    put(("asof",), json.dumps(snapshot))
    put(("curve", "date"), json.dumps(snapshot))
    put(("curve", "nodes"), "{" + ", ".join(f'"{k}": {v}' for k, v in nodes.items()) + "}")
    put(("ofz_in", "date"), json.dumps(snapshot))
    put(("ofz_in", "settlement_date"), json.dumps(next_weekday(snapshot)))
    for i, b in enumerate(inp["ofz_in"]["bonds"]):
        put(("ofz_in", "bonds", i, "real_yield"), str(yields[str(b["secid"])]))
    for a, b, s in sorted(edits, reverse=True):
        text = text[:a] + s + text[b:]
    first, last = dt.date.fromisoformat(keep[0]), dt.date.fromisoformat(keep[-1])
    old_last = dt.date.fromisoformat(sorted(cw)[-1])
    span_old = f"{first:%d}–{old_last:%d.%m.%Y}"
    text = text.replace(span_old, f"{first:%d}–{last:%d.%m.%Y}")
    text = text.replace(span_old.replace("–", "-"), f"{first:%d}-{last:%d.%m.%Y}")      # заметки записи (латиница)
    chk = yaml.safe_load(text)
    assert sorted(chk["curve"]["window"]["days"]) == keep and sorted(chk["ofz_in"]["window"]["days"]) == keep
    return text


def sector_sheet(base_sheet: Path, overlay: dict, record_path: Path) -> str:
    """Лист сектора пробы: пути надстройки новой записи, происхождение новой записи, дата и рецепт надстройки."""
    text = base_sheet.read_text(encoding="utf-8")
    head = "\n".join(ln for ln in text.split("\n") if ln.startswith("#")).split("\nmeta:")[0]
    doc = yaml.safe_load(text)
    rec = json.loads(record_path.read_bytes().decode("utf-8"))
    doc["meta"]["status"] = "лист сектора пробной версии миров (только сухой прогон моделей)"
    doc["meta"]["worlds_record"].update(sha256=W.sha256(record_path), asof=rec["asof"])
    doc["meta"]["sector_overlay"]["sha256"] = None
    doc["meta"]["overlay"] = {"as_of": overlay["source"]["as_of"], "recipe": overlay["recipe"]}
    for w, blk in overlay["worlds"].items():
        sw = doc["sector"]["worlds"][w]
        for grp in ("credit_growth", "funds_growth"):
            for k, path in blk[grp].items():
                sw[grp][k] = {int(y) if str(y).isdigit() and not isinstance(next(iter(sw[grp][k])), str) else y: v
                              for y, v in path.items()}
        sw["nominal_gdp_growth"] = {int(y) if not isinstance(next(iter(sw["nominal_gdp_growth"])), str) else y: v
                                    for y, v in blk["nominal_gdp_growth"].items()}
    body = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=120)
    return head.rstrip("\n") + "\n" + body


def make_window_trial(base: str, v: str, snapshot: str, title: str | None) -> int:
    src, dst = W.VERSIONS / base, W.VERSIONS / v
    if dst.exists():
        print(f"ОТКАЗ: каталог {dst.relative_to(ROOT)} уже есть")
        return 1
    meta = W.passport(src)
    (dst / "inputs").mkdir(parents=True)
    (dst / "bank").mkdir()
    (dst / "doc").mkdir()
    shutil.copyfile(src / "doc" / "WORLDS-RECIPE.md", dst / "doc" / "WORLDS-RECIPE.md")
    text = window_inputs((src / "inputs" / "worlds_inputs.yaml").read_text(encoding="utf-8"), snapshot)
    (dst / "inputs" / "worlds_inputs.yaml").write_text(text, encoding="utf-8", newline="\n")
    meta.update(version=v, status="trial", built=dt.date.today().isoformat(),
                title=title or f"проба: версия {base} со снимком мира M на {dt.date.fromisoformat(snapshot):%d.%m.%Y}")
    meta.setdefault("labels", {})["walk_step"] = f"миры ставок (проба: снимок {dt.date.fromisoformat(snapshot):%d.%m.%Y})"
    (dst / "VERSION.yaml").write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=120),
                                      encoding="utf-8", newline="\n")
    (dst / "NOTES.md").write_text(
        f"# Проба {v}\n\nВерсия {base}, окно рыночного снимка мира M — по {dt.date.fromisoformat(snapshot):%d.%m.%Y} "
        "(дни после снимка выпали; узлы кривой и доходности ОФЗ-ИН — среднее оставшихся дней). Остальные входы — "
        f"{base}. Статус `trial`: только сухой прогон моделей (`tools/rollout.py --mode dry-run`).\n",
        encoding="utf-8", newline="\n")
    # запись — текущим рецептом
    recipe = W.load_module(W.RECIPE_HEAD, "trial_recipe")
    inp = yaml.safe_load(text)
    bad = recipe.check_window(inp)
    if bad:
        raise SystemExit("окно пробы не проходит правило: " + "; ".join(bad))
    W.write_record(recipe.build_worlds(inp), dst / "record")
    (dst / "recipe").mkdir()
    shutil.copyfile(W.RECIPE_HEAD, dst / "recipe" / "worlds_recipe.py")
    rec = dst / "record" / "worlds_source.json"
    print(f"запись {v}: sha256 {W.sha256(rec)[:12]}…, asof {snapshot}")
    # надстройка: черновик сборщиком основы на новой записи → worlds_bank.json → лист сектора
    builders = sorted((src / "bank").glob("bank_overlay_build_*.py"))
    if builders:
        env = dict(os.environ, WORLDS_RECORD="worlds_source.json", OVERLAY_OUT=str(dst / "bank"), PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, "-B", str(builders[-1])], env=env, capture_output=True, text=True,
                           encoding="utf-8", cwd=str(dst / "record"))      # путь записи в черновике — относительный
        if p.returncode != 0:
            raise SystemExit("сборщик черновика надстройки:\n" + p.stdout[-800:] + p.stderr[-800:])
        draft = dst / "bank" / "bank_overlay_draft.yaml"
        ov_text = W.overlay_text(draft, rec)
        (dst / "bank" / "worlds_bank.json").write_text(ov_text, encoding="utf-8", newline="\n")
        ov = json.loads(ov_text)
        print(f"надстройка {v}: sha256 {W.sha256(dst / 'bank' / 'worlds_bank.json')[:12]}…")
        if (src / "bank" / "sector_sheet.yaml").exists():
            sheet = sector_sheet(src / "bank" / "sector_sheet.yaml", ov, rec)
            (dst / "bank" / "sector_sheet.yaml").write_text(sheet, encoding="utf-8", newline="\n")
            same = W.overlay_text(dst / "bank" / "sector_sheet.yaml", rec, W.SECTOR_BUILDER) == ov_text
            print("лист сектора даёт ту же надстройку:", "да" if same else "НЕТ")
            if not same:
                return 1
    code, last = W.run_recipe(dst / "recipe" / "worlds_recipe.py", dst / "inputs" / "worlds_inputs.yaml", rec)
    print("проверка рецептом:", last)
    return code


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("window")
    p.add_argument("--base", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--title")
    a = ap.parse_args(argv)
    if a.cmd == "window":
        return make_window_trial(a.base, a.version, a.snapshot, a.title)
    return 2


if __name__ == "__main__":
    sys.exit(main())
