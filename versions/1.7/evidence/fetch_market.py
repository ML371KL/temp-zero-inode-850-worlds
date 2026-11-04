# -*- coding: utf-8 -*-
"""Скачивание рыночных входов листа «Миры 1.7»: окно мира M после решения Банка России 23.10.2026.

Запускается ТОЛЬКО для обновления данных: `python -B fetch_market.py` (сеть — MOEX ISS и cbr.ru).
Основной расчёт (`window.py`) сети не требует. Запросы последовательные, пауза >= 1,2 с.

Что качается в data/:
  zcyc_<ДАТА>.json                 бескупонная кривая MOEX на конец дня (params + yearyields) на каждую торговую дату
                                   с 15.10 по 28.10.2026 (окно записи 23–28.10 и справочное окно 10 дней 15–28.10)
  ofzin_history_<SECID>.json       история торгов ОФЗ-ИН 52002–52005 (TQOB) за 01–28.10.2026: YIELDCLOSE и др.
  cbr_keyrate_2026-06-01_2026-10-28.html   ряд ЦБ «Ключевая ставка» (для current_half_actual)
  cbr_infl_2025-01_2026-10.html            ряд ЦБ «Инфляция и ключевая ставка» (ИПЦ г/г по месяцам, правило 5.2 п. 4)
  cbr_cpd_2026-09.html                     таблица ЦБ «Динамика потребительских цен», сентябрь 2026 (ИПЦ и продовольствие г/г
                                           одной таблицы — спред продовольствия текущего полугодия; второй заход 29.10)
  rosstat_tab1-zpl_08-2026.xlsx            Росстат: среднемесячная номинальная начисленная зарплата по месяцам 1991–2026
                                           (зарплаты текущего полугодия; второй заход 29.10)
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
ISS = "https://iss.moex.com/iss"
UA = {"User-Agent": "Mozilla/5.0 (magnit-850oa evidence script; polite, sequential)"}
PAUSE = 1.2
OFZ_IN = ("SU52002RMFS1", "SU52003RMFS9", "SU52004RMFS7", "SU52005RMFS4")
HIST_FROM, HIST_TILL = "2026-10-01", "2026-10-28"
CURVE_FROM = "2026-10-15"
CBR = {
    "cbr_keyrate_2026-06-01_2026-10-28.html":
        "https://www.cbr.ru/hd_base/KeyRate/?UniDbQuery.Posted=True&UniDbQuery.From=01.06.2026&UniDbQuery.To=28.10.2026",
    "cbr_infl_2025-01_2026-10.html":
        "https://www.cbr.ru/hd_base/infl/?UniDbQuery.Posted=True&UniDbQuery.From=01.01.2025&UniDbQuery.To=31.10.2026",
    "rosstat_tab1-zpl_08-2026.xlsx": "https://rosstat.gov.ru/storage/mediabank/tab1-zpl_08-2026.xlsx",
}
# cbr.ru отдаёт эту страницу только запросу urllib с его заголовком User-Agent по умолчанию
PLAIN = {"cbr_cpd_2026-09.html": "https://cbr.ru/analytics/dkp/dinamic/CPD_2026-9/"}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    time.sleep(PAUSE)
    return data


def _save(name: str, payload: bytes) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / name).write_bytes(payload)
    print(f"  {name}: {len(payload)} байт")


def trading_days() -> list[str]:
    """Торговые даты окна — даты истории ОФЗ-ИН (все четыре выпуска торгуются каждый день TQOB)."""
    days = set()
    for s in OFZ_IN:
        h = json.loads((DATA / f"ofzin_history_{s}.json").read_text(encoding="utf-8"))["history"]
        i = h["columns"].index("TRADEDATE")
        days |= {r[i] for r in h["data"]}
    return sorted(days)


def fetch() -> None:
    print("MOEX ISS: история ОФЗ-ИН", HIST_FROM, "…", HIST_TILL)
    for s in OFZ_IN:
        _save(f"ofzin_history_{s}.json",
              _get(f"{ISS}/history/engines/stock/markets/bonds/boards/TQOB/securities/{s}.json"
                   f"?from={HIST_FROM}&till={HIST_TILL}"))
    days = [d for d in trading_days() if d >= CURVE_FROM]
    print("MOEX ISS: кривая zcyc на", len(days), "дат:", ", ".join(days))
    for d in days:
        _save(f"zcyc_{d}.json", _get(f"{ISS}/engines/stock/zcyc.json?date={d}&iss.only=params,yearyields"))
    print("cbr.ru и Росстат: ряды ключевой, инфляции, таблица ИПЦ, зарплаты")
    for name, url in CBR.items():
        _save(name, _get(url))
    for name, url in PLAIN.items():
        with urllib.request.urlopen(url, timeout=60) as r:
            _save(name, r.read())
        time.sleep(PAUSE)


if __name__ == "__main__":
    fetch()
