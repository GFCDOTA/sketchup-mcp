"""project_state.py — STATE MACHINE canônica do projeto (GAP 1 do GPT) + inventário DINÂMICO por cômodo.

Em vez de derivar estado ad-hoc espalhado, aqui há UM modelo: projeto → cômodos → assets → estado.
Cada asset tem um estado explícito (máquina de 11 fases) + a PRÓXIMA AÇÃO resolvida (GAP 2). O inventário
nasce daqui (não é lista fixa de móveis): cada cômodo lista os assets que FAZEM SENTIDO pra ele (Felipe:
"nem todo cômodo tem sofá"). stdlib only; NÃO toca :8765 nem geometria — só LÊ sinais reais.

Sinais: tools/<asset>_class.py (classe existe) · reference pack curado · cycle.learning (patch aprovado) ·
artefatos em artifacts/review/furniture/<asset>/ (render compare / gpt_verdict / vray).
"""
from __future__ import annotations

import json
from pathlib import Path

from tools.interior_studio import cycles as ic_cycles
from tools.interior_studio import reference_packs as ic_refpacks

ROOT = Path(__file__).resolve().parents[2]

# ---- as 11 fases da máquina de estado do asset (ordem = avanço) ----
STATE_ORDER = ["not_started", "references_needed", "curation_needed", "build_spec_ready", "building",
               "form_review_needed", "context_review_needed", "vray_ready", "approved", "learned", "frozen"]
STATE_LABEL = {
    "not_started": "a fazer", "references_needed": "falta referências", "curation_needed": "falta curar ⭐",
    "build_spec_ready": "pronto p/ build spec", "building": "construindo", "form_review_needed": "revisar forma (GPT)",
    "context_review_needed": "revisar contexto (GPT)", "vray_ready": "pronto p/ V-Ray", "approved": "aprovado",
    "learned": "aprendido", "frozen": "congelado",
}
# próxima AÇÃO por estado (o "next-action resolver" — 1 ação certa, não 8 botões)
NEXT_ACTION = {
    "not_started": ("definir/escopar", None), "references_needed": ("🔭 curar referências", "sec-refpack"),
    "curation_needed": ("⭐ escolher principal", "sec-refpack"), "build_spec_ready": ("🔌 Consult GPT → spec", "sec-consult"),
    "building": ("🔨 construir a classe", "sec-ren"), "form_review_needed": ("🤖 veredito de forma", None),
    "context_review_needed": ("🏠 veredito de contexto", None), "vray_ready": ("🎞️ gerar V-Ray", None),
    "approved": ("✓ congelar", None), "learned": ("🧠 aprendido", None), "frozen": ("🔒 congelado", None),
}

# ---- cômodos da planta_74 × os assets que fazem sentido neles (inventário dinâmico) ----
ASSET_META = {
    "sofa": "🛋️ Sofá", "armchair": "🪑 Poltrona", "coffee_table": "☕ Mesa de centro",
    "dining_table": "🍽️ Mesa de jantar", "rack": "📺 Rack", "bed": "🛏️ Cama",
    "wardrobe": "🚪 Guarda-roupa", "nightstand": "🗄️ Criado-mudo", "kitchen": "🍳 Cozinha (marcenaria)",
    "vanity": "🚿 Bancada/cuba",
}
ROOMS = [
    {"key": "sala", "label": "Sala / Jantar", "icon": "🛋️",
     "assets": ["sofa", "armchair", "coffee_table", "dining_table", "rack"]},
    {"key": "suite", "label": "Suíte / Quarto", "icon": "🛏️", "assets": ["bed", "wardrobe", "nightstand"]},
    {"key": "cozinha", "label": "Cozinha", "icon": "🍳", "assets": ["kitchen"]},
    {"key": "banheiro", "label": "Banheiro", "icon": "🚿", "assets": ["vanity"]},
]
# assets sem classe própria, com estado fixo (já resolvidos por outro pipeline)
FIXED_STATE = {"kitchen": "frozen"}   # GOLDEN_SAMPLE_004 (geometria congelada)


def asset_state(asset: str) -> dict:
    """Resolve o estado canônico + próxima ação de UM asset, a partir dos sinais reais."""
    if asset in FIXED_STATE:
        st = FIXED_STATE[asset]
        lbl, jump = NEXT_ACTION.get(st, ("—", None))
        return {"asset": asset, "state": st, "state_label": STATE_LABEL[st], "next": lbl, "jump": jump,
                "refs": 0, "refs_img": 0, "has_class": False}
    has_class = (ROOT / "tools" / f"{asset}_class.py").exists()
    pack = ic_refpacks.load_pack(f"{asset}_reference_pack_001")
    prefs = (pack or {}).get("references", [])
    nrefs = len(prefs)
    nimg = sum(1 for r in prefs if r.get("og_image"))
    main = sum(1 for r in prefs if r.get("status") == "main")
    cyc = next((c for c in ic_cycles.list_cycles() if c.get("asset") == asset), None)
    lr = (cyc or {}).get("learning") or {}
    spec_done = bool(lr.get("new_rules") or lr.get("patches"))
    vdir = ROOT / "artifacts/review/furniture" / asset

    def has(glb):
        return bool(list(vdir.glob(glb))) if vdir.exists() else False
    build_done = has("**/*compare*.png")
    vray_done = has("**/*vray*.png") or has("**/*_final*.png")
    # SPEC-E: estado deriva do gpt_verdict.json ESTRUTURADO {gate,verdict} — não de substring de
    # markdown (frágil: o GPT varia "Contexto"/"context"/caixa/idioma). Fallback p/ o .md enquanto
    # o asset ainda não tiver sidecar (compat retro).
    verdicts = []
    for vj in (vdir.glob("**/gpt_verdict.json") if vdir.exists() else []):
        try:
            verdicts.append(json.loads(vj.read_text("utf-8", "ignore")))
        except Exception:  # noqa: BLE001  (sidecar corrompido não derruba o estado)
            pass
    if verdicts:
        def _passed(gate_pref):
            return any(str(v.get("gate", "")).lower().startswith(gate_pref)
                       and str(v.get("verdict", "")).upper() == "PASS" for v in verdicts)
        form_pass = _passed("form")
        ctx_pass = _passed("context") or _passed("contexto")
    else:
        vf = list(vdir.glob("**/gpt_verdict.md")) if vdir.exists() else []
        vlow = (vf[0].read_text("utf-8", "ignore").lower() if vf else "")
        form_pass = ("parou de parecer caixa" in vlow) or ("forma" in vlow and "pass" in vlow)
        ctx_pass = ("contexto" in vlow and "pass" in vlow) or ("context" in vlow and "pass" in vlow)

    if vray_done:
        st = "approved"
    elif ctx_pass:
        st = "vray_ready"
    elif form_pass:
        st = "context_review_needed"
    elif build_done:
        st = "form_review_needed"
    elif spec_done:
        st = "building"
    elif main:
        st = "build_spec_ready"
    elif nrefs > 0:
        st = "curation_needed"
    elif has_class:
        st = "references_needed"   # classe pronta (programa antigo), falta entrar no método de referência
    else:
        st = "not_started"
    lbl, jump = NEXT_ACTION.get(st, ("—", None))
    return {"asset": asset, "state": st, "state_label": STATE_LABEL[st], "next": lbl, "jump": jump,
            "refs": nrefs, "refs_img": nimg, "main": main, "has_class": has_class}


def save_asset_verdict(asset: str, gate: str, verdict: str, environment: str | None = None,
                       md: str | None = None, subdir: str | None = None) -> Path:
    """SPEC-E: grava o veredito GPT de um asset como JSON ESTRUTURADO (sidecar) p/ o asset_state
    derivar estado SEM caçar substring em markdown. `gate` ∈ {form, context, vray, …}; `verdict`
    ∈ {PASS, WARN, FAIL}. Um JSON por gate (em subdir nomeado pelo gate por default). Opcionalmente
    grava também o gpt_verdict.md (espelho humano). Idempotente por (asset, gate). Devolve o path do JSON."""
    d = ROOT / "artifacts/review/furniture" / asset / (subdir or gate)
    d.mkdir(parents=True, exist_ok=True)
    payload = {"asset": asset, "gate": gate, "verdict": str(verdict).upper(), "environment": environment}
    jpath = d / "gpt_verdict.json"
    jpath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    if md is not None:
        (d / "gpt_verdict.md").write_text(md, "utf-8")
    return jpath


# ---- asset → KIND: define a POLÍTICA de pipeline do domínio (GPT: "pipeline é política do domínio, não enum global") ----
ASSET_KIND = {a: "furniture" for a in ("sofa", "armchair", "coffee_table", "dining_table",
                                       "rack", "bed", "wardrobe", "nightstand")}
ASSET_KIND.update({"kitchen": "kitchen", "vanity": "bathroom"})
PIPELINES = {   # cada KIND tem o SEU pipeline
    "furniture": ["references", "curation", "build_spec", "build", "form_review", "context_review", "vray", "learned"],
    "kitchen": ["geometry", "appliances", "skin", "golden", "learned"],
    "bathroom": ["geometry", "fixtures", "counter", "tiling", "lighting", "render", "learned"],
}
STAGE_META = {
    "references": ("📚", "Referências"), "curation": ("🎨", "Curadoria"), "build_spec": ("📐", "Build Spec"),
    "build": ("🔨", "Construção"), "form_review": ("🤖", "GPT Forma"), "context_review": ("🏠", "GPT Contexto"),
    "vray": ("🎞️", "V-Ray"), "learned": ("🧠", "Aprendido"), "geometry": ("📐", "Geometria"),
    "appliances": ("🧊", "Eletros"), "skin": ("🎨", "Pele"), "golden": ("✨", "Golden"),
    "fixtures": ("🚿", "Louças"), "counter": ("🪨", "Bancada"), "tiling": ("🧱", "Revestimento"),
    "lighting": ("💡", "Luz"), "render": ("🎞️", "Render"),
}
# quantas etapas do pipeline FURNITURE já estão DONE, por estado
_FURNITURE_DONE = {"not_started": 0, "references_needed": 0, "curation_needed": 1, "build_spec_ready": 2,
                   "building": 3, "form_review_needed": 4, "context_review_needed": 5, "vray_ready": 6,
                   "approved": 7, "learned": 8, "frozen": 8}
# estados "EM ANDAMENTO" → viram FOCO ATIVO no dash (o que estamos tratando agora)
IN_PROGRESS = {"curation_needed", "build_spec_ready", "building", "form_review_needed",
               "context_review_needed", "vray_ready"}


def env_of(asset: str) -> dict | None:
    """Ambiente (cômodo) ao qual o asset pertence — AssetRegistry."""
    return next((r for r in ROOMS if asset in r["assets"]), None)


# ---- SPEC-B: inventário DINÂMICO a partir do furniture_program aprovado pelo Arquiteto ----
# O Arquiteto fala uma linguagem mais rica ("mesa_centro", "tv_console", "sofa_2_places"); o
# modelo canônico tem 10 assets. Este mapa reconcilia asset→canônico (canonical → keywords).
ASSET_SYNONYMS = {
    "sofa": ["sofa", "sofá"],
    "armchair": ["poltrona", "armchair", "accent_chair", "cadeira_de_leitura", "leitura"],
    "coffee_table": ["mesa_centro", "mesa_de_centro", "coffee", "centro"],
    "dining_table": ["mesa_jantar", "mesa_de_jantar", "dining", "jantar"],
    "rack": ["rack", "tv_console", "console", "tv", "estante_tv", "painel_tv", "home_theater"],
    "bed": ["cama", "bed"],
    "wardrobe": ["guarda_roupa", "wardrobe", "closet", "armario_roupa", "roupeiro"],
    "nightstand": ["criado", "nightstand", "cabeceira"],
}
# cômodos monolíticos no modelo canônico: QUALQUER item do programa colapsa no asset único
SINGLE_ASSET_ROOM = {"cozinha": "kitchen", "banheiro": "vanity"}


def canonical_asset(name: str, room_key: str | None = None) -> str | None:
    """asset (linguagem do Arquiteto) → asset canônico do modelo, ou None se não houver classe.
    Cozinha/banheiro colapsam no asset único do cômodo (kitchen/vanity)."""
    if room_key in SINGLE_ASSET_ROOM:
        return SINGLE_ASSET_ROOM[room_key]
    n = name.strip().lower().replace(" ", "_").replace("-", "_")
    if n in ASSET_META:
        return n
    for canon, kws in ASSET_SYNONYMS.items():
        if any(k in n for k in kws):
            return canon
    return None


def room_asset_keys(room_key: str, default_assets: list) -> tuple[list, str]:
    """Os assets do cômodo: o furniture_program APROVADO (mapeado p/ canônico, deduped, na ordem
    do programa) se existir; senão o ROOMS hardcoded. Devolve (keys, source). Item sem canônico
    entra 'loose' (estado not_started) — o inventário reflete a escolha do Arquiteto."""
    try:
        from tools.interior_studio import proposals
        prog = proposals.approved_program(room_key)
    except Exception:  # noqa: BLE001
        prog = None
    if not prog:
        return list(default_assets), "default"
    seen, out = set(), []
    for it in prog.get("items", []):
        nm = str(it.get("asset", "")).strip().lower()
        if not nm:
            continue
        key = canonical_asset(nm, room_key) or nm
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return (out, "program") if out else (list(default_assets), "default")


def pipeline_for(asset: str) -> list:
    """PipelineResolver: o pipeline (política do domínio) do asset, com status derivado do estado."""
    kind = ASSET_KIND.get(asset, "furniture")
    stages = PIPELINES.get(kind, PIPELINES["furniture"])
    st = asset_state(asset)["state"]
    if kind == "furniture":
        done = _FURNITURE_DONE.get(st, 0)
    elif st == "frozen":
        done = len(stages)
    else:
        done = 0
    closed = st in ("frozen", "approved", "learned")
    out = []
    for i, sg in enumerate(stages):
        ic, lbl = STAGE_META.get(sg, ("•", sg))
        status = "done" if i < done else ("doing" if (i == done and not closed) else "pending")
        out.append({"icon": ic, "label": lbl, "status": status})
    return out


def active_focuses() -> list:
    """Os fluxos VIVOS (assets em andamento) = o que estamos tratando AGORA. Suporta MÚLTIPLOS focos
    (resolve 'tenho 2-3 sessões abertas'). Derivado do estado — o sistema mostra os fluxos vivos."""
    reason = {"curation_needed": "referências baixadas, falta escolher a principal ⭐",
              "build_spec_ready": "principal escolhida, pronto p/ build spec",
              "building": "spec aprovada, construindo a classe",
              "form_review_needed": "classe construída, aguardando veredito de forma",
              "context_review_needed": "forma OK, aguardando veredito de contexto",
              "vray_ready": "forma + contexto aprovados pelo GPT"}
    out = []
    for r in ROOMS:
        for a in r["assets"]:
            stt = asset_state(a)
            if stt["state"] in IN_PROGRESS:
                out.append({"environment": r["key"], "env_label": r["label"], "env_icon": r["icon"],
                            "asset": a, "label": ASSET_META.get(a, a), "state": stt["state"],
                            "state_label": stt["state_label"], "next": stt["next"], "jump": stt["jump"],
                            "reason": reason.get(stt["state"], ""), "pipeline": pipeline_for(a)})
    return out


def project_state() -> dict:
    """O modelo inteiro: projeto → cômodos → assets (com estado + próxima ação). É a fonte do inventário."""
    rooms = []
    for r in ROOMS:
        keys, source = room_asset_keys(r["key"], r["assets"])   # SPEC-B: programa aprovado sobrepõe ROOMS
        assets = []
        for a in keys:
            stt = asset_state(a)
            stt["label"] = ASSET_META.get(a, a)
            assets.append(stt)
        done = sum(1 for a in assets if a["state"] in ("approved", "learned", "frozen"))
        rooms.append({"key": r["key"], "label": r["label"], "icon": r["icon"],
                      "assets": assets, "done": done, "total": len(assets), "assets_source": source})
    return {"project": "planta_74", "rooms": rooms}
