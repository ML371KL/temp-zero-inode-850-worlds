# -*- coding: utf-8 -*-
"""Рецепт миров книги 1.7: правки правил яруса 2, уровень терминала правилом, окно рыночного снимка.

ЗАЧЕМ. Запись миров одна на шесть моделей семейства 850. Книга 1.7 меняет правила вывода якорей (решение
27.10.2026, WORLDS-RECIPE.md, раздел 3) и снимает мир M окном дней после решения Банка России (решение ведущего
29.10.2026, раздел 2.1). Всё новое включается только ключами входов, поэтому здесь проверяется:

* без новых ключей рецепт считает бит в бит как 1.6: каноны 1.4 и 1.3.1 воспроизводятся целиком, якоря правил на
  входах канона 1.4 и кандидата ведущего REC_win — те же, что у рецепта 1.6 (фикстура `anchors_recipe_1_6.json`
  снята рецептом из тега `v5`/1ebec750);
* каждая правка по отдельности делает то, что написано в разделе 3, и только это (второй заход 29.10.2026:
  продовольствие и зарплаты текущего полугодия по факту, средний ИПЦ H — середина соседних концов периода);
* на входах кандидата ведущего REC_win (оракул) правила дают его якоря N/H, кроме восьми строк, причина которых
  названа (ровный 2027 год мира H — правка, которой в оракуле нет; средний ИПЦ текущего полугодия — правило против
  ручных 6,7 / 6,8 оракула);
* окно рыночного снимка проверяется: дни не раньше решения, не больше 10, не меньше трёх, одни и те же дни у
  номинальной и реальной сторон, узлы и доходности записи — их среднее;
* запись 1.7 — выход правил на своих входах, и `--check` её воспроизводит.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "recipe" / "worlds_recipe.py"            # текущий рецепт источника (книга-источник: data/assumptions)
V14 = ROOT / "versions" / "1.4"
V17 = ROOT / "versions" / "1.7"
CANON_131 = Path(__file__).parent / "fixtures" / "canon-1.3.1"   # запись 1.3.1 (входы — 1.4 в режиме judgement)
FIX = Path(__file__).parent / "fixtures" / "worlds_rules_1_7"
FIELDS = ("key", "cpi_eop", "cpi_avg", "food_avg", "wage")
NEW_RULES = {"h_key_rule": "monotone", "h_cpi_rule": "cbr_upper_linear", "n_cpi_survey_blend": True}
FACT = {"yoy": {"2026-07": 5.98, "2026-08": 6.33, "2026-09": 6.35}}
FOOD = {"food_yoy": {"2026-07": 4.4, "2026-08": 5.1, "2026-09": 5.1}, "all_yoy": {"2026-07": 6.0, "2026-08": 6.3, "2026-09": 6.4}}
WAGE = {"yoy": {"2026-07": 10.29, "2026-08": 10.93}}


@pytest.fixture(scope="module")
def R():
    spec = importlib.util.spec_from_file_location("worlds_recipe_17", RECIPE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def canon14() -> dict:
    return _yaml(V14 / "inputs" / "worlds_inputs.yaml")


@pytest.fixture(scope="module")
def oracle() -> dict:
    """Кандидат ведущего REC_win (анализ 27.10.2026): входы окна 16–26.10 и его якоря N/H."""
    return _yaml(FIX / "inputs_REC_win.yaml")


@pytest.fixture(scope="module")
def old_rules() -> dict:
    return json.loads((FIX / "anchors_recipe_1_6.json").read_text(encoding="utf-8"))


def _with(inp: dict, **rules) -> dict:
    x = copy.deepcopy(inp)
    x["anchor_rules"].update(rules)
    return x


def _jsonable(anchors: dict) -> dict:
    return json.loads(json.dumps(anchors))


# ------------------------------------------------------------------ (1) без ключей — как 1.6


def test_canon_1_4_reproduces_whole_and_byte_for_byte(R, canon14, tmp_path):
    record = json.loads((V14 / "record" / "worlds_source.json").read_text(encoding="utf-8"))
    rebuilt = R.build_worlds(canon14)
    assert rebuilt == record
    assert "curve_lt" not in rebuilt and "market_window" not in rebuilt
    R.write_candidate(rebuilt, tmp_path)
    for name in ("worlds_source.json", "worlds_source.csv"):
        assert (tmp_path / name).read_bytes() == (V14 / "record" / name).read_bytes(), name


def test_canon_1_3_1_reproduces_in_judgement_mode(R, canon14):
    inp = copy.deepcopy(canon14)
    inp["m_inflation"]["source"] = "judgement"
    record = json.loads((CANON_131 / "worlds_source.json").read_text(encoding="utf-8"))
    assert R.compare(record, R.build_worlds(inp)) == []


@pytest.mark.parametrize("name, path", [("canon_1_4", V14 / "inputs" / "worlds_inputs.yaml"),
                                         ("rec_win", FIX / "inputs_REC_win.yaml")])
def test_without_new_keys_the_rules_are_those_of_1_6(R, old_rules, name, path):
    anchors, notes = R.candidate_anchors(_yaml(path))
    assert _jsonable(anchors) == old_rules[name]["anchors"]
    assert notes == old_rules[name]["notes"]


# ------------------------------------------------------------------ (2) правки раздела 3 по одной


def test_h_key_monotone_drops_the_year_below_steady_and_keeps_2027_flat(R, oracle, old_rules):
    """Проект ОНДКП 30.09: 14,0 / 11,5 + 1,25 / 9,0 + 1,25 = 10,25 < 10,5. Прежнее правило проваливало H до
    10,0 в 2029H2 и росло обратно; монотонное — 14,0 / 12,75 / 12,0 / 11,25 / 10,5, 2027 год ровно."""
    old = old_rules["rec_win"]["anchors"]["H"]["key"]
    assert min(old[p] for p in old if p != "2026H2") < 10.5          # провал ниже установившейся
    new, notes = R.candidate_anchors(_with(oracle, h_key_rule="monotone"))
    key = new["H"]["key"]
    path = [key[p] for p in R.periods_of("2027H1", 10)]
    assert path == sorted(path, reverse=True) and min(path) == 10.5
    assert key["2027H1"] == key["2027H2"] == 14.0
    assert [key[p] for p in ("2028H1", "2028H2", "2029H1", "2029H2", "2030H1", "2030H2")] == [13.0, 12.5, 12.25, 11.75, 11.5, 11.0]
    assert any("2029" in n and "не входит" in n for n in notes)
    for w in ("N", "M"):                                              # другие миры правка не трогает
        assert _jsonable(new[w]) == old_rules["rec_win"]["anchors"][w]


def test_h_cpi_from_the_cbr_upper_bound_even_with_the_scenario_published(R, oracle, old_rules):
    old = old_rules["rec_win"]["anchors"]["H"]["cpi_eop"]
    assert old["2028H2"] == 4.0                                       # прежде — ИПЦ сценария, к цели к 2028
    new, notes = R.candidate_anchors(_with(oracle, h_cpi_rule="cbr_upper_linear"))
    eop = new["H"]["cpi_eop"]
    assert eop == {"2026H2": 7.6, "2027H1": 7.4, "2027H2": 7.2, "2028H1": 7.0, "2028H2": 6.8, "2029H1": 6.6,
                   "2029H2": 6.3, "2030H1": 6.1, "2030H2": 5.9, "2031H1": 5.7, "2031H2": 5.5}
    assert any("только для сверки" in n for n in notes)
    assert not any("ОНДКП без инфляции" in n for n in notes)
    for f in ("key", "cpi_avg", "food_avg", "wage"):
        assert _jsonable(new["H"][f]) == old_rules["rec_win"]["anchors"]["H"][f]


def test_n_cpi_takes_the_survey_with_the_weight_of_the_rate(R, oracle, old_rules):
    new, _ = R.candidate_anchors(_with(oracle, n_cpi_survey_blend=True))
    w = oracle["survey"]["weight_in_N"]
    eop = new["N"]["cpi_eop"]
    assert eop["2027H2"] == R.rnd((1 - w) * 4.0 + w * 5.0, 0.1) == 4.7
    assert eop["2026H2"] == R.rnd((1 - w) * 7.35 + w * 7.1, 0.1) == 7.2
    assert old_rules["rec_win"]["anchors"]["N"]["cpi_eop"]["2027H2"] == 4.0
    assert new["N"]["cpi_avg"]["2027H1"] == 5.9 and new["N"]["cpi_avg"]["2028H1"] == 4.5
    assert _jsonable(new["N"]["key"]) == old_rules["rec_win"]["anchors"]["N"]["key"]
    assert _jsonable(new["M"]) == old_rules["rec_win"]["anchors"]["M"]   # M и верхняя граница H — по таблице ЦБ
    assert new["H"]["cpi_eop"]["2026H2"] == 7.6


def test_current_half_cpi_is_the_fact_plus_the_path_to_each_worlds_year_end(R, oracle):
    new, notes = R.candidate_anchors(dict(copy.deepcopy(oracle), cpi_actual=FACT))
    # июль–сентябрь факт, октябрь–декабрь — линейно от 6,35 к ИПЦ мира на конец 2026 года
    def expect(eop):
        return R.rnd((5.98 + 6.33 + 6.35 + sum(6.35 + (eop - 6.35) * k / 3 for k in (1, 2, 3))) / 6, 0.1)
    for w in ("N", "H", "M"):
        eop = new[w]["cpi_eop"]["2026H2"]
        assert new[w]["cpi_avg"]["2026H2"] == expect(eop)
    # без смешивания с опросом ИПЦ N на конец 2026 года — середина 7,35 диапазона ЦБ (7,3 после округления), H — 7,6
    assert (new["N"]["cpi_avg"]["2026H2"], new["H"]["cpi_avg"]["2026H2"], new["M"]["cpi_avg"]["2026H2"]) == (6.6, 6.7, 6.6)
    assert new["N"]["food_avg"]["2026H2"] == R.rnd(6.6 + 0.3, 0.1)                # связанные ряды — от нового среднего
    assert any(n.startswith("текущее полугодие") for n in notes)


def test_current_half_arithmetic(R):
    inp = {"cpi_actual": {"yoy": {f"2026-{m:02d}": 6.0 + m / 10 for m in range(7, 13)}}}
    assert R.current_half_cpi_avg(inp, "2026H2", 99.0) == pytest.approx(sum(6.0 + m / 10 for m in range(7, 13)) / 6)
    assert R.current_half_cpi_avg({"cpi_actual": {"yoy": {"2026-08": 6.0}}}, "2026H2", 7.0) is None   # нет июля
    assert R.current_half_cpi_avg({}, "2026H2", 7.0) is None


def test_current_half_food_takes_the_fact_spread_in_every_world(R, oracle, old_rules):
    """Второй заход (решение ведущего 29.10): наблюдённое полугодие не берёт долгосрочный спред продовольствия."""
    x = dict(copy.deepcopy(oracle), cpi_actual=dict(FACT, food_spread=FOOD))
    new, notes = R.candidate_anchors(x)
    spread = (4.4 + 5.1 + 5.1 - 6.0 - 6.3 - 6.4) / 3
    assert R.current_half_food_spread(x, "2026H2") == pytest.approx(spread) and round(spread, 4) == -1.3667
    for w in ("N", "H", "M"):
        assert new[w]["food_avg"]["2026H2"] == R.rnd(new[w]["cpi_avg"]["2026H2"] + spread, 0.1)
    assert (new["N"]["food_avg"]["2026H2"], new["H"]["food_avg"]["2026H2"], new["M"]["food_avg"]["2026H2"]) == (5.2, 5.3, 5.2)
    base, _ = R.candidate_anchors(dict(copy.deepcopy(oracle), cpi_actual=FACT))
    for w in ("N", "H", "M"):                                          # с 2027H1 — правила без изменений
        assert {p: v for p, v in new[w]["food_avg"].items() if p != "2026H2"} == \
               {p: v for p, v in base[w]["food_avg"].items() if p != "2026H2"}
        assert new[w]["cpi_avg"] == base[w]["cpi_avg"] and new[w]["wage"] == base[w]["wage"]
    assert any("фактический спред" in n for n in notes)


def test_current_half_wage_blends_published_months_with_the_world_rule(R, oracle):
    x = dict(copy.deepcopy(oracle), cpi_actual=FACT, wage_actual=WAGE)
    new, notes = R.candidate_anchors(x)
    base, _ = R.candidate_anchors(dict(copy.deepcopy(oracle), cpi_actual=FACT))
    for w in ("N", "H", "M"):
        rw = x["anchor_rules"]["real_wage_lt_pct"][w]
        rule = ((1 + base[w]["cpi_avg"]["2026H2"] / 100) * (1 + rw / 100) - 1) * 100
        assert new[w]["wage"]["2026H2"] == R.rnd((10.29 + 10.93 + 4 * rule) / 6, 0.1)
        assert {p: v for p, v in new[w]["wage"].items() if p != "2026H2"} == {p: v for p, v in base[w]["wage"].items() if p != "2026H2"}
        assert new[w]["food_avg"] == base[w]["food_avg"]
    assert R.current_half_wage({"wage_actual": {"yoy": {"2026-08": 10.9}}}, "2026H2", 9.0) is None   # нет июля
    assert any(n.startswith("текущее полугодие: зарплаты") for n in notes)


def test_h_cpi_avg_is_the_mid_of_its_period_ends(R, oracle, old_rules):
    """Второй заход: средний ИПЦ H согласован с ИПЦ H на конец периода — |средний − середина соседних концов| в
    пределах округления 0,1 для всех полугодий после текущего; текущее — по факту; установившиеся — как было."""
    x = _with(oracle, h_cpi_rule="cbr_upper_linear", h_cpi_avg_rule="eop_mid")
    x["cpi_actual"] = FACT
    new, _ = R.candidate_anchors(x)
    P = R.periods_of("2026H2", 21)
    eop = R.path(new["H"]["cpi_eop"], x["worlds"]["H"]["steady"]["cpi_eop"], P)
    avg = R.path(new["H"]["cpi_avg"], x["worlds"]["H"]["steady"]["cpi_avg"], P)
    for i in range(1, len(P)):
        assert abs(avg[i] - (eop[i - 1] + eop[i]) / 2) <= 0.05 + 1e-9, (P[i], avg[i], eop[i - 1], eop[i])
    plain, _ = R.candidate_anchors(_with(dict(copy.deepcopy(oracle), cpi_actual=FACT), h_cpi_rule="cbr_upper_linear"))
    assert new["H"]["cpi_avg"]["2026H2"] == plain["H"]["cpi_avg"]["2026H2"]          # текущее полугодие — факт
    assert abs(plain["H"]["cpi_avg"]["2028H2"] - (eop[3] + eop[4]) / 2) > 1.0          # без ключа — разрыв > 1 п.п.
    for p in new["H"]["cpi_avg"]:
        assert new["H"]["food_avg"][p] == R.rnd(new["H"]["cpi_avg"][p] + 0.5, 0.1) or p == "2026H2"
    for w in ("N", "M"):
        assert new[w] == plain[w]


def test_curve_lt_rule_block_only_by_key(R, canon14):
    plain = R.build_worlds(canon14)
    ruled = R.build_worlds(dict(copy.deepcopy(canon14), curve_lt_source="rule"))
    assert "curve_lt" not in plain
    assert ruled["curve_lt"] == R.curve_lt_rule(plain) == {"N": 8.9, "H": 12.6, "M": 16.7}
    assert {k: v for k, v in ruled.items() if k != "curve_lt"} == plain


# ------------------------------------------------------------------ (3) оракул REC_win


def test_oracle_rec_win_anchors_by_the_new_rules(R, oracle):
    inp = _with(oracle, **NEW_RULES)
    inp["cpi_actual"] = FACT
    new, _ = R.candidate_anchors(inp)
    diffs = {}
    for w in ("N", "H"):
        for f in FIELDS:
            rule = {p: v for p, v in new[w][f].items() if p != "steady"}
            for p in set(rule) | set(oracle["worlds"][w]["anchors"][f]):
                a, b = oracle["worlds"][w]["anchors"][f].get(p), rule.get(p)
                if a != b:
                    diffs[(w, f, p)] = (a, b)
    assert diffs == {
        # ровный 2027 год мира H (раздел 3, правило H): в оракуле правки нет — наклон 14,25 / 13,75
        ("H", "key", "2027H1"): (14.25, 14.0), ("H", "key", "2027H2"): (13.75, 14.0),
        # средний ИПЦ текущего полугодия: правило (июль–сентябрь + путь к ИПЦ мира на конец года) против ручных
        # 6,7 / 6,8 оракула; продовольствие и зарплаты — производные
        ("N", "cpi_avg", "2026H2"): (6.7, 6.6), ("N", "food_avg", "2026H2"): (7.0, 6.9),
        ("N", "wage", "2026H2"): (9.0, 8.9),
        ("H", "cpi_avg", "2026H2"): (6.8, 6.7), ("H", "food_avg", "2026H2"): (7.3, 7.2),
        ("H", "wage", "2026H2"): (8.8, 8.7),
    }


# ------------------------------------------------------------------ (4) окно рыночного снимка


@pytest.fixture(scope="module")
def record17() -> dict:
    return _yaml(V17 / "inputs" / "worlds_inputs.yaml")


def test_the_record_window_is_the_rule(R, record17):
    W = record17["curve"]["window"]
    assert sorted(W["days"]) == ["2026-10-23", "2026-10-26", "2026-10-27", "2026-10-28"]
    assert W["last_decision"] == "2026-10-23" and W["max_days"] == 10 and W["min_days"] == 3
    assert R.check_window(record17) == []


@pytest.mark.parametrize("break_it, says", [
    (lambda x: x["curve"]["window"].update(last_decision="2026-10-26"), "раньше дня решения"),
    (lambda x: x["curve"]["window"].update(max_days=3), "больше 3"),
    (lambda x: x["curve"]["window"].update(min_days=5), "третьего торгового дня"),
    (lambda x: x["ofz_in"]["window"]["days"].pop("2026-10-27"), "обе стороны"),
    (lambda x: x["curve"]["nodes"].update({"10": 16.5}), "узлы кривой записи"),
    (lambda x: x["ofz_in"]["bonds"][0].update(real_yield=9.1), "доходности ОФЗ-ИН записи"),
    (lambda x: x["curve"].update(date="2026-10-27"), "не дата снимка"),
])
def test_a_broken_window_is_refused(R, record17, break_it, says):
    x = copy.deepcopy(record17)
    break_it(x)
    bad = R.check_window(x)
    assert any(says in b for b in bad), bad
    with pytest.raises(SystemExit):
        R.market_window(x)


def test_fewer_than_three_days_after_the_decision_wait(R, record17):
    """Дополнение ведущего 29.10.2026: два дня после решения — снимок ждёт третьего торгового дня."""
    x = copy.deepcopy(record17)
    for side in (x["curve"]["window"]["days"], x["ofz_in"]["window"]["days"]):
        for d in ("2026-10-23", "2026-10-26"):
            side.pop(d)
    x["curve"]["nodes"] = R.window_mean(x["curve"]["window"]["days"])
    yields = R.window_mean(x["ofz_in"]["window"]["days"])
    for b in x["ofz_in"]["bonds"]:
        b["real_yield"] = yields[b["secid"]]
    x["curve"]["window"]["last_decision"] = "2026-10-27"
    assert any("третьего торгового дня" in b for b in R.check_window(x))


def test_market_window_noise_by_day(R, record17):
    mw = R.market_window(record17)
    assert mw["days"] == sorted(record17["curve"]["window"]["days"])
    # отчёт ведущего (раздел 4, п. 7): 23.10 — π_ss 10,42, терминал M 17,0, установившаяся ключевая M 17,6;
    # 26.10 — 10,17 / 16,8 / 17,3
    for day, (pi, lt, ss) in {"2026-10-23": (10.42, 17.0, 17.6), "2026-10-26": (10.17, 16.8, 17.3)}.items():
        d = mw["by_day"][day]
        assert round(d["pi_ss"], 2) == pi and d["curve_lt_M"] == lt and d["key_M_steady"] == ss
    for f, (lo, hi) in mw["range"].items():
        assert lo <= mw["window"][f] <= hi


# ------------------------------------------------------------------ (5) запись 1.7


def test_record_1_7_anchors_are_the_rules(R, record17):
    A, _ = R.candidate_anchors(record17)
    for w in ("N", "H"):
        for f in FIELDS:
            assert {p: v for p, v in A[w][f].items() if p != "steady"} == record17["worlds"][w]["anchors"][f], (w, f)
    M = record17["worlds"]["M"]
    assert {p: v for p, v in A["M"]["key"].items() if p != "steady"} == M["anchors"]["key"]
    assert A["M"]["key"]["steady"] == M["steady"]["key"]
    for f in ("cpi_eop", "cpi_avg", "food_avg", "wage"):                 # текущее полугодие M — по факту, как у N и H
        assert A["M"][f]["2026H2"] == M["anchors"][f]["2026H2"]
    built = R.build_worlds(record17)
    assert {w: record17["worlds"][w]["curve_lt"] for w in ("N", "H", "M")} == built["curve_lt"]


def test_record_1_7_reproduces(R, record17):
    record = json.loads((V17 / "record" / "worlds_source.json").read_text(encoding="utf-8"))
    assert R.build_worlds(record17) == record
