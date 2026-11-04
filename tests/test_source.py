# -*- coding: utf-8 -*-
"""Источник миров: индекс актуален, версии целы и воспроизводятся, публичная гигиена."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import worlds as W  # noqa: E402


def test_the_index_is_built_from_the_versions():
    assert W.render_index(W.build_index()) == (ROOT / "versions.json").read_text(encoding="utf-8")


def test_every_version_is_whole_and_reproduces():
    assert W.verify() == []


def test_records_are_crlf_bytes_and_git_keeps_them():
    for v in W.version_dirs():
        rec = (v / "record" / "worlds_source.json").read_bytes()
        assert b"\r\n" in rec and b"\n" not in rec.replace(b"\r\n", b""), v.name
    out = subprocess.run(["git", "-C", str(ROOT), "check-attr", "text", "--", "versions/1.7/record/worlds_source.json"],
                         capture_output=True, text=True).stdout
    assert out.strip().endswith("unset"), out


def test_a_canon_version_has_what_models_read():
    idx = json.loads((ROOT / "versions.json").read_text(encoding="utf-8"))
    for v, e in idx["versions"].items():
        if e["status"] != "canon":
            continue
        assert {"record/worlds_source.json", "record/worlds_source.csv", "inputs/worlds_inputs.yaml",
                "recipe/worlds_recipe.py", "doc/WORLDS-RECIPE.md"} <= set(e["files"]), v
        assert e["record"]["asof"] and e["record"]["curve_date"] and e["origin"], v
        doc = (ROOT / "versions" / v / "doc" / "WORLDS-RECIPE.md").read_text(encoding="utf-8")
        assert "<<book_gen>>" in doc, v


def test_no_local_paths_or_private_words_in_tracked_files():
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout.split()
    sep = chr(92)
    bad_marks = ("C:/Users", "C:" + sep + "Users", "/home/", "Desktop/Claude", "Desktop" + sep + "Claude")
    words = []
    wl = os.environ.get("HYGIENE_WORDS")
    if wl and Path(wl).exists():
        words = [w.strip() for w in Path(wl).read_text(encoding="utf-8").splitlines() if w.strip() and not w.startswith("#")]
    hits = []
    for f in files:
        p = ROOT / f
        if p.suffix in (".xlsx", ".pdf", ".png"):
            hits.append(f"{f}: первичный файл в публичном репозитории")
            continue
        text = p.read_bytes().decode("utf-8", errors="ignore")
        hits += [f"{f}: {m}" for m in bad_marks if m in text and f != "tests/test_source.py"]
        hits += [f"{f}: слово из личного списка" for w in words if w.lower() in text.lower()]
    assert not hits, hits


@pytest.mark.skipif(sys.version_info < (3, 12), reason="источник считается на Python 3.12+")
def test_the_tool_refuses_nothing_on_this_python():
    p = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "worlds.py"), "index", "--check"],
                       capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stdout + p.stderr
