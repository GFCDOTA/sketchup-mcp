"""Materializacao da porta Shaker no SketchUp (FP-046/P3): driver Python dos jobs Ruby `shaker_build` e `shaker_inspect`.

Mesmas regras do gabinete (`..sketchup`): so materializa plano que passou por `require_valid_shaker` — a chamada FALHA antes de
subir o SketchUp; o SketchUp abre uma COPIA do .skp que ja contem o gabinete pai (nunca fixtures/ nem artifacts/); o PID que
subimos vem no resultado e so ele e fechado; a inspecao reabre o arquivo SALVO em outro processo.
`verify_shaker` compara plano x modelo reaberto: vertices de mundo por peca, recuo do painel MEDIDO nas coordenadas do modelo,
frente lisa substituida ausente, uma unica submontagem por request_id, definicoes compartilhadas so entre equivalentes.
"""
from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Any

from tools.sketchup import paths
from tools.sketchup.batch import run_job
from tools.sketchup.process import SketchUp

from ..scratch import scratch_dir
from ..sketchup import GRAIN_SUPPORT, _discard_unedited, _match, _out, expected_corners
from .plan import CAPABILITY_ID, ShakerPlanRefused, require_valid_shaker

RUBY_DIR = Path(__file__).resolve().parent.parent / "ruby"
BUILD_JOB, INSPECT_JOB = RUBY_DIR / "shaker_build.rb", RUBY_DIR / "shaker_inspect.rb"


def materialize_shaker(plan: dict, parent_plan: dict, out_skp: str | Path, *, base_skp: str | Path,
                       edits: list[dict] | None = None, mode: str | None = None, timeout_s: int = 240,
                       su: SketchUp | None = None) -> dict[str, Any]:
    """Aplica a Shaker (ou, com `edits`, edita) no gabinete pai de uma COPIA de `base_skp` e salva. `require_valid_shaker` primeiro."""
    require_valid_shaker(plan, parent_plan)               # ShakerPlanRefused ANTES de qualquer processo
    su = su or SketchUp()
    base = paths.resolve(base_skp)
    if base.suffix.lower() != ".skp" or not base.exists():
        return {"status": "ERROR", "reason": f"base nao e um .skp existente (com o gabinete pai): {base}"}
    out, err = _out(out_skp, base)
    if err:
        return err
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base, out)
    started_ns = out.stat().st_mtime_ns
    job_dir = out.parent / f"_{out.stem}_shaker_build"
    res = run_job(su, "shaker_build", out_dir=job_dir, skp_in=out, timeout_s=timeout_s, mode=mode, script=BUILD_JOB,
                  params={"plan": plan, "save_as": "", "edits": edits})
    res["out_skp"], res["base_skp"] = str(out), str(base)
    if res.get("status") == "OK":
        saved = res["result"].get("saved") is True and out.exists() and out.stat().st_mtime_ns >= started_ns
        if not saved:
            res.update(status="FAILED", reason=f"o job disse ok mas {out} nao foi gravado")
    if res.get("status") != "OK":
        _discard_unedited(out, res)          # job interrompido/falho: a copia nao editada NAO pode parecer resultado
    return res


def inspect_shaker(skp: str | Path, *, mode: str | None = None, timeout_s: int = 180,
                   su: SketchUp | None = None) -> dict[str, Any]:
    """Reabre o .skp (uma COPIA, em outro processo) e devolve a inspecao dos gabinetes e das portas Shaker."""
    src = paths.resolve(skp)
    if src.suffix.lower() != ".skp" or not src.exists():
        return {"status": "ERROR", "reason": f"nao e um .skp existente: {src}"}
    job_dir = scratch_dir(src, "shaker_inspect")
    job_dir.mkdir(parents=True, exist_ok=True)
    copy = job_dir / f"_copy_{src.name}"
    shutil.copy2(src, copy)
    res = run_job(su or SketchUp(), "shaker_inspect", out_dir=job_dir, skp_in=copy, timeout_s=timeout_s, mode=mode,
                  script=INSPECT_JOB, params={})
    res["input_skp"] = str(src)
    return res


def _local_y(pose: dict, corner: list[float]) -> float:
    """Coordenada +y LOCAL (traseira->frente do gabinete) de um vertice de mundo, desfazendo pose (translacao + rotacao em z)."""
    th = math.radians(pose["rotation_deg"])
    return -math.sin(th) * (corner[0] - pose["x"]) + math.cos(th) * (corner[1] - pose["y"])


def verify_shaker(plan: dict, parent_plan: dict, inspected: dict, *, tol_m: float = 1e-5,
                  baseline: dict | None = None, sibling_replaced: tuple[str, ...] = ()) -> dict:
    """Compara plano Shaker (+ pai) x modelo REABERTO (`inspected` = result do job shaker_inspect).

    `sibling_replaced`: ids de frentes que OUTRAS portas Shaker do mesmo gabinete ja substituiram (2 portas no mesmo modelo)."""
    from ..plan import signature_of_plan

    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    roots = [c for c in inspected["cabinets"] if c["request_id"] == plan["parent_cabinet_request_id"]]
    check("exactly_one_parent_root", len(roots) == 1, f"{len(roots)} gabinete(s) para {plan['parent_cabinet_request_id']}")
    if len(roots) != 1:
        return {"ok": False, "checks": checks}
    root = roots[0]
    check("parent_signature_unchanged", root["signature"] == signature_of_plan(parent_plan) == plan["parent_plan_signature"])

    remaining = {p["part_id"]: p for p in root["parts"]}
    gone = {plan["replaces_part"], *sibling_replaced}
    expected_remaining = sorted(p["id"] for p in parent_plan["parts"] if p["id"] not in gone)
    check("replaced_front_is_gone", plan["replaces_part"] not in remaining, "nenhuma frente lisa sob a Shaker")
    check("other_parent_parts_untouched", sorted(remaining) == expected_remaining, f"{len(remaining)} peca(s) diretas")
    check("sibling_fronts_also_gone", all(i not in remaining for i in sibling_replaced), str(sorted(sibling_replaced)))
    for part in parent_plan["parts"]:
        got = remaining.get(part["id"])
        if got is not None:
            check(f"parent_part_corners:{part['id']}", _match(expected_corners(parent_plan, part), got["world_corners_m"], tol_m) is not None)

    same = [s for c in inspected["cabinets"] for s in c["shakers"] if s["request_id"] == plan["request_id"]]
    check("exactly_one_shaker_group", len(same) == 1, f"{len(same)} subgrupo(s) para {plan['request_id']}")
    if len(same) != 1:
        return {"ok": False, "checks": checks}
    sub = same[0]
    check("capability_attributes", sub["capability"] == CAPABILITY_ID == plan["capability"]["id"]
          and sub["capability_version"] == plan["capability"]["version"])
    check("signature_attribute", sub["signature"] == plan["signature"])
    check("parent_link_attributes", sub["parent_plan_signature"] == plan["parent_plan_signature"]
          and sub["replaces_part"] == plan["replaces_part"] and sub["parent_request_id"] == plan["parent_cabinet_request_id"])
    check("source_verified_carried_not_flipped", sub["source_verified"] is plan["origin_context"]["source_verified"],
          str(sub["source_verified"]))
    check("group_tag", sub["tag"] == "Cabinet")
    check("no_loose_geometry", sub["loose_faces"] == 0 and sub["loose_edges"] == 0)
    by_id = {p["part_id"]: p for p in sub["parts"]}
    plan_ids = [p["id"] for p in plan["parts"]]
    check("part_ids_match_plan", sorted(by_id) == sorted(plan_ids) and len(sub["parts"]) == len(plan_ids) == 5,
          f"plano={len(plan_ids)} modelo={len(sub['parts'])}")
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
        check(f"material:{part['id']}", got["material"] == part["material"] == got["attr_material"], f"{got['material']!r}")
        check(f"tag:{part['id']}", got["tag"] == f"Cabinet_{part['role']}", got["tag"])
        check(f"name:{part['id']}", got["name"] == part["id"])
    # recuo REAL medido nas coordenadas do modelo reaberto (nao o numero do plano): face visivel do painel x face frontal da moldura
    frame = [c for p in sub["parts"] if p["role"] == "frame" for c in p["world_corners_m"]]
    panel = [c for p in sub["parts"] if p["role"] == "panel" for c in p["world_corners_m"]]
    if frame and panel:
        measured = max(_local_y(plan["pose"], c) for c in frame) - max(_local_y(plan["pose"], c) for c in panel)
        wanted = plan["parameters"]["recess"]
        check("panel_recess_measured_in_model", abs(measured - wanted) <= tol_m, f"medido {measured:.7f} m, pedido {wanted:.7f} m")
        if wanted > tol_m:
            check("panel_face_behind_frame_face", measured > tol_m, f"{measured:.7f} m")
    for d in plan["definitions"]:
        names = {by_id[i]["definition"] for i in d["instances"] if i in by_id}
        shared_ok = (not d["shared"]) or by_id[d["instances"][0]]["definition_instances"] >= len(d["instances"])
        check(f"definition_sharing:{d['key']}", len(names) == 1 and shared_ok, f"{sorted(names)}")
    check("grain_not_claimed", GRAIN_SUPPORT == "NOT_SUPPORTED", "veio registrado, nao aplicado")
    if baseline is not None:
        check("non_cabinet_unchanged", baseline["non_cabinet"]["fingerprint"] == inspected["non_cabinet"]["fingerprint"]
              and baseline["non_cabinet"]["count"] == inspected["non_cabinet"]["count"], "arquitetura/outros objetos intactos")
    return {"ok": all(c["ok"] for c in checks), "checks": checks, "max_corner_error_m": worst}


__all__ = ["ShakerPlanRefused", "inspect_shaker", "materialize_shaker", "verify_shaker"]
