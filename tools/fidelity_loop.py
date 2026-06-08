#!/usr/bin/env python3
"""Fidelity loop — o ALVO do GPT como âncora + o ciclo medível (lado VALIDAR).

Fase PRODUTO: "ficar fiel à imagem do GPT" só tem sentido se houver (1) um ALVO — a
imagem que o GPT definiu como referência — e (2) um registro do ciclo FAIL→PASS por
objeto (o KPI Learning-Cycle-Time). Este módulo é o MÚSCULO que:
  - guarda o alvo (register_ref),
  - monta o pacote `alvo × render` pro GPT julgar (build_validation_package),
  - audita o veredito e calcula o KPI (record_verdict / kpi),
devolvendo só JSON compacto (contrato brain_muscle.md: verboso no disco, não no contexto).

NÃO julga: o veredito visual é do GPT via Chrome (negative_dogfood provou que visão
local alucina; skill gpt-review-gate diz que o agente NUNCA autojulga). Determinístico.

CLI (exit-code = status; 0 ok, 1 erro):
  python tools/fidelity_loop.py register-ref <id> <imagem> --room sala --style industrial
  python tools/fidelity_loop.py package      <id> <render.png> [--attempt N]
  python tools/fidelity_loop.py record       <id> <PASS|WARN|FAIL> [--attempt N] [--notes ..]
  python tools/fidelity_loop.py kpi          [--object <id>]
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = REPO_ROOT / ".ai_bridge" / "fidelity"   # alvo + ledger (commitado, precioso)
DEFAULT_PKG_ROOT = REPO_ROOT / "runs" / "fidelity"      # montagens p/ GPT (scratch, gitignored)
VERDICTS = {"PASS", "WARN", "FAIL"}

# Eixos fixos que o GPT compara alvo×render (curto e estável; base do checklist).
FIDELITY_AXES = ("materiais", "iluminacao", "proporcao_escala", "estilo_coerente",
                 "realismo_premium", "fidelidade_ao_alvo")


def _slug(s) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in str(s)).strip("_") or "obj"


def _ledger_rows(base: Path) -> list:
    p = Path(base) / "ledger.jsonl"
    rows = []
    if p.is_file():
        for ln in p.read_text("utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if ln:
                try:
                    rows.append(json.loads(ln))
                except ValueError:
                    pass
    return rows


def _attempts_for(object_id, base: Path) -> list:
    return [r.get("attempt", 0) for r in _ledger_rows(base) if r.get("object_id") == object_id]


def register_ref(object_id, image_path, *, room="", style="", source="gpt",
                 design_intent=None, base=None) -> dict:
    """Guarda a imagem-ALVO (dada pelo GPT) + metadados como âncora de fidelidade."""
    base = Path(base) if base else DEFAULT_BASE
    img = Path(image_path)
    if not img.is_file():
        raise FileNotFoundError(f"imagem de referência não existe: {img}")
    oid = _slug(object_id)
    d = base / "refs" / oid
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"target{img.suffix.lower() or '.png'}"
    shutil.copyfile(img, target)
    meta = {"object_id": object_id, "room": room, "style": style, "source": source,
            "target_image": str(target.relative_to(base)).replace("\\", "/"),
            "design_intent": design_intent, "created_at": time.time()}
    (d / "ref.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
    return {"object_id": object_id, "status": "REF_REGISTERED",
            "ref_dir": str(d).replace("\\", "/"), "target": str(target).replace("\\", "/")}


def _compose_pair(left_png, right_png, out_png, *, gap=16, bg=(245, 245, 245)) -> tuple:
    """Monta ESQUERDA|DIREITA com a mesma altura. Sem texto (evita dependência de fonte);
    o ask_gpt.md explica qual lado é o alvo."""
    from PIL import Image
    a = Image.open(left_png).convert("RGB")
    b = Image.open(right_png).convert("RGB")
    h = min(a.height, b.height) or 1

    def _scale(im):
        w = max(1, round(im.width * h / im.height))
        return im.resize((w, h))

    a, b = _scale(a), _scale(b)
    out = Image.new("RGB", (a.width + gap + b.width, h), bg)
    out.paste(a, (0, 0))
    out.paste(b, (a.width + gap, 0))
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    out.save(out_png)
    return out.size


def _verdict_schema() -> dict:
    return {"format": "text",
            "fields": ["<eixo>: PASS|WARN|FAIL — evidência",
                       "VEREDITO_GLOBAL: PASS|WARN|FAIL", "TOP_3_PROBLEMAS", "PROXIMA_ACAO"],
            "axes": list(FIDELITY_AXES)}


def _ask_md(object_id, meta, attempt) -> str:
    axes = "\n".join(f"- {a}: PASS|WARN|FAIL — evidência" for a in FIDELITY_AXES)
    return (
        f"# Validação de fidelidade — {object_id} (tentativa {attempt})\n\n"
        f"Cômodo: {meta.get('room', '?')} · Estilo: {meta.get('style', '?')}\n\n"
        f"`alvo_x_render.png`: **ESQUERDA = ALVO (referência do GPT)** · "
        f"**DIREITA = RENDER do .skp atual**.\n\n"
        f"Você é o JUIZ visual (o agente não autojulga). Compare o RENDER com o ALVO, por eixo:\n\n"
        f"{axes}\n\n"
        f"Depois: **VEREDITO_GLOBAL: PASS|WARN|FAIL** · TOP_3_PROBLEMAS · "
        f"PROXIMA_ACAO (1 ajuste concreto). Seja crítico: aponte o que está longe do alvo.\n"
    )


def build_validation_package(object_id, render_path, *, attempt=None,
                             base=None, pkg_root=None) -> dict:
    """Monta o pacote que o GPT vai julgar: montagem alvo×render + pergunta + schema.
    Verboso vai pro pacote (scratch), não pro contexto. Devolve JSON compacto."""
    base = Path(base) if base else DEFAULT_BASE
    pkg_root = Path(pkg_root) if pkg_root else DEFAULT_PKG_ROOT
    oid = _slug(object_id)
    ref_meta_p = base / "refs" / oid / "ref.json"
    if not ref_meta_p.is_file():
        return {"object_id": object_id, "status": "NO_REF",
                "error": f"sem alvo registrado p/ {object_id!r} — rode register-ref antes"}
    render = Path(render_path)
    if not render.is_file():
        return {"object_id": object_id, "status": "NO_RENDER", "error": f"render não existe: {render}"}
    meta = json.loads(ref_meta_p.read_text("utf-8"))
    target = base / meta["target_image"]
    if attempt is None:
        attempt = max(_attempts_for(object_id, base), default=0) + 1
    pkg = pkg_root / oid / f"attempt_{attempt:03d}"
    montage = pkg / "alvo_x_render.png"
    try:
        _compose_pair(target, render, montage)
    except Exception as e:  # PIL/arquivo ruim — não derruba o músculo
        return {"object_id": object_id, "status": "COMPOSE_FAILED",
                "error": f"{type(e).__name__}: {e}"}
    (pkg / "ask_gpt.md").write_text(_ask_md(object_id, meta, attempt), "utf-8")
    (pkg / "verdict_schema.json").write_text(
        json.dumps(_verdict_schema(), ensure_ascii=False, indent=2), "utf-8")
    return {"object_id": object_id, "attempt": attempt, "status": "READY_FOR_GPT",
            "montage": str(montage).replace("\\", "/"),
            "package_dir": str(pkg).replace("\\", "/"),
            "note": "mostrar alvo_x_render.png + ask_gpt.md ao GPT via Chrome; veredito -> record"}


def record_verdict(object_id, verdict, *, attempt=None, notes="", base=None) -> dict:
    """Audita o veredito do GPT (PASS/WARN/FAIL) no ledger — base do KPI."""
    base = Path(base) if base else DEFAULT_BASE
    v = str(verdict).upper()
    if v not in VERDICTS:
        raise ValueError(f"verdict {verdict!r} inválido; use {sorted(VERDICTS)}")
    if attempt is None:
        attempt = max(_attempts_for(object_id, base), default=0) or 1
    entry = {"object_id": object_id, "attempt": attempt, "verdict": v,
             "notes": notes, "ts": time.time()}
    ledger = base / "ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"object_id": object_id, "attempt": attempt, "verdict": v, "status": "RECORDED"}


def kpi(object_id=None, base=None) -> dict:
    """KPI Learning-Cycle-Time: por objeto, tempo/tentativas do 1º FAIL ao 1º PASS."""
    base = Path(base) if base else DEFAULT_BASE
    rows = sorted(_ledger_rows(base), key=lambda r: r.get("ts", 0))
    if object_id:
        rows = [r for r in rows if r.get("object_id") == object_id]
    by: dict = {}
    for r in rows:
        by.setdefault(r.get("object_id"), []).append(r)
    objs = {}
    for oid, rs in by.items():
        first_fail = next((r for r in rs if r.get("verdict") == "FAIL"), None)
        first_pass = next((r for r in rs if r.get("verdict") == "PASS"), None)
        cycle = None
        if first_pass:
            start = first_fail["ts"] if first_fail and first_fail["ts"] <= first_pass["ts"] else rs[0]["ts"]
            cycle = round(first_pass["ts"] - start, 1)
        objs[oid] = {"attempts": len(rs), "reached_pass": bool(first_pass),
                     "n_fail": sum(1 for r in rs if r.get("verdict") == "FAIL"),
                     "cycle_time_s": cycle, "last_verdict": rs[-1].get("verdict")}
    passed = [o for o in objs.values() if o["reached_pass"]]
    cycles = [o["cycle_time_s"] for o in passed if o["cycle_time_s"] is not None]
    agg = {"objects": len(objs), "reached_pass": len(passed),
           "pass_rate": round(len(passed) / len(objs), 2) if objs else 0.0,
           "avg_cycle_time_s": round(sum(cycles) / len(cycles), 1) if cycles else None}
    return {"status": "OK", "kpi": "learning_cycle_time", "aggregate": agg, "objects": objs}


_OK_STATUS = {"REF_REGISTERED", "READY_FOR_GPT", "RECORDED", "OK"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fidelity loop — alvo do GPT + ciclo medível")
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("register-ref"); p.add_argument("object_id"); p.add_argument("image")
    p.add_argument("--room", default=""); p.add_argument("--style", default="")
    p = sub.add_parser("package"); p.add_argument("object_id"); p.add_argument("render")
    p.add_argument("--attempt", type=int, default=None)
    p = sub.add_parser("record"); p.add_argument("object_id"); p.add_argument("verdict")
    p.add_argument("--attempt", type=int, default=None); p.add_argument("--notes", default="")
    p = sub.add_parser("kpi"); p.add_argument("--object", default=None)
    a = ap.parse_args(argv)

    if a.verb == "register-ref":
        out = register_ref(a.object_id, a.image, room=a.room, style=a.style)
    elif a.verb == "package":
        out = build_validation_package(a.object_id, a.render, attempt=a.attempt)
    elif a.verb == "record":
        out = record_verdict(a.object_id, a.verdict, attempt=a.attempt, notes=a.notes)
    else:
        out = kpi(object_id=a.object)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("status") in _OK_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
