"""architect_program.py — o ARQUITETO (LLM local) PROPÕE o programa de mobiliário de um cômodo.

GPT validou (ARCHITECT_AGENT_DESIGN_GPT.md): substitui o ROOMS hardcodado por uma PROPOSAL do Arquiteto —
recebe dims reais da planta + estilo DNA + o que já existe → devolve um furniture_program {items: asset/
priority/reason}. Arquiteto = deepseek-r1:14b (raciocínio). A saída é PROPOSAL pra Felipe aprovar (nada
entra direto no estado canônico). stdlib only; LÊ sinais reais; não muta nada.
"""
from __future__ import annotations

import json
import os
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

# chave pt do project_state → room_type EN do reference_db.retrieve()/references/tokens.
ROOM_TYPE_EN = {"cozinha": "kitchen", "sala": "living", "suite": "bedroom",
                "banheiro": "bathroom"}
# estilo default do DNA do Felipe (industrial boutique preto+madeira+dourado) para o retrieve.
FELIPE_STYLE = "black_wood_gold"
# Backend do RAG na geração. DEFAULT 'faceted' (comportamento de hoje, seguro).
# 'embed' liga a fusão RRF do recall semântico -> muda os tokens injetados ->
# muda o .skp: só o Felipe aprova (veredito visual GPT) e exige `reference_db
# reindex --rebuild` (re-embeda com os prefixos nomic). Gate = env RAG_BACKEND.
_RAG_BACKEND = os.environ.get("RAG_BACKEND", "faceted")

# --- SPEC-C: gate deterministico do programa (o LLM local erra: suite sem cama, cozinha
#     com item de banheiro). O LLM PROPOE; este gate GARANTE o invariante (CORE presente,
#     0 cross-comodo). Espelha a filosofia do projeto: gate deterministico = verdade, LLM = consultivo. ---
# CORE obrigatorio por tipo de comodo: (asset_canonico, [keywords p/ detectar no nome], label injetado)
CORE_BY_ROOM = {
    "sala":     [("sofa", ["sofa", "sofá"], "sofa")],
    "suite":    [("bed", ["cama", "bed"], "cama")],
    "cozinha":  [("counter", ["bancada", "counter"], "bancada"),
                 ("cooktop", ["cooktop", "fogão", "fogao", "stove", "cooktop"], "cooktop"),
                 ("fridge", ["geladeira", "fridge", "refrigerador"], "geladeira")],
    "banheiro": [("toilet", ["vaso", "privada", "sanitário", "sanitario", "toilet"], "vaso"),
                 ("sink", ["cuba", "pia", "lavatório", "lavatorio", "sink"], "cuba")],
}
# tokens que pertencem EXCLUSIVAMENTE a OUTRO tipo de comodo (presenca => remover por cross-comodo).
# NUNCA conter um token que seja legitimo no proprio comodo (ex.: cozinha nao proibe 'bancada').
ROOM_EXCLUSIVE = {
    "sala":     ["cama", "bed", "cooktop", "fogão", "fogao", "geladeira", "fridge", "vaso",
                 "privada", "chuveiro", "shower", "guarda-roupa", "wardrobe", "criado-mudo"],
    "suite":    ["sofa", "sofá", "cooktop", "fogão", "fogao", "geladeira", "fridge", "vaso",
                 "privada", "chuveiro", "shower", "cuba", "cooktop", "rack"],
    "cozinha":  ["cama", "bed", "sofa", "sofá", "vaso", "privada", "chuveiro", "shower",
                 "guarda-roupa", "wardrobe", "criado-mudo", "criado"],
    "banheiro": ["cama", "bed", "sofa", "sofá", "cooktop", "fogão", "fogao", "geladeira",
                 "fridge", "guarda-roupa", "wardrobe", "rack"],
}
ROOM_TOKENS = ["banheiro", "banho", "cozinha", "sala", "suite", "quarto", "lavabo"]


def _strip_room_prefix(name: str, room_key: str) -> str:
    """Tira um prefixo '<comodo>_' do nome (bug real: Arquiteto prefixou itens da cozinha com
    'banheiro_'). Salva o asset bom ('banheiro_cooktop' -> 'cooktop'); o gate de exclusao decide depois."""
    for tok in ROOM_TOKENS:
        for sep in ("_", "-", " "):
            if name.startswith(tok + sep):
                return name[len(tok) + 1:]
    return name


def normalize_program(items: list[dict], room_key: str) -> tuple[list[dict], dict]:
    """LLM propoe, gate garante: remove item exclusivo de outro comodo, injeta CORE faltante.
    Deterministico, idempotente. Devolve (items_normalizados, report{removed,injected})."""
    core = CORE_BY_ROOM.get(room_key, [])
    excl = ROOM_EXCLUSIVE.get(room_key, [])
    kept, removed, seen = [], [], set()
    for it in items or []:
        raw = str(it.get("asset", "")).strip().lower()
        if not raw:
            continue
        name = _strip_room_prefix(raw, room_key)
        if any(tok in name for tok in excl):                     # exclusivo de outro comodo
            removed.append({"asset": raw, "why": "cross-cômodo"})
            continue
        kept.append({**it, "asset": name})
        for canon, kws, _ in core:                               # marca CORE ja satisfeito
            if any(k in name for k in kws):
                seen.add(canon)
    injected = [{"asset": label, "priority": "core",
                 "reason": "CORE obrigatório do cômodo (injetado pelo gate determinístico)"}
                for canon, _, label in core if canon not in seen]
    return injected + kept, {"removed": removed, "injected": [i["asset"] for i in injected]}


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


def _retrieve_bundle(room_key: str | None) -> dict | None:
    """FP-035: recupera o DesignSpecBundle do cômodo/estilo do Felipe. RETROCOMPAT:
    qualquer erro/import ausente devolve None -> o gerador cai no DNA cru."""
    room_type = ROOM_TYPE_EN.get(room_key or "")
    if not room_type:
        return None
    try:
        from tools import reference_db as rdb
        bundle = rdb.retrieve(room_type, FELIPE_STYLE, backend=_RAG_BACKEND)
        return bundle if bundle.get("tokens") else None
    except Exception:  # noqa: BLE001 — retrieve nunca deve quebrar o gerador
        return None


def guard_bundle_freshness(bundle: dict | None) -> dict | None:
    """FP-037: freshness guard ANTES do arquiteto consumir o contexto RAG.

    Se o bundle traz retrieved_chunks (backend embed), passa-os pelo
    rag_freshness.freshness_guard: chunk inativo / de corpus_version antigo é
    REJEITADO; chunk cuja fonte ficou mais nova que o índice é marcado STALE e
    NÃO é usado silenciosamente (registra em bundle['freshness']). Contexto stale
    degrada — nunca entra calado no prompt.

    RETROCOMPAT: sem bundle, ou sem retrieved_chunks (faceted puro), é NO-OP —
    devolve o bundle intacto. Qualquer erro/infra ausente -> devolve o bundle como
    veio (o guard nunca derruba o gerador).
    """
    if not bundle:
        return bundle
    chunks = bundle.get("retrieved_chunks") or []
    if not chunks:
        return bundle
    try:
        from tools import rag_freshness as rf
        con = rf.connect()
        try:
            candidates = [{"chunk_id": c.get("chunk_id"),
                           "document_id": _doc_id_of_chunk(con, c.get("chunk_id"))}
                          for c in chunks]
            res = rf.freshness_guard(con, candidates)
        finally:
            con.close()
        fresh_ids = {c["chunk_id"] for c in res.fresh_chunks}
        kept = [c for c in chunks if c.get("chunk_id") in fresh_ids]
        bundle = {**bundle, "retrieved_chunks": kept, "freshness": {
            "kept": len(kept), "rejected": res.rejected, "stale": res.stale,
            "corpus_version": res.corpus_version,
        }}
        if res.rejected or res.stale:
            # degradação honesta: avisa o consumidor que contexto foi descartado
            note = (f"freshness guard: {len(res.rejected)} chunk(s) rejeitado(s), "
                    f"{len(res.stale)} stale (fonte mais nova que o índice — "
                    f"reindex pendente). Contexto stale NÃO usado.")
            bundle["notes"] = list(bundle.get("notes") or []) + [note]
        return bundle
    except Exception:  # noqa: BLE001 — guard nunca quebra o gerador
        return bundle


def _doc_id_of_chunk(con, chunk_id: str | None) -> str | None:
    if not chunk_id:
        return None
    row = con.execute("SELECT document_id FROM chunk WHERE chunk_id=?",
                      (chunk_id,)).fetchone()
    return row["document_id"] if row else None


def render_bundle_for_prompt(bundle: dict | None, max_tokens: int = 6) -> str:
    """Bloco estruturado (não texto cru truncado) do bundle recuperado pro prompt:
    tokens canônicos + anti-patterns + layout_hints. Vazio se sem bundle."""
    if not bundle or not bundle.get("tokens"):
        return ""
    lines = [f"TOKENS DE MARCENARIA RECUPERADOS (curadoria do Felipe, "
             f"confidence={bundle.get('confidence')}):"]
    for t in bundle["tokens"][:max_tokens]:
        kinds = ", ".join(t.get("builder_kinds", []))
        lines.append(f"- {t['name']}" + (f" (builder: {kinds})" if kinds else ""))
    antis = bundle.get("anti_patterns") or []
    if antis:
        lines.append("ANTI-PADRÕES (NÃO fazer): " + " | ".join(a[:120] for a in antis[:4]))
    hints = bundle.get("layout_hints") or []
    if hints:
        lines.append("LAYOUT: " + " | ".join(h[:140] for h in hints[:3]))
    return "\n".join(lines)


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
    # FP-035: injeta o bundle estruturado recuperado (laço curadoria→furnish→.skp).
    # RETROCOMPAT: sem bundle -> design_spec vazio; o prompt cai no dna cru.
    # FP-037: passa o bundle pelo freshness guard ANTES de virar contexto do prompt
    # (rejeita chunk inativo/stale; contexto stale não entra calado). No-op no
    # faceted puro (sem retrieved_chunks).
    bundle = guard_bundle_freshness(_retrieve_bundle(rm["key"]))
    return {"room": rm, "dna": dna, "existing": existing,
            "design_bundle": bundle,
            "design_spec": render_bundle_for_prompt(bundle)}


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
{design_spec}
JA EXISTE no comodo: {existing}
{core_hint}
REGRAS: ape compacto, nao bloquear circulacao; so o que CABE e faz sentido nessa area; gosto do Felipe = industrial boutique premium, black/wood/gold. No maximo 6 itens. NAO inclua movel de OUTRO comodo (ex.: nada de cama/sofa na cozinha; nada de cooktop/geladeira no quarto; nada de vaso/cuba fora do banheiro). Use o nome do PROPRIO comodo, SEM prefixo de outro comodo (errado: "banheiro_cooktop"; certo: "cooktop").

Responda APENAS um JSON valido, nada fora dele:
{{"environment":"{key}","items":[{{"asset":"nome_curto_minusculo","priority":"core","reason":"por que, 1 linha curta"}}]}}
priority deve ser core, secundario ou opcional."""


def propose_program(room_id: str, model: str = "deepseek") -> dict:
    ctx = room_context(room_id)
    if not ctx:
        return {"ok": False, "error": f"comodo {room_id} nao encontrado"}
    rm = ctx["room"]
    mdl = MODELS.get(model, model)
    rkey = rm["key"] or rm["id"]
    core = CORE_BY_ROOM.get(rkey, [])
    core_hint = ("ITENS CORE OBRIGATORIOS deste comodo (TEM que aparecer): "
                 + ", ".join(label for _, _, label in core) + ".") if core else ""
    # FP-035: bundle estruturado recuperado > DNA cru truncado. Se veio bundle,
    # o dna cru encolhe (só contexto de fundo); o design_spec vira a autoridade.
    design_spec = ctx.get("design_spec") or ""
    dna_len = 400 if design_spec else 900
    prompt = PROMPT.format(name=rm["name"], area=rm["area_m2"], w=rm["w_m"], d=rm["d_m"],
                           dna=(ctx["dna"][:dna_len] or "(sem DNA)"),
                           design_spec=design_spec,
                           existing=", ".join(ctx["existing"]) or "(nada ainda)",
                           key=rkey, core_hint=core_hint)
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
    # SPEC-C: gate deterministico — garante CORE presente + 0 cross-comodo (o LLM erra)
    items, gate = normalize_program(prog.get("items", []), rkey)
    prog["items"] = items
    prog["environment"] = rkey
    return {"ok": True, "model": used, "room": rm, "program": prog,
            "existing": ctx["existing"], "gate": gate}


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
            "items": r["program"].get("items", []), "existing": r["existing"],
            "gate": r.get("gate", {})}   # SPEC-C: o que o gate determinístico corrigiu (transparência)
    proposals.save(prop)
    return {"ok": True, "proposal": prop}


if __name__ == "__main__":
    import sys
    rid = sys.argv[1] if len(sys.argv) > 1 else "r002"
    mdl = sys.argv[2] if len(sys.argv) > 2 else "deepseek"
    save = "--save" in sys.argv
    out = propose_and_save(rid, mdl) if save else propose_program(rid, mdl)
    print(json.dumps(out, ensure_ascii=False, indent=2))
