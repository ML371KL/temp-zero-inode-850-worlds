# -*- coding: utf-8 -*-
"""Движок приёма (model-kit/adopt_worlds.py): числа в текстах — язык меток, форматы, шаблон объяснений гейтов,
округление журналов."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("kit_adopt_worlds", ROOT / "model-kit" / "adopt_worlds.py")
A = importlib.util.module_from_spec(_spec)
sys.modules["kit_adopt_worlds"] = A
_spec.loader.exec_module(A)

REC = {"rows": [{"world": w, "period": p, "key_avg": v, "cpi": c} for w, rows in {
    "N": [("2026H2", 14.05, 6.6), ("2027H1", 13.25, 5.8), ("2027H2", 12.5, 5.6), ("2031H1", 8.0, 4.0), ("2031H2", 8.0, 4.0)],
    "M": [("2026H2", 14.0, 6.6), ("2027H1", 15.5, 5.7), ("2027H2", 17.7, 11.4), ("2031H1", 17.3, 10.1), ("2031H2", 17.3, 10.1)],
}.items() for p, v, c in rows], "curve": {"N": {"10": 10.04}}, "probs": {"N": 0.35}}
CELLS = {"cells": [{"world": "M", "regime": "crisis", "scenario": s, "pb": pb, "flags": f} for s, pb, f in
                   (("upper", 0.12, ["pb_by_world"]), ("strict", 0.21, ["pb_by_world", "x"]), ("mid", 0.5, []))],
         "checks": [{"name": "pb_by_world", "kind": "gate", "fired": True, "mass": 0.025380211281700277},
                    {"name": "roe_range", "kind": "gate", "fired": False, "mass": 0.0},
                    {"name": "spread_sign", "kind": "info", "fired": True, "mass": 1.0}]}
S = {"rec": REC, "res": CELLS}


@pytest.mark.parametrize("spec, want", [
    ("rec:rows[world=N&period=2026H2].key_avg r2t", "14,05"),
    ("rec:rows[*world=N&period^=2027].key_avg@mean r2t", "12,88"),          # 12,875 — половина вверх
    ("rec:rows[*world=N&period>=2031H1].key_avg@mean r2t", "8,0"),
    ("rec:rows[*world=N&period>=2031H1].key_avg@mean r2T", "8"),
    ("rec:curve.N.10 r2", "10,04"),
    ('rec:curve.N["10"] r2', "10,04"),
    ("rec:probs.N p0", "35"),
    ("rec:rows[*world=M]@argmax(key_avg,period) h", "2П2027"),
    ("rec:rows[*world=M].key_avg@max r1", "17,7"),
    ("rec:rows[*world=M]@settle(key_avg,period) yr", "2031"),
    ("rec:rows[-1].key_avg r1", "17,3"),
    ("res:cells[*flags~=pb_by_world].pb@span r2", "0,12–0,21"),
    ("res:cells[*flags~=pb_by_world]@keys(world,regime,scenario) str", "['M/crisis/strict', 'M/crisis/upper']"),
    ("res:cells[*flags~=pb_by_world]@len r0", "2"),
    ("res:checks[name=pb_by_world].mass y4", "0.0254"),
    ("res:checks[name=pb_by_world].mass y", "0.025380211281700277"),
    ("res:checks[name=pb_by_world].mass p1", "2,5"),
    ("rec:rows[world=M&period=2026H2].key_avg − rec:rows[world=N&period=2026H2].key_avg s2", "−0,05"),
    ("rec:rows[world=N&period=2026H2].key_avg - 14.05 s2", "0,00"),
    ("rec:rows[world=N&period=2026H2].key_avg * 1000 r0", "14 050"),
    ("res:checks[name=pb_by_world].mass @neg sp2", "−2,54"),
    ("( 1 + rec:curve.N.10 / 100 ) / ( 1 + 0.04 ) - 1 p2", "5,81"),
    ("2 + 3 * 4 r0", "14"),
    ("res:cells[*world=M&scenario=upper,strict].pb@span r2", "0,12–0,21"),
    ("res:cells[*scenario=mid|flags~=x].pb@sorted@first r2", "0,21"),
])
def test_marks_resolve_and_format(spec, want):
    if " @neg " in spec:                               # функция — хвост пути, не отдельное слово
        spec = spec.replace(" @neg", "@neg")
    assert A.eval_mark(spec, S) == want


def test_yaml_numbers_keep_their_digits():
    assert [A.format_value(x, "ys2") for x in (0.047939896, 0.020811, 0.2095249, 0.02973, 0.64054, 1.0)] ==         ["0.048", "0.021", "0.21", "0.03", "0.64", "1.0"]
    assert A.format_value(0.5176000000000001, "y4") == "0.5176" and A.format_value(0.54, "y") == "0.54"


def test_half_up_is_decimal_not_binary():
    assert A.ru_num(327.025) == "327,03" and A.ru_num(50.575) == "50,58" and A.ru_num(3173.105) == "3 173,11"
    assert A.format_value(0.12345, "p2") == "12,35" and A.format_value(-0.0004, "s2") == "0,00"


def test_bad_marks_say_why():
    for spec in ("rec:rows[world=N].key_avg r2", "zz:rows r2", "rec:rows[world=N&period=2026H2].key_avg q2",
                 "rec:rows[world=N&period=2026H2].nope r2"):
        with pytest.raises(A.MarkError):
            A.eval_mark(spec, S)


def test_doc_marks_rewrite_values_in_place():
    text = "| N | <!--~rec:curve.N.10 r2-->9,99<!--~--> % |\nбез меток\n"
    new, n, errors = A.render_doc_marks(text, S)
    assert (new, n, errors) == ("| N | <!--~rec:curve.N.10 r2-->10,04<!--~--> % |\nбез меток\n", 1, [])
    _, _, errors = A.render_doc_marks("<!--~rec:curve.N.10 r2-->10,04<!--~--> в начале\n", S)
    assert errors and "начале строки" in errors[0]


TEMPLATE = """# шапка
pb_by_world:
  #= состав: res:cells[*flags~=pb_by_world]@keys(world,regime,scenario) = ["M/crisis/strict", "M/crisis/upper"]
  explanation: >-
    Оценка — {{res:cells[*flags~=pb_by_world].pb@span r2}} капитала (вес {{res:checks[name=pb_by_world].mass p1}} %).
  expected_mass: {{res:checks[name=pb_by_world].mass y4}}

# ---- совещательные
roe_range:
  explanation: >-
    Текст.
  expected_mass: 0.0
corridor_holder:
  #= всегда
  explanation: >-
    Держит коридор.
"""


def test_gate_texts_render_drop_and_flag():
    fired = A.fired_names(CELLS, {"path": "checks", "where": {"kind": "gate"}})
    assert fired == ["pb_by_world"]
    r = A.render_gate_texts(TEMPLATE, None, S, fired + ["new_gate"])
    assert r["errors"] == [] and r["gone"] == ["roe_range"] and r["kept"] == ["pb_by_world", "corridor_holder"]
    assert "Оценка — 0,12–0,21 капитала (вес 2,5 %)." in r["text"] and "expected_mass: 0.0254" in r["text"]
    assert "#=" not in r["text"] and "roe_range" not in r["text"] and "# ---- совещательные" in r["text"]
    assert len(r["flags"]) == 1 and "new_gate" in r["flags"][0]
    other = {"rec": REC, "res": {**CELLS, "cells": CELLS["cells"][:1]}}
    r2 = A.render_gate_texts(TEMPLATE, r["text"], other, fired)
    assert any("состав не тот" in f for f in r2["flags"]) and "Оценка — 0,12 капитала" in r2["text"]


def test_a_broken_mark_keeps_the_old_entry_and_flags():
    tpl = TEMPLATE.replace("@span r2", ".nope r2")
    old = A.render_gate_texts(TEMPLATE, None, S, ["pb_by_world"])["text"]
    r = A.render_gate_texts(tpl, old, S, ["pb_by_world"])
    assert r["fallback"] == ["pb_by_world"] and r["text"] == old and any("не разобралась" in f for f in r["flags"])
    assert A.render_gate_texts(tpl, None, S, ["pb_by_world"])["errors"]
