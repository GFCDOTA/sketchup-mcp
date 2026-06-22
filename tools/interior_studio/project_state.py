"""project_state.py — STATE MACHINE canônica do projeto (GAP 1 do GPT) + inventário DINÂMICO por cômodo.

Em vez de derivar estado ad-hoc espalhado, aqui há UM modelo: projeto → cômodos → assets → estado.
Cada asset tem um estado explícito (máquina de 11 fases) + a PRÓXIMA AÇÃO resolvida (GAP 2). O inventário
nasce daqui (não é lista fixa de móveis): cada cômodo lista os assets que FAZEM SENTIDO pra ele (Felipe:
"nem todo cômodo tem sofá"). stdlib only; NÃO toca :8765 nem geometria — só LÊ sinais reais.

Sinais: tools/<asset>_class.py (classe existe) · reference pack curado · cycle.learning (patch aprovado) ·
artefatos em artifacts/review/furniture/<asset>/ (render compare / gpt_verdict / vray).
"""
from __future__ import annotations

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
    vtxt = ""
    vf = list(vdir.glob("**/gpt_verdict.md")) if vdir.exists() else []
    if vf:
        vtxt = vf[0].read_text("utf-8", "ignore")
    build_done = has("**/*compare*.png")
    form_pass = ("parou de parecer caixa" in vtxt) or ("Forma" in vtxt and "PASS" in vtxt)
    ctx_pass = ("Contexto" in vtxt and "PASS" in vtxt) or ("CONTEXTO" in vtxt and "PASS" in vtxt)
    vray_done = has("**/*vray*.png") or has("**/*_final*.png")

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


def project_state() -> dict:
    """O modelo inteiro: projeto → cômodos → assets (com estado + próxima ação). É a fonte do inventário."""
    rooms = []
    for r in ROOMS:
        assets = []
        for a in r["assets"]:
            stt = asset_state(a)
            stt["label"] = ASSET_META.get(a, a)
            assets.append(stt)
        done = sum(1 for a in assets if a["state"] in ("approved", "learned", "frozen"))
        rooms.append({"key": r["key"], "label": r["label"], "icon": r["icon"],
                      "assets": assets, "done": done, "total": len(assets)})
    return {"project": "planta_74", "rooms": rooms}
