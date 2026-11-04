# -*- coding: utf-8 -*-
"""Окно рыночного снимка мира M книги 1.7: из снимков data/ — дни окна, средние узлы и доходности, таблица по дням.

Правило (WORLDS-RECIPE.md, раздел 2.1): окно — до 10 торговых дней по дату снимка, но не раньше дня последнего
решения Банка России по ключевой ставке; если таких дней меньше трёх, снимок ждёт третьего торгового дня после
решения. Усредняются обе стороны по одним дням: узлы бескупонной кривой zcyc (на конец дня) и реальные доходности
ОФЗ-ИН 52002–52005 (`YIELDCLOSE` истории TQOB); округление 0,0001.

Запуск (из корня репозитория, сеть не нужна):
  python -B data/assumptions/evidence/book-1.7/worlds/window.py              # таблица, сверка со входами записи
  python -B data/assumptions/evidence/book-1.7/worlds/window.py --compare ДИР   # + сверка со снимками ведущего
Пишет рядом window_block.json (блоки окна для worlds_inputs.yaml и справочные варианты) и window_out.txt.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
BOOK = HERE.parents[2]
OFZ_IN = {"SU52002RMFS1": "52002", "SU52003RMFS9": "52003", "SU52004RMFS7": "52004", "SU52005RMFS4": "52005"}
NODE_KEYS = ("0.25", "0.5", "0.75", "1", "2", "3", "5", "7", "10", "15", "20")   # ключи узлов — как в записи
SNAPSHOT, LAST_DECISION, MAX_DAYS, MIN_DAYS = "2026-10-28", "2026-10-23", 10, 3
RULE = ("до 10 торговых дней по дату снимка, но не раньше дня последнего решения Банка России по ключевой ставке; "
        "если таких дней меньше трёх, снимок ждёт третьего торгового дня после решения")
METHOD = ("среднее по дням окна обеих сторон: узлы бескупонной кривой MOEX zcyc на конец дня и реальные доходности "
          "ОФЗ-ИН 52002–52005 (YIELDCLOSE истории TQOB), округление 0,0001; дата снимка — последний день окна")
# Таблица отчёта ведущего (WORLDS-850-CBR-2026-10-23.md): раздел 2.4 — узлы, % годовых; раздел 4, п. 7 — π_ss,
# уровень терминала M, установившаяся ключевая M; ОФЗ-ИН 26.10 — раздел 1.2.
REPORT = {
    "2026-10-23": {"nodes": {"0.5": 13.74, "1": 14.21, "2": 14.97, "3": 15.51, "5": 16.13, "10": 16.64, "20": 16.83},
                   "pi_ss": 10.42, "curve_lt_M": 17.0, "key_M_steady": 17.6},
    "2026-10-26": {"nodes": {"0.5": 13.38, "1": 14.05, "2": 14.99, "3": 15.56, "5": 16.13, "10": 16.51, "20": 16.64},
                   "pi_ss": 10.17, "curve_lt_M": 16.8, "key_M_steady": 17.3,
                   "ofz_in": {"52002": 8.98, "52003": 6.80, "52004": 6.46, "52005": 6.13}},
}


def _recipe():
    spec = importlib.util.spec_from_file_location("worlds_recipe", BOOK / "worlds_recipe.py")
    mod = importlib.util.module_from_spec(spec)
    was, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = was
    return mod


def _key(period) -> str:
    s = f"{float(period):g}"
    assert s in NODE_KEYS, s
    return s


def zcyc_nodes(path: Path) -> tuple[dict, str, str]:
    yy = json.loads(path.read_text(encoding="utf-8"))["yearyields"]
    c = yy["columns"]
    days = {r[c.index("tradedate")] for r in yy["data"]}
    times = {r[c.index("tradetime")] for r in yy["data"]}
    assert len(days) == 1 and len(times) == 1, (path, days, times)
    return ({_key(r[c.index("period")]): float(r[c.index("value")]) for r in yy["data"]}, days.pop(), times.pop())


def ofz_in_history() -> dict:
    """{день: {выпуск: YIELDCLOSE}} по истории TQOB."""
    out = {}
    for secid, short in OFZ_IN.items():
        h = json.loads((DATA / f"ofzin_history_{secid}.json").read_text(encoding="utf-8"))["history"]
        c = {k: i for i, k in enumerate(h["columns"])}
        for r in h["data"]:
            if r[c["YIELDCLOSE"]] is not None:
                out.setdefault(r[c["TRADEDATE"]], {})[short] = float(r[c["YIELDCLOSE"]])
    return out


def select_window(trading: list[str], snapshot: str, decision: str | None, max_days: int, min_days: int) -> list[str]:
    days = [d for d in trading if d <= snapshot and (decision is None or d >= decision)][-max_days:]
    if decision is not None and len(days) < min_days:
        raise SystemExit(f"окно {days}: меньше {min_days} торговых дней после решения {decision} — снимок ждёт "
                         "третьего торгового дня после решения")
    return days


def mean(per_day: dict) -> dict:
    """Среднее по дням для каждого ключа, округление 0,0001 (то же, что `worlds_recipe.window_mean`)."""
    keys = list(next(iter(per_day.values())))
    return {k: round(sum(per_day[d][k] for d in per_day) / len(per_day), 4) for k in keys}


def block(days: list[str], curves: dict, linkers: dict, decision: str | None) -> dict:
    nd = {d: {k: curves[d][k] for k in NODE_KEYS} for d in days}
    yd = {d: {s: linkers[d][s] for s in OFZ_IN.values()} for d in days}
    out = {"days": days, "nodes": mean(nd), "yields": mean(yd)}
    out["curve_window"] = {"rule": RULE, "last_decision": decision, "max_days": MAX_DAYS, "min_days": MIN_DAYS,
                           "method": METHOD, "days": nd}
    out["ofz_in_window"] = {"days": yd}
    return out


def inputs_for(record: dict, b: dict, snapshot: str, with_window: bool) -> dict:
    """Входы записи с рыночным снимком варианта `b` (кривая и ОФЗ-ИН — средние окна, дата — последний день)."""
    x = copy.deepcopy(record)
    x["curve"] = {"source": record["curve"]["source"], "date": snapshot, "nodes": dict(b["nodes"])}
    x["ofz_in"]["date"], x["ofz_in"]["settlement_date"] = snapshot, _recipe().next_weekday(snapshot)
    x["ofz_in"]["bonds"] = [dict(bd, real_yield=b["yields"][str(bd["secid"])]) for bd in record["ofz_in"]["bonds"]]
    x["ofz_in"].pop("window", None)
    if with_window:
        x["curve"]["window"] = b["curve_window"]
        x["ofz_in"]["window"] = b["ofz_in_window"]
    if "current_half_actual" in x:
        x["current_half_actual"]["to"] = record["current_half_actual"]["to"]
    return x


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", help="каталог снимков ведущего (zcyc_<день>.json, ofzin_hist.json) для сверки")
    args = ap.parse_args(argv)
    lines = []

    def say(s=""):
        print(s)
        lines.append(s)

    linkers = ofz_in_history()
    curves, stamp = {}, {}
    for p in sorted(DATA.glob("zcyc_*.json")):
        nodes, day, tm = zcyc_nodes(p)
        assert p.stem == f"zcyc_{day}", p
        curves[day], stamp[day] = nodes, tm
    trading = sorted(set(curves) & set(linkers))
    say(f"Торговые дни в данных (кривая и все четыре ОФЗ-ИН): {', '.join(trading)}")
    win = select_window(trading, SNAPSHOT, LAST_DECISION, MAX_DAYS, MIN_DAYS)
    say(f"Правило окна: {RULE}.")
    say(f"Решение Банка России — {LAST_DECISION}, снимок — {SNAPSHOT}: окно {', '.join(win)} ({len(win)} дн.)")
    variants = {"record": block(win, curves, linkers, LAST_DECISION),
                "one_day": block([SNAPSHOT], curves, linkers, None),
                "ten_days": block(select_window(trading, SNAPSHOT, None, 10, 1), curves, linkers, None)}
    say("")
    say("| день | время кривой | 0,5 | 1 | 2 | 3 | 5 | 10 | 20 | 52002 | 52003 | 52004 | 52005 |")
    say("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for d in variants["ten_days"]["days"]:
        c, y = curves[d], linkers[d]
        mark = " **" if d in win else ""
        say(f"| {d}{mark} | {stamp[d]} | " + " | ".join(f"{c[k]:.4f}" for k in ("0.5", "1", "2", "3", "5", "10", "20"))
            + " | " + " | ".join(f"{y[s]:.2f}" for s in OFZ_IN.values()) + " |")
    for name, title in (("record", "окно записи 23–28.10"), ("ten_days", "10 дней 15–28.10"), ("one_day", "один день 28.10")):
        b = variants[name]
        say(f"| **среднее: {title}** | | " + " | ".join(f"{b['nodes'][k]:.4f}" for k in ("0.5", "1", "2", "3", "5", "10", "20"))
            + " | " + " | ".join(f"{b['yields'][s]:.4f}" for s in OFZ_IN.values()) + " |")
    say("")
    say("Сверка с таблицами отчёта ведущего (узлы — раздел 2.4, ОФЗ-ИН 26.10 — раздел 1.2), до округления отчёта:")
    for d, ref in REPORT.items():
        dn = {k: round(curves[d][k] - v, 3) for k, v in ref["nodes"].items() if abs(curves[d][k] - v) > 0.005}
        dy = {s: round(linkers[d][s] - v, 3) for s, v in (ref.get("ofz_in") or {}).items() if abs(linkers[d][s] - v) > 0.005}
        say(f"- {d}: узлы {'совпадают' if not dn else 'расходятся ' + str(dn)}"
            + (f"; ОФЗ-ИН {'совпадают' if not dy else 'расходятся ' + str(dy)}" if ref.get("ofz_in") else ""))
    if args.compare:
        cmp_dir = Path(args.compare)
        say("")
        say(f"Сверка со снимками ведущего ({cmp_dir}):")
        hist = json.loads((cmp_dir / "ofzin_hist.json").read_text(encoding="utf-8"))
        for d in variants["ten_days"]["days"]:
            p = cmp_dir / f"zcyc_{d}.json"
            if not p.exists():
                say(f"- {d}: снимка у ведущего нет")
                continue
            n2, _, t2 = zcyc_nodes(p)
            dn = {k: round(curves[d][k] - n2[k], 4) for k in NODE_KEYS if curves[d][k] != n2[k]}
            y2 = {OFZ_IN[s]: float(r["YIELDCLOSE"]) for s, rows in hist.items() for r in rows if r["TRADEDATE"] == d}
            dy = {s: round(linkers[d][s] - y2[s], 4) for s in y2 if linkers[d][s] != y2[s]}
            say(f"- {d}: кривая ведущего {t2}, наша {stamp[d]} — узлы {'бит в бит' if not dn else 'разница ' + str(dn)}; "
                f"ОФЗ-ИН {'бит в бит' if not dy and y2 else ('нет у ведущего' if not y2 else 'разница ' + str(dy))}")

    rec_inp = yaml.safe_load((BOOK / "worlds_inputs.yaml").read_text(encoding="utf-8"))
    rec = variants["record"]
    if (rec_inp.get("curve") or {}).get("window"):
        W = rec_inp["curve"]["window"]
        same = (W["days"] == rec["curve_window"]["days"] and rec_inp["ofz_in"]["window"]["days"] == rec["ofz_in_window"]["days"]
                and {str(k): float(v) for k, v in rec_inp["curve"]["nodes"].items()} == rec["nodes"]
                and {str(b["secid"]): float(b["real_yield"]) for b in rec_inp["ofz_in"]["bonds"]} == rec["yields"])
        say("")
        say(f"Входы записи (worlds_inputs.yaml, книга {rec_inp['version']}): окно, средние узлы и доходности — "
            + ("**совпадают с данными бит в бит**" if same else "**НЕ совпадают с данными**"))
        if not same:
            return 1
        R = _recipe()
        assert not R.check_window(rec_inp), R.check_window(rec_inp)
        mw = R.market_window(rec_inp)
        say("")
        say("Шум снимка по дням окна (рецепт `market_window`, те же входы записи; ключевая M — правило яруса 2):")
        say("")
        flds = list(mw["window"])
        say("| день | " + " | ".join(flds) + " |")
        say("|---|" + "---:|" * len(flds))
        for d, v in mw["by_day"].items():
            say(f"| {d} | " + " | ".join(f"{v[f]:g}" for f in flds) + " |")
        say("| разброс (мин–макс) | " + " | ".join(f"{mw['range'][f][0]:g}–{mw['range'][f][1]:g}" for f in flds) + " |")
        say("| среднее по дням | " + " | ".join(f"{mw['mean_of_days'][f]:g}" for f in flds) + " |")
        say("| **окно (запись)** | " + " | ".join(f"**{mw['window'][f]:g}**" for f in flds) + " |")
        say("")
        say("Сверка с отчётом ведущего (раздел 4, п. 7): " + "; ".join(
            f"{d}: π_ss {mw['by_day'][d]['pi_ss']:.2f} (отчёт {r['pi_ss']}), терминал M {mw['by_day'][d]['curve_lt_M']} "
            f"(отчёт {r['curve_lt_M']}), установившаяся ключевая M {mw['by_day'][d]['key_M_steady']} (отчёт {r['key_M_steady']})"
            for d, r in REPORT.items() if d in mw["by_day"]))
        for name in ("one_day", "ten_days"):
            x = inputs_for(rec_inp, variants[name], SNAPSHOT, with_window=False)
            st = R.snapshot_stats(x, R.Curve(x["curve"]["nodes"], x["curve"]["date"]))
            say(f"Справочный вариант «{name}» ({', '.join(variants[name]['days'])}): "
                + ", ".join(f"{f} {st[f]:g}" for f in flds))
    (HERE / "window_block.json").write_text(json.dumps(variants, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "window_out.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
