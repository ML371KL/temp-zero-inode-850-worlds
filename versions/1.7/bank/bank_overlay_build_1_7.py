# -*- coding: utf-8 -*-
"""Банковская надстройка миров (черновик) — сборка bank_overlay_draft.yaml из таблиц ЦБ и записи миров семейства.

ВЕРСИЯ ПЕРЕСБОРКИ МИРОВ 1.7 (29.10.2026, этап 1 канона): копия stage1/worlds/bank_overlay_build.py Сбера
(sha256 5dd9fd38…) с тремя заменами — база = среднесрочный прогноз ЦБ 23.10.2026 (forecast_261023.pdf, с. 1; те же
числа — табл. 3.2 итоговой ОНДКП 28.10.2026, PDF-с. 73), альтернативные сценарии — итоговая ОНДКП 28.10.2026
(табл. 3.3–3.5, PDF-с. 77 / 81 / 85), запись миров — 1.7 (magnit-850oa, ветка worlds-2026-10); остальные правила те же.
Пишет meta.overlay (as_of, recipe) — их берёт build_overlay.py листа (без блока — прежние константы).
Запуск: WORLDS_RECORD=<worlds_source.json> OVERLAY_OUT=<каталог> python -B bank_overlay_build_1_7.py

Входы (числа вписаны руками с документа, страницы указаны):
  * прогноз ЦБ 23.10.2026 (cbr.ru/Content/Document/File/198897/forecast_261023.pdf, sha256 0e007c6d…) — база;
  * ОНДКП 2027–2029, итоговая 28.10.2026 (cbr.ru/Content/Document/File/197907/on_2027(2028-2029).pdf, sha256 7e3b29af…):
    табл. 3.3 дезинфляционный (PDF-с. 77 / печ. 75), 3.4 проинфляционный (81/79), 3.5 рисковый (85/83);
  * «Банковский сектор. II кв. 2026» (ЦБ, сент. 2026): прогноз по балансам — PDF-с. 20 / печ. 19;
  * доля ИЖК в задолженности ФЛ — dataservice ЦБ (pub 20/ds 42 и pub 21/ds 46, measure 22 = РФ) на 01.08.2026;
  * запись миров 850oa worlds_source.json (sha256 7296567d…): средний ИПЦ миров по полугодиям.
Правила: N = базовый сценарий как есть; H и M — реальный рост базового сценария при инфляции своего мира
(g_w = (1+g_base)·(1+π_w)/(1+π_N) − 1, π — средний за год ИПЦ мира из записи; 2026 — одинаково во всех мирах);
кризисный режим = рисковый сценарий (табл. 3.5) как есть. «Прочая розница» = (население − w·ипотека)/(1 − w) [Р],
кроме 2026–2027 базы, где у ЦБ есть прямой прогноз (обзор II кв. 2026, с. 19). После 2029 — правило [В]: линейно к
номинальному ВВП мира (реальный 2,0 % — середина потенциала 1,5–2,5 %, ОНДКП PDF-с. 77 — × LT-инфляция мира) к 2031.
Запуск: python -B bank_overlay_build.py  → bank_overlay_draft.yaml
"""
import hashlib, json, os, sys
import yaml

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
WORLDS = os.environ.get("WORLDS_RECORD", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "record", "worlds_source.json"))
PRIMARY = os.environ.get("WORLDS_PRIMARY_DIR", "primary")   # первичка ЦБ — приватная папка (в черновик идут относительные пути)
OUT_DIR = os.environ.get("OVERLAY_OUT", os.path.dirname(os.path.abspath(__file__)))
YEARS = [2026, 2027, 2028, 2029]
R = lambda lo, hi: [lo, hi]

# ---------------------------------------------------------------- таблицы ОНДКП (%, г/г; [низ, верх]); 2024–2025 — факт
Y26 = dict(key_avg=R(14.6, 14.6), cpi_dec=R(7.1, 7.6), cpi_avg=R(6.2, 6.3), gdp=R(0.5, 1.0), m2=R(10, 13),
           claims=R(8, 11), orgs=R(9, 12), households=R(5, 8), mortgage=R(6, 9))       # 2026 — одинаково во всех таблицах
ONDKP = {
    "base": dict(table="прогноз ЦБ 23.10.2026 (= табл. 3.2 итоговой ОНДКП 28.10.2026, PDF-с. 73)", pdf_page=1, printed_page=1,
                 name="Базовый", years={
        2026: dict(Y26),
        2027: dict(key_avg=R(12.5, 13.5), cpi_dec=R(4.0, 4.0), cpi_avg=R(5.2, 5.7), gdp=R(1.0, 2.0), m2=R(5, 10),
                   claims=R(5, 10), orgs=R(6, 11), households=R(5, 10), mortgage=R(5, 10)),
        2028: dict(key_avg=R(9.0, 10.0), cpi_dec=R(4.0, 4.0), cpi_avg=R(4.0, 4.0), gdp=R(1.5, 2.5), m2=R(7, 12),
                   claims=R(8, 13), orgs=R(8, 13), households=R(8, 13), mortgage=R(10, 15)),
        2029: dict(key_avg=R(7.5, 8.5), cpi_dec=R(4.0, 4.0), cpi_avg=R(4.0, 4.0), gdp=R(1.5, 2.5), m2=R(7, 12),
                   claims=R(8, 13), orgs=R(8, 13), households=R(8, 13), mortgage=R(10, 15))}),
    "disinflation": dict(table="3.3", pdf_page=77, printed_page=75, name="Дезинфляционный", years={
        2026: dict(Y26),
        2027: dict(key_avg=R(10.0, 12.0), cpi_dec=R(3.0, 4.0), cpi_avg=R(4.5, 5.5), gdp=R(2.0, 3.0), m2=R(7, 12),
                   claims=R(7, 12), orgs=R(7, 12), households=R(8, 13), mortgage=R(8, 13)),
        2028: dict(key_avg=R(7.5, 8.5), cpi_dec=R(4.0, 4.0), cpi_avg=R(4.0, 4.0), gdp=R(2.0, 3.0), m2=R(8, 13),
                   claims=R(9, 14), orgs=R(9, 14), households=R(9, 14), mortgage=R(11, 16)),
        2029: dict(key_avg=R(7.5, 8.5), cpi_dec=R(4.0, 4.0), cpi_avg=R(4.0, 4.0), gdp=R(1.5, 2.5), m2=R(7, 12),
                   claims=R(8, 13), orgs=R(8, 13), households=R(8, 13), mortgage=R(10, 15))}),
    "proinflation": dict(table="3.4", pdf_page=81, printed_page=79, name="Проинфляционный", years={
        2026: dict(Y26),
        2027: dict(key_avg=R(14.0, 16.0), cpi_dec=R(4.5, 5.5), cpi_avg=R(5.2, 6.2), gdp=R(0.5, 1.5), m2=R(7, 12),
                   claims=R(3, 8), orgs=R(3, 8), households=R(4, 9), mortgage=R(4, 9)),
        2028: dict(key_avg=R(11.5, 12.5), cpi_dec=R(4.0, 4.0), cpi_avg=R(4.0, 4.5), gdp=R(0.5, 1.5), m2=R(7, 12),
                   claims=R(6, 11), orgs=R(6, 11), households=R(6, 11), mortgage=R(8, 13)),
        2029: dict(key_avg=R(8.5, 9.5), cpi_dec=R(4.0, 4.0), cpi_avg=R(4.0, 4.0), gdp=R(1.5, 2.5), m2=R(7, 12),
                   claims=R(6, 11), orgs=R(6, 11), households=R(6, 11), mortgage=R(8, 13))}),
    "risk": dict(table="3.5", pdf_page=85, printed_page=83, name="Рисковый", years={
        2026: dict(Y26),
        2027: dict(key_avg=R(19.0, 21.0), cpi_dec=R(11.0, 13.0), cpi_avg=R(8.1, 9.7), gdp=R(-4.0, -3.0), m2=R(4, 9),
                   claims=R(0, 5), orgs=R(2, 7), households=R(-5, 0), mortgage=R(0, 5)),
        2028: dict(key_avg=R(14.0, 16.0), cpi_dec=R(5.0, 7.0), cpi_avg=R(9.3, 11.4), gdp=R(-2.5, -1.5), m2=R(6, 11),
                   claims=R(2, 7), orgs=R(3, 8), households=R(-1, 4), mortgage=R(2, 7)),
        2029: dict(key_avg=R(9.5, 10.5), cpi_dec=R(4.0, 4.0), cpi_avg=R(3.6, 4.4), gdp=R(2.0, 3.0), m2=R(8, 13),
                   claims=R(9, 14), orgs=R(9, 14), households=R(10, 15), mortgage=R(12, 17))}),
}
# «Банковский сектор. II кв. 2026», печ. с. 19 (PDF 20): прогноз по балансам (база на прогнозе 24.07.2026)
BANK_REVIEW = dict(source="cbr_bs_review_2026q2.pdf, PDF-с. 20 / печ. 19 (текст пунктов 1–4 к графикам)",
                   companies={2026: R(7, 11), 2027: R(7, 12)}, mortgage={2026: R(6, 10), 2027: R(7, 12)},
                   other_retail={2026: R(4, 8), 2027: R(3, 8)}, client_funds={2026: R(7, 12), 2027: None})
# доля ИЖК в задолженности ФЛ, 01.08.2026: 21 723 362 / 37 413 036 млн ₽ (dataservice ЦБ; stage1/worlds/cbr_dataservice_hh_loans_2026.json)
HH_TOTAL, HH_MORTGAGE = 37413036.0, 21723362.0
W_MORT = round(HH_MORTGAGE / HH_TOTAL, 4)
REAL_POTENTIAL = 2.0          # ОНДКП PDF-с. 77: «устойчивым долгосрочным темпам роста потенциала 1,5 – 2,5%» — середина
CONVERGE_YEAR = 2031          # как converge_year рецепта миров 850oa


def mid(r):
    return None if r is None else round((r[0] + r[1]) / 2, 3)


def other_retail(h, m):
    lo = (h[0] - W_MORT * m[0]) / (1 - W_MORT)
    hi = (h[1] - W_MORT * m[1]) / (1 - W_MORT)
    return [round(lo, 2), round(hi, 2)]


def world_cpi(src):
    """средний за год ИПЦ мира = среднее двух полугодий cpi_yoy_avg записи (2026 — только H2)."""
    out = {}
    for w in ("N", "H", "M"):
        rows = {r["period"]: r["cpi_yoy_avg"] for r in src["rows"] if r["world"] == w}
        out[w] = {y: round((rows[f"{y}H1"] + rows[f"{y}H2"]) / 2, 3) for y in range(2027, 2037)}
        out[w][2026] = rows["2026H2"]
    return out


def reprice(r, f):
    return None if r is None else [round(((1 + v / 100) * f - 1) * 100, 2) for v in r]


def main():
    raw = open(WORLDS, "rb").read()
    src = json.loads(raw.decode("utf-8"))
    cpi = world_cpi(src)
    lt_pi = src["lt_inflation"]
    base = ONDKP["base"]["years"]
    worlds = {}
    for w in ("N", "H", "M"):
        yrs = {}
        for y in YEARS:
            b = base[y]
            f = 1.0 if (w == "N" or y == 2026) else (1 + cpi[w][y] / 100) / (1 + cpi["N"][y] / 100)
            orr = BANK_REVIEW["other_retail"].get(y) if y <= 2027 else None
            orr_src = "ЦБ, обзор II кв. 2026" if orr else "[Р] (население − w·ипотека)/(1 − w)"
            orr = orr or other_retail(b["households"], b["mortgage"])
            ngdp_base = [round(((1 + b["gdp"][i] / 100) * (1 + b["cpi_avg"][i] / 100) - 1) * 100, 2) for i in (0, 1)]
            row = dict(repricing_factor=round(f, 5),
                       pi_world_avg=cpi[w][y] if y > 2026 else None,
                       nominal_gdp_proxy=reprice(ngdp_base, f), m2=reprice(b["m2"], f),
                       claims_total=reprice(b["claims"], f), orgs=reprice(b["orgs"], f),
                       households=reprice(b["households"], f), mortgage=reprice(b["mortgage"], f),
                       other_retail=reprice(orr, f), other_retail_source=orr_src,
                       client_funds=reprice(BANK_REVIEW["client_funds"].get(y), f) if y <= 2027 else None)
            yrs[y] = row
        # 2030+ [В]: линейно от 2029 к номинальному ВВП мира к 2031
        ng_lt = round(((1 + REAL_POTENTIAL / 100) * (1 + lt_pi[w] / 100) - 1) * 100, 2)
        c29 = mid(yrs[2029]["claims_total"])
        path = {}
        for y in range(2030, 2037):
            k = min(1.0, (y - 2029) / (CONVERGE_YEAR - 2029))
            path[y] = round(c29 + k * (ng_lt - c29), 2)
        worlds[w] = dict(years=yrs, claims_growth_2030_2036_mid=path, nominal_gdp_lt=ng_lt, lt_inflation=lt_pi[w])
    doc = dict(
        meta=dict(status="пересборка миров 1.7, 29.10.2026 (этап 1 канона: база — прогноз ЦБ 23.10.2026, сценарии — итоговая ОНДКП 28.10.2026, запись миров 1.7); в книгу — решением автора книги",
                  units="% г/г; [низ, верх] — диапазон ЦБ; середина — mid()",
                  worlds_record=dict(path=WORLDS, sha256=hashlib.sha256(raw).hexdigest(), asof=src["asof"]),
                  sources=dict(
                      ondkp=dict(file=f"{PRIMARY}/forecast_261023.pdf",
                                 url="https://www.cbr.ru/Content/Document/File/198897/forecast_261023.pdf",
                                 sha256="0e007c6d0d654b9ada9beb10ea7a6cec66d3973385fb7795677db095dd8e9cb2",
                                 note="база надстройки — «Среднесрочный прогноз Банка России по итогам заседания Совета директоров по ключевой ставке 23 октября 2026 года», с. 1 (сноска ¹: средняя КС 01.01–25.10.2026 = 14,7 %, 26.10–31.12.2026 — 14,0 %); те же числа — табл. 3.2 итоговой ОНДКП 28.10.2026 (PDF-с. 73). Ключ блока — ondkp, как читает build_overlay.py"),
                      ondkp_final=dict(file=f"{PRIMARY}/ondkp_2027_2029_final.pdf",
                                       url="https://www.cbr.ru/Content/Document/File/197907/on_2027(2028-2029).pdf",
                                       sha256="7e3b29af616175fd33324aed85d446c4f55e5b7c3c34c938a12610bb65a4a6a9",
                                       note="итоговая ОНДКП 2027–2029 от 28.10.2026: альтернативные сценарии — табл. 3.3–3.5 (PDF-с. 77 / 81 / 85); проект 30.09.2026 — sha256 3c3270ef…"),
                      bank_review=dict(file=f"{PRIMARY}/cbr_bs_review_2026q2.pdf",
                                       url="https://www.cbr.ru/Collection/Collection/File/62347/analytical_review_bs-2026-2.pdf",
                                       sha256="ed4826f87f33741defd797d1c53f7da5ebf28c0944264fed9d4d965e268e5f4e"),
                      hh_mortgage_weight=dict(value=W_MORT, asof="2026-08-01",
                                              basis="задолженность по кредитам ФЛ-резидентам: ИЖК 21 723 362 / всего 37 413 036 млн ₽",
                                              source="cbr.ru/dataservice pub 20/ds 42 и pub 21/ds 46, measure 22 (РФ); stage1/worlds/cbr_dataservice_hh_loans_2026.json")),
                  conventions=[
                      "Требования банковской системы к экономике — по сноске ³ табл. 3.2 (кредиты, бумаги, участие; без валютной переоценки); «к населению» включает ИЖК.",
                      "Ставки и инфляция миров берутся ТОЛЬКО из записи миров (worlds_source.json); ключевая и ИПЦ ОНДКП здесь — справочно и для пересчёта.",
                      "N = базовый сценарий как есть. H, M = реальный рост базы × инфляция мира: g_w = (1+g_base)·(1+π_w)/(1+π_N) − 1; π — средний ИПЦ мира за год (среднее полугодий cpi_yoy_avg); 2026 — одинаково во всех мирах (год почти прожит).",
                      "Кризисный режим = рисковый сценарий (табл. 3.5) как есть; ставка рискового сценария (КС 19–21 % в 2027) в миры НЕ переносится — гейт «M × кризис» сверяет CoR, рост кредита и нормативы.",
                      "Номинальный ВВП — прокси: (1 + реальный ВВП)·(1 + средний ИПЦ) − 1 (дефлятора в таблице нет).",
                      "После 2029 [В]: рост требований линейно от 2029 к номинальному ВВП мира (2,0 % реально × LT-инфляция мира) к 2031, далее постоянно (кредит/ВВП стабилен).",
                      "Альтернатива для H (не принята): реальный рост проинфляционного сценария (табл. 3.4) вместо базового — ниже в 2027–2028 на 2–3 п.п.",
                      "«Прочая розница» 2026–2027 — прогноз по балансам из обзора «Банковский сектор. II кв. 2026» (собран на прогнозе 24.07.2026); новее обзора на 29.10.2026 нет."],
                  overlay=dict(as_of="2026-10-23", recipe=(
                      "N — середины диапазонов базового сценария Банка России: среднесрочный прогноз 23.10.2026 "
                      "(forecast_261023.pdf, с. 1, sha256 0e007c6d…; те же числа — табл. 3.2 итоговой ОНДКП 2027–2029 от "
                      "28.10.2026, PDF-с. 73), кроме «прочей розницы» 2026–2027 — прогноз ЦБ по балансам («Банковский сектор. "
                      "II кв. 2026», PDF-с. 20 / печ. 19, sha256 ed4826f8…) и 2028–2029 — [Р] (население − w·ИЖК)/(1 − w), "
                      "w = 0,5806 (доля ИЖК в задолженности ФЛ на 01.08.2026, dataservice ЦБ). H и M — реальный рост базы при "
                      "инфляции своего мира: g_W = (1 + g_N)·(1 + π_W)/(1 + π_N) − 1, π — средний ИПЦ мира за год по записи "
                      f"миров семейства 1.7 (worlds_source.json, sha256 {hashlib.sha256(open(WORLDS, 'rb').read()).hexdigest()[:8]}…); "
                      "2026 — одинаково во всех мирах. credit_growth.corporate — «организации», mortgage — ИЖК, retail_other — "
                      "«прочая розница»; funds_growth.retail = funds_growth.corporate = М2 (раздельных рядов нет); "
                      "nominal_gdp_growth — справочно. Середины диапазонов → доли. Годы 2026–2029; после 2029 ядро сводит рост "
                      "объёмов к g_T мира к volumes.lt_from (MODEL §4.3). Сборщик — "
                      "data/assumptions/evidence/worlds_bank/build_overlay.py; вход — черновик надстройки "
                      "(evidence/worlds_bank/inputs/bank_overlay_draft.yaml)."))),
        cbr_scenarios=ONDKP, cbr_bank_review_2026q2=BANK_REVIEW,
        worlds=worlds,
        crisis_regime=dict(source="ОНДКП табл. 3.5 (рисковый), PDF-с. 85 / печ. 83", years={
            y: dict(ONDKP["risk"]["years"][y], other_retail=other_retail(ONDKP["risk"]["years"][y]["households"], ONDKP["risk"]["years"][y]["mortgage"]))
            for y in YEARS}),
    )
    out = os.path.join(OUT_DIR, "bank_overlay_draft.yaml")
    header = ("# Банковская надстройка миров — ЧЕРНОВИК (пересборка миров 1.7, 29.10.2026: база — прогноз ЦБ 23.10.2026).\n"
              "# Собрано bank_overlay_build_1_7.py (канон миров 1.7, impl/canon/bank); править входы там, не здесь. Источники и страницы — блок meta.sources и поля table/pdf_page.\n")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(header)
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False, width=140, default_flow_style=None)
    print("записано", out)
    print("w(ИЖК/ФЛ) =", W_MORT)
    for w in ("N", "H", "M"):
        print(w, "π:", {y: cpi[w][y] for y in (2027, 2028, 2029)}, "LT", lt_pi[w])
        for y in YEARS:
            r = worlds[w]["years"][y]
            print(f"  {y} f={r['repricing_factor']:.4f} требования {r['claims_total']} орг {r['orgs']} насел {r['households']} ИЖК {r['mortgage']} "
                  f"прочая {r['other_retail']} M2 {r['m2']} ВВПн {r['nominal_gdp_proxy']}")
        print("  2030+ требования (сер.):", worlds[w]["claims_growth_2030_2036_mid"], "ВВПн LT", worlds[w]["nominal_gdp_lt"])
    for y in YEARS:
        print("кризис", y, doc["crisis_regime"]["years"][y]["claims"], "прочая", doc["crisis_regime"]["years"][y]["other_retail"])


if __name__ == "__main__":
    main()
