# -*- coding: utf-8 -*-
"""Приём версии миров во всех моделях реестра и одна сводная таблица.

  python -B tools/rollout.py --version 1.8 [--models svcb,t] [--mode dry-run|branch] [--jobs 1] [--out DIR]
  python -B tools/rollout.py --version 1.8 --collect          только собрать отчёты, уже лежащие в моделях

Реестр — `models.yaml`: путь рабочей копии модели от корня папки семейства (`FAMILY_ROOT`, по умолчанию —
каталог над источником), её venv, переменные окружения (число процессов). Для каждой модели
запускается её команда `ops/tools/adopt_worlds.py --version V --source <этот каталог> --report <файл>` (режим
`dry-run` — во временной копии дерева, в рабочую копию ничего не пишется; `branch` — ветка `worlds-<V>` в рабочей
копии модели, push ветки и CI, без выкладки). Команды идут по очереди (`--jobs`, по умолчанию 1: тяжёлые прогоны на
общей машине — по одному). Отчёт каждой модели — JSON по схеме `adopt-worlds-report-v1` (её пишет команда модели);
сводка — `rollout/<V>/SUMMARY.md` и `SUMMARY.json`: модель × сдвиг точки и медианы, печать, полоса 80 %, гейты, CI,
красные флаги. Числа — блок `numbers` отчёта команды: полный шаг таблиц книги (2 000 прогонов) до и после приёма.
Выкладка — не здесь: одно «да» владельца по сводке, затем модели по очереди по своим справочникам.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "models.yaml"
REPORT_SCHEMA = "adopt-worlds-report-v1"


def load_registry(only: set[str] | None, path: Path = REGISTRY) -> list[dict]:
    reg = yaml.safe_load(path.read_text(encoding="utf-8"))
    models = [m for m in reg["models"] if not only or m["id"] in only]
    unknown = (only or set()) - {m["id"] for m in models}
    if unknown:
        raise SystemExit(f"нет в реестре: {sorted(unknown)}")
    return models


def family_root() -> Path:
    return Path(os.environ.get("FAMILY_ROOT") or ROOT.parent).resolve()


def model_dir(m: dict) -> Path:
    return family_root() / m["path"]


def model_python(m: dict) -> str:
    venv = (model_dir(m) / m.get("venv", ".venv")).resolve()
    for cand in (venv / "Scripts" / "python.exe", venv / "bin" / "python"):
        if cand.exists():
            return str(cand)
    raise SystemExit(f"{m['id']}: нет интерпретатора в {venv}")


def run_model(m: dict, version: str, mode: str, out: Path) -> dict:
    report = out / f"{m['id']}.json"
    log = out / f"{m['id']}.log"
    cmd = [model_python(m), "-B", m.get("adopt", "ops/tools/adopt_worlds.py"), "--version", version,
           "--source", str(ROOT), "--report", str(report), f"--{mode}"]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", **{k: str(v) for k, v in (m.get("env") or {}).items()})
    t0 = dt.datetime.now()
    with open(log, "w", encoding="utf-8") as fh:
        p = subprocess.run(cmd, cwd=model_dir(m), stdout=fh, stderr=subprocess.STDOUT, env=env)
    rep = read_report(report)
    rep.setdefault("model", m["id"])
    rep["_exit"] = p.returncode
    rep["_seconds"] = round((dt.datetime.now() - t0).total_seconds())
    rep["_log"] = str(log)
    return rep


def read_report(path: Path) -> dict:
    if not path.exists():
        return {"status": "no-report", "red_flags": ["команда приёма не оставила отчёта"]}
    rep = json.loads(path.read_text(encoding="utf-8"))
    if rep.get("schema") != REPORT_SCHEMA:
        rep.setdefault("red_flags", []).append(f"схема отчёта {rep.get('schema')!r} ≠ {REPORT_SCHEMA}")
    return rep


def fmt(x, nd=2):
    if x is None:
        return "—"
    if isinstance(x, (int, float)):
        return f"{x:+.{nd}f}".replace(".", ",").replace("-", "−") if isinstance(x, float) else str(x)
    return str(x)


def prn(x):
    """Печать витрины: без «.0», с запятой."""
    return "—" if x is None else f"{x:g}".replace(".", ",")


def num(x, nd=2):
    return "—" if x is None else f"{x:.{nd}f}".replace(".", ",")


def band(n: dict):
    """Полоса 80 % таблиц: печать витрины (`printed_band`), иначе числа полосы (`band`)."""
    if n.get("printed_band"):
        return f"{prn(n['printed_band'][0])}–{prn(n['printed_band'][1])}"
    if n.get("band"):
        return f"{num(n['band'][0], 1)}–{num(n['band'][1], 1)}"
    return "—"


def summary_rows(reports: list[dict]) -> list[dict]:
    rows = []
    for r in reports:
        n = r.get("numbers") or {}
        b, a = n.get("before") or {}, n.get("after") or {}
        g = r.get("gates") or {}
        ci = (r.get("git") or {}).get("ci") or {}
        rows.append({
            "model": r.get("model"), "status": r.get("status"), "exit": r.get("_exit"),
            "point": [b.get("point"), a.get("point")], "median": [b.get("median"), a.get("median")],
            "print": [b.get("print"), a.get("print")], "band": [band(b), band(a)],
            "d_point": None if None in (b.get("point"), a.get("point")) else a["point"] - b["point"],
            "d_median": None if None in (b.get("median"), a.get("median")) else a["median"] - b["median"],
            "print_steps": n.get("print_steps"),
            "gates_new": g.get("new") or [], "gates_gone": g.get("gone") or [],
            "ci": ci.get("conclusion") or ci.get("status"), "ci_url": ci.get("url"),
            "flags": r.get("red_flags") or [], "seconds": r.get("_seconds"),
        })
    return rows


def render_md(version: str, mode: str, rows: list[dict]) -> str:
    L = [f"# Приём миров {version} — сводка ({mode}, {dt.datetime.now():%d.%m.%Y %H:%M})", "",
         "Числа — таблицы книги (2 000 прогонов) до и после приёма.", "",
         "| Модель | Итог | Точка было → стало | Δ | Медиана было → стало | Δ | Печать | Полоса 80 % | Гейты: новые / ушли | CI | Флаги |",
         "|---|---|---|---:|---|---:|---|---|---|---|---|"]
    for r in rows:
        L.append("| {m} | {s} | {p0} → {p1} | {dp} | {m0} → {m1} | {dm} | {pr0} → {pr1} | {b0} → {b1} | {gn} / {gg} | {ci} | {fl} |".format(
            m=r["model"], s=r["status"], p0=num(r["point"][0]), p1=num(r["point"][1]), dp=fmt(r["d_point"]),
            m0=num(r["median"][0]), m1=num(r["median"][1]), dm=fmt(r["d_median"]),
            pr0=prn(r["print"][0]), pr1=prn(r["print"][1]), b0=(r.get("band") or ["—", "—"])[0],
            b1=(r.get("band") or ["—", "—"])[1],
            gn=", ".join(r["gates_new"]) or "—", gg=", ".join(r["gates_gone"]) or "—", ci=r["ci"] or "—",
            fl=len(r["flags"]) or "—"))
    flagged = [r for r in rows if r["flags"]]
    if flagged:
        L += ["", "## Красные флаги", ""]
        for r in flagged:
            L.append(f"**{r['model']}**")
            L += [f"- {f}" for f in r["flags"]]
            L.append("")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", required=True)
    ap.add_argument("--models", help="через запятую; по умолчанию — весь реестр")
    ap.add_argument("--mode", default="dry-run", choices=("dry-run", "branch"))
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--out")
    ap.add_argument("--collect", action="store_true", help="не запускать, только собрать отчёты из каталога сводки")
    ap.add_argument("--registry", help="другой реестр (например, ветки перевода до слияния); по умолчанию models.yaml")
    a = ap.parse_args(argv)
    idx = json.loads((ROOT / "versions.json").read_text(encoding="utf-8"))
    if a.version not in idx["versions"]:
        print(f"ОТКАЗ: версии {a.version} нет в индексе")
        return 1
    if a.mode == "branch" and idx["versions"][a.version]["status"] != "canon":
        print(f"ОТКАЗ: версия {a.version} — {idx['versions'][a.version]['status']}: её принимают только сухим прогоном")
        return 1
    models = load_registry(set(a.models.split(",")) if a.models else None, Path(a.registry) if a.registry else REGISTRY)
    out = Path(a.out) if a.out else ROOT / "rollout" / a.version
    out.mkdir(parents=True, exist_ok=True)
    if a.collect:
        reports = []
        for m in models:                  # отчёт сводки, иначе — последний отчёт команды в дереве модели
            f = out / f"{m['id']}.json"
            if not f.exists():
                f = model_dir(m) / "var" / "adopt" / a.version / "report.json"
            reports.append(dict(read_report(f), model=m["id"], _source=str(f)))
    else:
        with cf.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
            futs = {ex.submit(run_model, m, a.version, a.mode, out): m["id"] for m in models}
            reports = []
            for f in cf.as_completed(futs):
                rep = f.result()
                print(f"{futs[f]}: {rep.get('status')} (код {rep.get('_exit')}, {rep.get('_seconds')} с)")
                reports.append(rep)
        order = {m["id"]: i for i, m in enumerate(models)}
        reports.sort(key=lambda r: order.get(r.get("model"), 99))
    rows = summary_rows(reports)
    (out / "SUMMARY.json").write_text(json.dumps({"version": a.version, "mode": a.mode, "rows": rows},
                                                 ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    md = render_md(a.version, a.mode, rows)
    (out / "SUMMARY.md").write_text(md, encoding="utf-8", newline="\n")
    print(md)
    return 0 if all(r["status"] == "ok" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
