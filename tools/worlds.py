# -*- coding: utf-8 -*-
"""Источник миров ставок семейства 850: версии записей, проверка, индекс, сборка новой версии.

Версия — каталог `versions/<v>/`, после выпуска не меняется:
  VERSION.yaml                       паспорт версии (руками): статус, подписи для книг, дата решения ЦБ, шаг прогулки
  record/worlds_source.json, .csv    запись миров — байты, которые модели копируют побайтово (CRLF, как канон 1.4–1.7)
  inputs/worlds_inputs.yaml          входы записи (LF; строка 1 у каждой модели своя)
  recipe/worlds_recipe.py            рецепт, которым собрана запись (семейные строки документации, LF)
  bank/worlds_bank.json              банковская надстройка (LF) — побайтово у всех банков
  bank/bank_overlay_draft.yaml       черновик надстройки с диапазонами ЦБ (сборщик bank/build_overlay.py), если есть
  bank/sector_sheet.yaml             лист сектора с готовыми путями (сборщик bank/build_overlay_sector.py), если есть
  evidence/                          лист окна и фактов: скрипты, данные, выходы
  NOTES.md                           что изменилось против прошлой версии

`versions.json` — индекс, который читают команды приёма моделей (`ops/tools/adopt_worlds.py`); его пишет `index`
из паспортов и хэшей файлов, руками не правится.

  python -B tools/worlds.py verify [--version V]   хэши = индекс; рецепт версии и текущий рецепт воспроизводят запись;
                                                   надстройка воспроизводится из черновика
  python -B tools/worlds.py index [--check]        пересобрать versions.json (--check: индекс актуален)
  python -B tools/worlds.py show --version V       запись индекса (JSON)
  python -B tools/worlds.py new --version V --from U [--status trial]
                                                   каталог новой версии от U: входы, черновик, паспорт — для правки
  python -B tools/worlds.py build --version V      запись версии из её входов текущим рецептом (CRLF явно, на любой ОС),
                                                   рецепт копируется в версию; надстройка — из черновика

Только stdlib и PyYAML; Python 3.12+ (сумма float в 3.11 считается иначе, проверки записи там не гарантированы).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "versions"
INDEX = ROOT / "versions.json"
RECIPE_HEAD = ROOT / "recipe" / "worlds_recipe.py"
OVERLAY_BUILDER = ROOT / "bank" / "build_overlay.py"            # черновик с диапазонами ЦБ (форма книги Сбербанка)
SECTOR_BUILDER = ROOT / "bank" / "build_overlay_sector.py"     # лист с готовыми путями sector.worlds (форма Т)
SCHEMA = "850-worlds-index-v1"
STATUSES = ("canon", "trial")
REQUIRED = ("record/worlds_source.json", "record/worlds_source.csv", "inputs/worlds_inputs.yaml",
            "recipe/worlds_recipe.py", "VERSION.yaml")


class SourceError(RuntimeError):
    pass


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def vkey(v: str) -> tuple:
    out = []
    for part in v.replace("-", ".").split("."):
        out.append((0, int(part), "") if part.isdigit() else (1, 0, part))
    return tuple(out)


def version_dirs() -> list[Path]:
    return sorted((p for p in VERSIONS.iterdir() if (p / "VERSION.yaml").exists()), key=lambda p: vkey(p.name))


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def passport(vdir: Path) -> dict:
    meta = yaml.safe_load((vdir / "VERSION.yaml").read_text(encoding="utf-8"))
    if str(meta.get("version")) != vdir.name:
        raise SourceError(f"{vdir.name}: VERSION.yaml.version = {meta.get('version')!r}")
    if meta.get("status") not in STATUSES:
        raise SourceError(f"{vdir.name}: статус {meta.get('status')!r} не из {STATUSES}")
    return meta


def entry(vdir: Path) -> dict:
    """Запись индекса версии: паспорт + хэши всех файлов + поля, которые книги вписывают в шаблон."""
    meta = passport(vdir)
    missing = [f for f in REQUIRED if not (vdir / f).exists()]
    if missing:
        raise SourceError(f"{vdir.name}: нет файлов {missing}")
    rec_path = vdir / "record" / "worlds_source.json"
    record = json.loads(rec_path.read_bytes().decode("utf-8"))
    inputs = yaml.safe_load((vdir / "inputs" / "worlds_inputs.yaml").read_text(encoding="utf-8"))
    files = {p.relative_to(vdir).as_posix(): sha256(p) for p in sorted(vdir.rglob("*")) if p.is_file()}
    inputs_body = (vdir / "inputs" / "worlds_inputs.yaml").read_bytes().split(b"\n", 1)[1]
    e = {
        "version": vdir.name,
        "status": meta["status"],
        "tag": f"worlds-{vdir.name}",
        "origin": meta["origin"],
        "title": meta["title"],
        "cbr_decision": str(meta.get("cbr_decision") or ""),
        "built": str(meta.get("built") or ""),
        "record": {
            "sha256": files["record/worlds_source.json"],
            "csv_sha256": files["record/worlds_source.csv"],
            "asof": record["asof"],
            "curve_date": str(inputs["curve"]["date"]),
            "curve_lt": record.get("curve_lt"),
            "window_days": (record.get("market_window") or {}).get("days"),
            "rows": len(record["rows"]),
        },
        "recipe_sha256": files["recipe/worlds_recipe.py"],
        "inputs_body_sha256": hashlib.sha256(inputs_body).hexdigest(),
        "files": files,
    }
    ov = vdir / "bank" / "worlds_bank.json"
    if ov.exists():
        doc = json.loads(ov.read_text(encoding="utf-8"))
        e["overlay"] = {"sha256": files["bank/worlds_bank.json"], "as_of": doc["source"]["as_of"],
                        "recipe": doc["recipe"], "source_doc": doc["source"]["doc"],
                        "source_sha256": doc["source"]["sha256"]}
    for k in ("labels", "notes_for_models"):
        if k in meta:
            e[k] = meta[k]
    return e


def build_index() -> dict:
    entries = {d.name: entry(d) for d in version_dirs()}
    canon = [v for v, e in entries.items() if e["status"] == "canon"]
    return {"schema": SCHEMA, "latest": canon[-1] if canon else None, "versions": entries}


def render_index(idx: dict) -> str:
    return json.dumps(idx, ensure_ascii=False, indent=1) + "\n"


def load_index() -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def run_recipe(recipe: Path, inputs: Path, record: Path) -> tuple[int, str]:
    """`worlds_recipe.py --check` в отдельном процессе (тот же интерпретатор): код и последняя строка вывода."""
    p = subprocess.run([sys.executable, "-B", str(recipe), "--inputs", str(inputs), "--check", str(record)],
                       capture_output=True, text=True, encoding="utf-8", env=_env(), cwd=str(recipe.parent))
    lines = (p.stdout + p.stderr).strip().splitlines()
    return p.returncode, (lines[-1] if lines else "")


def _env() -> dict:
    import os
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def overlay_text(draft: Path, record: Path, builder: Path = OVERLAY_BUILDER) -> str:
    bo = load_module(builder, f"family_{builder.stem}")
    return bo.render(bo.build_overlay(bo.load_draft(draft), record.read_bytes()))


def verify(only: str | None = None) -> list[str]:
    bad: list[str] = []
    idx = load_index()
    fresh = build_index()
    if render_index(fresh) != INDEX.read_text(encoding="utf-8"):
        bad.append("versions.json не совпадает с паспортами и файлами версий — `tools/worlds.py index`")
    for v, e in idx["versions"].items():
        if only and v != only:
            continue
        vdir = VERSIONS / v
        for rel, h in e["files"].items():
            p = vdir / rel
            if not p.exists():
                bad.append(f"{v}: нет {rel}")
            elif sha256(p) != h:
                bad.append(f"{v}: {rel} — хэш не равен индексу (версия после выпуска не меняется)")
        rec, inp = vdir / "record" / "worlds_source.json", vdir / "inputs" / "worlds_inputs.yaml"
        if b"\r\n" not in rec.read_bytes()[:64]:
            bad.append(f"{v}: запись не в CRLF — модели копируют её побайтово, хэш разойдётся")
        for name, recipe in (("рецепт версии", vdir / "recipe" / "worlds_recipe.py"), ("текущий рецепт", RECIPE_HEAD)):
            code, last = run_recipe(recipe, inp, rec)
            print(f"  {v}: {name}: {last}")
            if code != 0:
                bad.append(f"{v}: {name} не воспроизводит запись: {last}")
        ov = vdir / "bank" / "worlds_bank.json"
        for name, builder in (("bank_overlay_draft.yaml", OVERLAY_BUILDER), ("sector_sheet.yaml", SECTOR_BUILDER)):
            draft = vdir / "bank" / name
            if ov.exists() and draft.exists():
                ok = overlay_text(draft, rec, builder) == ov.read_text(encoding="utf-8")
                print(f"  {v}: надстройка из {name} {'воспроизводится' if ok else 'НЕ воспроизводится'}")
                if not ok:
                    bad.append(f"{v}: надстройка не воспроизводится сборщиком bank/{builder.name} из {name}")
    return bad


def write_record(cand: dict, out: Path) -> None:
    """Как `write_candidate` рецепта, но с CRLF явно: запись одинакова байт в байт на Windows и Linux."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "worlds_source.json").write_text(json.dumps(cand, ensure_ascii=False, indent=1), encoding="utf-8",
                                            newline="\r\n")
    buf = io.StringIO(newline="")
    wr = csv.DictWriter(buf, fieldnames=list(cand["rows"][0].keys()), lineterminator="\r\n")
    wr.writeheader()
    wr.writerows(cand["rows"])
    (out / "worlds_source.csv").write_bytes(buf.getvalue().encode("utf-8"))


def build(v: str) -> int:
    vdir = VERSIONS / v
    if v in load_index()["versions"]:
        print(f"ОТКАЗ: версия {v} уже выпущена (в индексе) — новая запись только новой версией")
        return 1
    passport(vdir)
    recipe = load_module(RECIPE_HEAD, "family_worlds_recipe")
    inp = yaml.safe_load((vdir / "inputs" / "worlds_inputs.yaml").read_text(encoding="utf-8"))
    cand = recipe.build_worlds(inp)
    write_record(cand, vdir / "record")
    (vdir / "recipe").mkdir(exist_ok=True)
    shutil.copyfile(RECIPE_HEAD, vdir / "recipe" / "worlds_recipe.py")
    print(f"запись {v}: {len(cand['rows'])} строк, asof {cand['asof']}, sha256 {sha256(vdir / 'record' / 'worlds_source.json')}")
    draft = vdir / "bank" / "bank_overlay_draft.yaml"
    if draft.exists():
        text = overlay_text(draft, vdir / "record" / "worlds_source.json")
        (vdir / "bank" / "worlds_bank.json").write_text(text, encoding="utf-8", newline="\n")
        print(f"надстройка {v}: sha256 {sha256(vdir / 'bank' / 'worlds_bank.json')}")
    code, last = run_recipe(vdir / "recipe" / "worlds_recipe.py", vdir / "inputs" / "worlds_inputs.yaml",
                            vdir / "record" / "worlds_source.json")
    print("проверка рецептом:", last)
    return code


def new(v: str, base: str, status: str) -> int:
    src, dst = VERSIONS / base, VERSIONS / v
    if dst.exists():
        print(f"ОТКАЗ: каталог {dst} уже есть")
        return 1
    (dst / "inputs").mkdir(parents=True)
    shutil.copyfile(src / "inputs" / "worlds_inputs.yaml", dst / "inputs" / "worlds_inputs.yaml")
    if (src / "bank" / "bank_overlay_draft.yaml").exists():
        (dst / "bank").mkdir()
        shutil.copyfile(src / "bank" / "bank_overlay_draft.yaml", dst / "bank" / "bank_overlay_draft.yaml")
    meta = passport(src)
    meta.update(version=v, status=status, built=None, title=f"TODO: что нового против {base}")
    (dst / "VERSION.yaml").write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=120),
                                      encoding="utf-8", newline="\n")
    print(f"каталог {dst.relative_to(ROOT)}: правь входы, черновик надстройки и паспорт; затем `build --version {v}`")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.version_info < (3, 12):
        print("ОТКАЗ: нужен Python 3.12+ (в 3.11 сумма float иная — проверки записи не гарантированы)")
        return 2
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("verify"); p.add_argument("--version")
    p = sub.add_parser("index"); p.add_argument("--check", action="store_true")
    p = sub.add_parser("show"); p.add_argument("--version", required=True)
    p = sub.add_parser("new"); p.add_argument("--version", required=True); p.add_argument("--from", dest="base", required=True)
    p.add_argument("--status", default="canon", choices=STATUSES)
    p = sub.add_parser("build"); p.add_argument("--version", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "index":
            text = render_index(build_index())
            if a.check:
                ok = INDEX.exists() and INDEX.read_text(encoding="utf-8") == text
                print("versions.json", "актуален" if ok else "УСТАРЕЛ")
                return 0 if ok else 1
            INDEX.write_text(text, encoding="utf-8", newline="\n")
            print("записано versions.json:", ", ".join(json.loads(text)["versions"]))
            return 0
        if a.cmd == "show":
            print(json.dumps(load_index()["versions"][a.version], ensure_ascii=False, indent=1))
            return 0
        if a.cmd == "verify":
            bad = verify(a.version)
            print("ИСТОЧНИК В ПОРЯДКЕ" if not bad else "РАСХОЖДЕНИЯ:\n  " + "\n  ".join(bad))
            return 0 if not bad else 1
        if a.cmd == "new":
            return new(a.version, a.base, a.status)
        if a.cmd == "build":
            return build(a.version)
    except SourceError as e:
        print("ОТКАЗ:", e)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
