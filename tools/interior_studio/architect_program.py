"""architect_program.py — o ARQUITETO (LLM local) PROPÕE o programa de mobiliário de um cômodo.

GPT validou (ARCHITECT_AGENT_DESIGN_GPT.md): substitui o ROOMS hardcodado por uma PROPOSAL do Arquiteto —
recebe dims reais da planta + estilo DNA + o que já existe → devolve um furniture_program {items: asset/
priority/reason}. Arquiteto = deepseek-r1:14b (raciocínio). A saída é PROPOSAL pra Felipe aprovar (nada
entra direto no estado canônico). stdlib only; LÊ sinais reais; não muta nada.
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

from tools.interior_studio import project_state as ps

ROOT = Path(__file__).resolve().parents[2]
PT_TO_M = 0.0259   # escala travada da planta_74 (ver project_planta74_scale_locked)
CONSENSUS = ROOT / "artifacts/review/planta_74/regen_candidate_20260531/final/consensus_regenerated.json"
FELIPE_DNA = ROOT / ".claude/memory/felipe_style_dna.md"
OLLAMA = "http://127.0.0.1:11434/api/generate"
MODELS = {"deepseek": "deepseek-r1:14b", "qwen": "qwen2.5-coder:14b"}

# nome do cômodo no consensus → chave do project_state (cômodos repetidos colapsam na mesma chave)
ROOM_KEY = {"SALA DE JANTAR | SALA DE ESTAR": "sala", "SUITE 01": "suite", "SUITE 02": "suite",
            "COZINHA": "cozinha", "BANHO 01": "banheiro", "BANHO 02": "banheiro", "LAVABO": "banheiro"}


def rooms() -> list[dict]:
    """Cômodos da planta_74 com área e dims em metros (derivadas do polígono × PT_TO_M)."""
    if not CONSENSUS.exists():
        return []
    d = json.loads(CONSENSUS.read_text("utf-8"))
    out = []
    for r in d.get("rooms", []):
        poly = r.get("polygon_pts") or []
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        w = (max(xs) - min(xs)) * PT_TO_M if xs else 0.0
        dep = (max(ys) - min(ys)) * PT_TO_M if ys else 0.0
        area = (r.get("area_pts2") or 0) * PT_TO_M * PT_TO_M
        out.append({"id": r.get("id"), "name": r.get("name"), "area_m2": round(area, 1),
                    "w_m": round(w, 1), "d_m": round(dep, 1), "key": ROOM_KEY.get(r.get("name", ""))})
    return out


def room_context(room_id: str) -> dict | None:
    rm = next((r for r in rooms() if r["id"] == room_id or r["name"] == room_id), None)
    if not rm:
        return None
    dna = FELIPE_DNA.read_text("utf-8", "ignore")[:1200] if FELIPE_DNA.exists() else ""
    existing = []
    if rm["key"]:
        room = next((x for x in ps.ROOMS if x["key"] == rm["key"]), None)
        for a in (room or {}).get("assets", []):
            st = ps.asset_state(a)
            if st["state"] != "not_started":
                existing.append(f'{ps.ASSET_META.get(a, a)} ({st["state_label"]})')
    return {"room": rm, "dna": dna, "existing": existing}


def _ollama(model: str, prompt: str, timeout: int = 240) -> str:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.3, "num_predict": 2400}}).encode("utf-8")
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8")).get("response", "")


def _extract_json(txt: str) -> dict | None:
    """deepseek-r1 cospe <think>…</think> antes do JSON; tira isso e pega o bloco {…} com items."""
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S)
    blocks = re.findall(r"\{(?:[^{}]|\{[^{}]*\})*\"items\"(?:[^{}]|\{[^{}]*\})*\}", txt, flags=re.S)
    cand = blocks[-1] if blocks else None
    if not cand:
        i, j = txt.find("{"), txt.rfind("}")
        cand = txt[i:j + 1] if i >= 0 and j > i else None
    try:
        return json.loads(cand) if cand else None
    except Exception:  # noqa: BLE001
        return None


PROMPT = """Você é o ARQUITETO de interiores de um apê compacto premium. Proponha o PROGRAMA DE MOBILIÁRIO do cômodo: QUE móveis devem existir nele, respeitando o estilo e o espaço REAL.

COMODO: {name}
AREA: {area} m2  (aprox {w} x {d} m)
ESTILO (DNA do Felipe, e RESTRICAO nao sugestao): {dna}
JA EXISTE no comodo: {existing}
REGRAS: ape compacto, nao bloquear circulacao; so o que CABE e faz sentido nessa area; gosto do Felipe = industrial boutique premium, black/wood/gold. No maximo 6 itens.

Responda APENAS um JSON valido, nada fora dele:
{{"environment":"{key}","items":[{{"asset":"nome_curto_minusculo","priority":"core","reason":"por que, 1 linha curta"}}]}}
priority deve ser core, secundario ou opcional."""


def propose_program(room_id: str, model: str = "deepseek") -> dict:
    ctx = room_context(room_id)
    if not ctx:
        return {"ok": False, "error": f"comodo {room_id} nao encontrado"}
    rm = ctx["room"]
    mdl = MODELS.get(model, model)
    prompt = PROMPT.format(name=rm["name"], area=rm["area_m2"], w=rm["w_m"], d=rm["d_m"],
                           dna=(ctx["dna"][:900] or "(sem DNA)"),
                           existing=", ".join(ctx["existing"]) or "(nada ainda)",
                           key=rm["key"] or rm["id"])
    raw = _ollama(mdl, prompt)
    prog = _extract_json(raw)
    used = mdl
    if (not prog or "items" not in prog) and model == "deepseek":
        # GPT: "DeepSeek pensa, Qwen formata" — deepseek-r1 às vezes cospe JSON sujo; qwen reformata o RACIOCÍNIO dele
        clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
        fix = (f'Converta o texto abaixo em UM JSON valido, nada fora dele, no formato '
               f'{{"environment":"{rm["key"] or rm["id"]}","items":[{{"asset":"nome_minusculo","priority":"core",'
               f'"reason":"1 linha"}}]}} (priority=core|secundario|opcional, max 6 itens):\n\n{clean[:1500]}')
        raw2 = _ollama(MODELS["qwen"], fix, timeout=120)
        prog = _extract_json(raw2)
        used = f'{mdl} + qwen(format)'
    if not prog or "items" not in prog:
        return {"ok": False, "error": "Arquiteto nao devolveu JSON valido", "raw": raw[:500], "model": mdl}
    return {"ok": True, "model": used, "room": rm, "program": prog, "existing": ctx["existing"]}


def propose_and_save(room_id: str, model: str = "deepseek") -> dict:
    """Gera o programa e salva como PROPOSAL pending (pro Felipe aprovar no dash). id por room_id (único)."""
    from tools.interior_studio import proposals
    r = propose_program(room_id, model)
    if not r["ok"]:
        return r
    rm = r["room"]
    prop = {"id": f"furniture_program_{rm['id']}", "type": "furniture_program",
            "source_worker": f"Arquiteto · {r['model']}", "environment": rm["key"] or rm["id"],
            "room_id": rm["id"], "room_name": rm["name"], "area_m2": rm["area_m2"],
            "items": r["program"].get("items", []), "existing": r["existing"]}
    proposals.save(prop)
    return {"ok": True, "proposal": prop}


if __name__ == "__main__":
    import sys
    rid = sys.argv[1] if len(sys.argv) > 1 else "r002"
    mdl = sys.argv[2] if len(sys.argv) > 2 else "deepseek"
    save = "--save" in sys.argv
    out = propose_and_save(rid, mdl) if save else propose_program(rid, mdl)
    print(json.dumps(out, ensure_ascii=False, indent=2))
