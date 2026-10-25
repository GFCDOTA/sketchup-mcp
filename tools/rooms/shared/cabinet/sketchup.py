"""Materializacao do gabinete no SketchUp (FP-043/P6b): driver Python dos jobs Ruby `cabinet_build` e `cabinet_inspect`.

Regras (as mesmas dos jobs su_*; ver tools/sketchup/jobs.py):
- so materializa plano que passou por `require_valid` — a chamada FALHA antes de subir o SketchUp se nao passou;
- o SketchUp abre uma COPIA (ou um modelo novo); a saida e sempre arquivo novo, nunca fixtures/ nem artifacts/;
- o PID do SketchUp que subimos vem no resultado: fecha-se so esse PID (nunca por nome de processo);
- a inspecao reabre o arquivo SALVO em outro processo (prova de save/reopen), em copia.
`verify` compara o plano com a inspecao geometrica real (vertices de mundo, manifold, material, tag, atributos).
"""
from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Any

from tools.sketchup import paths
from tools.sketchup.batch import run_job
from tools.sketchup.process import SketchUp

from .plan import CAPABILITY_ID, require_valid
from .scratch import scratch_dir

RUBY_DIR = Path(__file__).resolve().parent / "ruby"
BUILD_JOB, INSPECT_JOB = RUBY_DIR / "cabinet_build.rb", RUBY_DIR / "cabinet_inspect.rb"
GRAIN_SUPPORT = "NOT_SUPPORTED"


def _out(out_skp: str | Path, base: Path | None) -> tuple[Path | None, dict | None]:
    try:
        out = paths.check_output(out_skp, inputs=(base,) if base else ())
    except paths.OutputPathRefused as exc:
        return None, {"status": "REFUSED", "reason": str(exc)}
    if out.suffix.lower() != ".skp":
        return None, {"status": "ERROR", "reason": f"out_skp precisa terminar em .skp: {out}"}
    if out.exists():
        return None, {"status": "REFUSED", "reason": f"{out} ja existe; a materializacao sai sempre em arquivo novo"}
    return out, None


def materialize(plan: dict, out_skp: str | Path, *, base_skp: str | Path | None = None, edits: list[dict] | None = None,
                mode: str | None = None, timeout_s: int = 240, su: SketchUp | None = None) -> dict[str, Any]:
    """Constroi (ou, com `edits`, edita) o gabinete numa copia/modelo novo e salva. `require_valid` primeiro."""
    require_valid(plan)                                   # PlanRefused ANTES de qualquer processo
    su = su or SketchUp()
    base = paths.resolve(base_skp) if base_skp else None
    if base is not None and (base.suffix.lower() != ".skp" or not base.exists()):
        return {"status": "ERROR", "reason": f"base nao e um .skp existente: {base}"}
    out, err = _out(out_skp, base)
    if err:
        return err
    out.parent.mkdir(parents=True, exist_ok=True)
    skp_in = None
    if base is not None:
        shutil.copy2(base, out)
        skp_in = out
    started_ns = out.stat().st_mtime_ns if out.exists() else 0
    job_dir = out.parent / f"_{out.stem}_build"
    res = run_job(su, "cabinet_build", out_dir=job_dir, skp_in=skp_in, timeout_s=timeout_s, mode=mode, script=BUILD_JOB,
                  params={"plan": plan, "save_as": str(out).replace("\\", "/") if skp_in is None else "", "edits": edits})
    res["out_skp"] = str(out)
    res["base_skp"] = str(base) if base else None
    if res.get("status") == "OK":
        saved = res["result"].get("saved") is True and out.exists() and out.stat().st_mtime_ns >= started_ns
        if not saved:
            res.update(status="FAILED", reason=f"o job disse ok mas {out} nao foi gravado")
    if res.get("status") != "OK":
        _discard_unedited(out, res)          # job interrompido/falho: a copia nao editada NAO pode parecer resultado
    return res


def _discard_unedited(out: Path, res: dict[str, Any]) -> None:
    """Copia sem o gabinete nao e resultado. Se o SketchUp ainda a segura aberta (Windows), deixa um marcador ao lado."""
    try:
        out.unlink(missing_ok=True)
        res["unedited_copy_removed"] = True
    except OSError as exc:
        marker = out.with_name(out.name + ".NOT_A_RESULT.txt")
        marker.write_text(f"{out.name} e a copia NAO editada (o job nao concluiu: {res.get('reason') or res.get('status')}). "
                          f"Pode estar aberta no SketchUp PID {res.get('pid')}; apague depois de fechar." + chr(10), encoding="utf-8")
        res.update(unedited_copy_removed=False, unedited_copy_marker=str(marker), cleanup_error=f"{type(exc).__name__}: {exc}")


def inspect(skp: str | Path, *, mode: str | None = None, timeout_s: int = 180, su: SketchUp | None = None) -> dict[str, Any]:
    """Reabre o .skp (uma COPIA, em outro processo) e devolve a inspecao geometrica dos gabinetes."""
    src = paths.resolve(skp)
    if src.suffix.lower() != ".skp" or not src.exists():
        return {"status": "ERROR", "reason": f"nao e um .skp existente: {src}"}
    job_dir = scratch_dir(src, "cabinet_inspect", adjacent_suffix="inspect")     # nunca ao lado de .skp protegido (R3 / T0.2)
    job_dir.mkdir(parents=True, exist_ok=True)
    copy = job_dir / f"_copy_{src.name}"
    shutil.copy2(src, copy)
    res = run_job(su or SketchUp(), "cabinet_inspect", out_dir=job_dir, skp_in=copy, timeout_s=timeout_s, mode=mode,
                  script=INSPECT_JOB, params={})
    res["input_skp"] = str(src)
    return res


# ----------------------------------------------------------------------------- verificacao plano x SketchUp
def expected_corners(plan: dict, part: dict) -> list[tuple[float, float, float]]:
    """8 vertices de mundo (m) da peca: caixa local -> rotacao em +z -> translacao da pose."""
    th = math.radians(plan["pose"]["rotation_deg"])
    c, s = math.cos(th), math.sin(th)
    out = []
    for x in (part["min_m"][0], part["max_m"][0]):
        for y in (part["min_m"][1], part["max_m"][1]):
            for z in (part["min_m"][2], part["max_m"][2]):
                out.append((plan["pose"]["x"] + c * x - s * y, plan["pose"]["y"] + s * x + c * y, plan["pose"]["z"] + z))
    return out


def _match(expected: list[tuple], got: list[list[float]], tol: float) -> float | None:
    """Maior distancia do pareamento guloso vertice a vertice; None se algum vertice nao casa dentro de tol."""
    pool = [tuple(g) for g in got]
    worst = 0.0
    for e in expected:
        best = min(pool, key=lambda g: math.dist(e, g), default=None)
        if best is None or math.dist(e, best) > tol:
            return None
        worst = max(worst, math.dist(e, best))
        pool.remove(best)
    return worst


def verify(plan: dict, inspected: dict, *, tol_m: float = 1e-5, baseline: dict | None = None) -> dict:
    """Compara plano x modelo REABERTO. `inspected` = result do job cabinet_inspect. Tolerancia 0,01 mm: o SketchUp guarda
    polegadas em ponto flutuante (erro ~1e-9) e o job arredonda a 6 casas; nao e folga de projeto."""
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    cabs = [c for c in inspected["cabinets"] if c["request_id"] == plan["request_id"]]
    check("exactly_one_cabinet_root", len(cabs) == 1, f"{len(cabs)} grupo(s) para {plan['request_id']}")
    if len(cabs) != 1:
        return {"ok": False, "checks": checks}
    cab = cabs[0]
    check("capability_attribute", cab["capability"] == CAPABILITY_ID and cab["capability_version"] == plan["capability"]["version"])
    check("signature_attribute", cab["signature"] == plan["signature"])
    check("root_tag", cab["tag"] == "Cabinet")
    check("no_loose_geometry_in_root", cab["loose_faces"] == 0 and cab["loose_edges"] == 0)
    by_id = {p["part_id"]: p for p in cab["parts"]}
    plan_ids = [p["id"] for p in plan["parts"]]
    check("part_ids_match_plan", sorted(by_id) == sorted(plan_ids) and len(cab["parts"]) == len(plan_ids),
          f"plano={len(plan_ids)} modelo={len(cab['parts'])}")
    worst = 0.0
    for part in plan["parts"]:
        got = by_id.get(part["id"])
        if got is None:
            check(f"part:{part['id']}", False, "ausente")
            continue
        d = _match(expected_corners(plan, part), got["world_corners_m"], tol_m)
        worst = max(worst, d or 0.0)
        check(f"corners:{part['id']}", d is not None, "vertices de mundo fora de tolerancia" if d is None else f"max {d:.2e} m")
        check(f"solid:{part['id']}", got["manifold"] and got["geometry"]["faces"] == 6 and got["geometry"]["edges"] == 12,
              f"manifold={got['manifold']} faces={got['geometry']['faces']} edges={got['geometry']['edges']}")
        check(f"material:{part['id']}", got["material"] == part["material"] and got["attr_material"] == part["material"],
              f"{got['material']!r}")
        check(f"tag:{part['id']}", got["tag"] == f"Cabinet_{part['role']}", got["tag"])
        check(f"name:{part['id']}", got["name"] == part["id"])
    for d in plan["definitions"]:
        names = {by_id[i]["definition"] for i in d["instances"] if i in by_id}
        check(f"definition_sharing:{d['key']}", len(names) == 1 and (not d["shared"] or by_id[d["instances"][0]]["definition_instances"] >= len(d["instances"])),
              f"{sorted(names)}")
    check("grain_not_claimed", GRAIN_SUPPORT == "NOT_SUPPORTED", "veio registrado, nao aplicado")
    if baseline is not None:
        check("non_cabinet_unchanged", baseline["non_cabinet"]["fingerprint"] == inspected["non_cabinet"]["fingerprint"]
              and baseline["non_cabinet"]["count"] == inspected["non_cabinet"]["count"], "arquitetura/outros objetos intactos")
    return {"ok": all(c["ok"] for c in checks), "checks": checks, "max_corner_error_m": worst}
