# -*- coding: utf-8 -*-
"""Факт текущего полугодия для правил яруса 2 книги 1.7 (WORLDS-RECIPE.md, раздел 3): из снимков data/ — числа,
которые вписаны во входы записи (`cpi_actual`, `cpi_actual.food_spread`, `wage_actual`), и сверка с ними.

  * ИПЦ г/г по месяцам — ряд ЦБ «Инфляция и ключевая ставка» (data/cbr_infl_2025-01_2026-10.html);
  * продовольственные товары и все товары и услуги, г/г — одна таблица ЦБ «Динамика потребительских цен», сентябрь
    2026 (data/cbr_cpd_2026-09.html): спред = среднее продовольственных − среднее всех за опубликованные месяцы;
  * номинальная начисленная зарплата — Росстат, tab1-zpl_08-2026.xlsx (уровни, ₽): г/г = месяц 2026 / месяц 2025 − 1.
Запуск из корня репозитория (сеть не нужна): python -B data/assumptions/evidence/book-1.7/worlds/facts.py
"""
from __future__ import annotations

import html
import re
import sys
import zipfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
BOOK = HERE.parents[2]
MONTHS = {"Январь": 1, "Февраль": 2, "Март": 3, "Апрель": 4, "Май": 5, "Июнь": 6, "Июль": 7, "Август": 8,
          "Сентябрь": 9, "Октябрь": 10, "Ноябрь": 11, "Декабрь": 12}


def _rows(text: str) -> list[list[str]]:
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
        if any(cells):
            out.append(cells)
    return out


def _num(x: str) -> float:
    return float(x.replace("\xa0", "").replace(" ", "").replace(",", "."))


def cbr_infl() -> dict:
    t = (DATA / "cbr_infl_2025-01_2026-10.html").read_text(encoding="utf-8", errors="ignore")
    out = {}
    for r in _rows(t):
        if re.fullmatch(r"\d\d\.2026", r[0] or ""):
            m, y = r[0].split(".")
            out[f"{y}-{m}"] = _num(r[2])
    return dict(sorted(out.items()))


def cbr_cpd() -> dict:
    t = (DATA / "cbr_cpd_2026-09.html").read_text(encoding="utf-8", errors="ignore")
    rows = [[c.replace(" ", " ") for c in r] for r in _rows(t)]
    at = next(i for i, r in enumerate(rows) if r[0].startswith("Инфляция, г/г"))
    head = [h for h in rows[at] if h]                # пустые ячейки заголовка — разделители групп столбцов
    cols = {}
    for i, h in enumerate(head):
        m = re.fullmatch(r"([А-Яа-я]+)\s*2026", h)
        if m and m.group(1) in MONTHS:
            cols[i] = f"2026-{MONTHS[m.group(1)]:02d}"

    def pick(name: str) -> dict:                     # первая строка с этим именем после заголовка — та же таблица
        r = next(r for r in rows[at + 1:] if r[0] == name and len(r) == len(head))
        return {cols[i]: _num(r[i]) for i in cols}

    return {"all_yoy": pick("Все товары и услуги"), "food_yoy": pick("Продовольственные товары")}


def rosstat_wages() -> dict:
    z = zipfile.ZipFile(DATA / "rosstat_tab1-zpl_08-2026.xlsx")
    ss = [html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))
          for si in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8"), re.S)]
    sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    grid = {}
    for c in re.finditer(r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', sheet, re.S):
        col, row, attrs, inner = c.groups()
        v = re.search(r"<v>(.*?)</v>", inner or "")
        if v:
            grid[(col, int(row))] = ss[int(v.group(1))] if 't="s"' in attrs else v.group(1)
    head = {col: MONTHS[val] for (col, row), val in grid.items() if row == 5 and val in MONTHS}
    year_row = {re.match(r"\d{4}", val).group(0): row for (col, row), val in grid.items()
                if col == "A" and re.match(r"\d{4}", str(val))}
    lvl = {}
    for y in ("2025", "2026"):
        for col, m in head.items():
            x = grid.get((col, year_row[y]))
            if x not in (None, "…"):
                lvl[f"{y}-{m:02d}"] = float(str(x).replace(" ", "").split("(")[0])
    yoy = {f"2026-{m:02d}": round((lvl[f"2026-{m:02d}"] / lvl[f"2025-{m:02d}"] - 1) * 100, 2)
           for m in range(7, 13) if f"2026-{m:02d}" in lvl}
    return {"levels": {k: v for k, v in sorted(lvl.items()) if k[5:] in ("07", "08", "09", "10", "11", "12")}, "yoy": yoy}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    infl, cpd, wages = cbr_infl(), cbr_cpd(), rosstat_wages()
    h2 = [f"2026-{m:02d}" for m in range(7, 13)]
    known = [k for k in h2 if k in cpd["food_yoy"] and k in cpd["all_yoy"]]
    spread = (sum(cpd["food_yoy"][k] for k in known) - sum(cpd["all_yoy"][k] for k in known)) / len(known)
    print("ИПЦ г/г, ряд ЦБ:", {k: v for k, v in infl.items() if k in h2})
    print("Таблица ЦБ «Динамика потребительских цен», сентябрь 2026: все", {k: cpd["all_yoy"][k] for k in known},
          "продовольственные", {k: cpd["food_yoy"][k] for k in known}, f"→ спред {spread:+.4f} п.п.")
    print("Росстат, зарплата, ₽:", wages["levels"], "→ г/г", wages["yoy"])
    inp = yaml.safe_load((BOOK / "worlds_inputs.yaml").read_text(encoding="utf-8"))
    ca, fs, wa = inp.get("cpi_actual") or {}, (inp.get("cpi_actual") or {}).get("food_spread") or {}, inp.get("wage_actual") or {}
    ok = ({str(k): float(v) for k, v in (ca.get("yoy") or {}).items()} == {k: v for k, v in infl.items() if k in h2}
          and {str(k): float(v) for k, v in (fs.get("food_yoy") or {}).items()} == {k: cpd["food_yoy"][k] for k in known}
          and {str(k): float(v) for k, v in (fs.get("all_yoy") or {}).items()} == {k: cpd["all_yoy"][k] for k in known}
          and {str(k): float(v) for k, v in (wa.get("yoy") or {}).items()} == wages["yoy"])
    print(f"входы записи (книга {inp['version']}): cpi_actual, food_spread, wage_actual —",
          "совпадают с данными" if ok else "НЕ совпадают с данными")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
