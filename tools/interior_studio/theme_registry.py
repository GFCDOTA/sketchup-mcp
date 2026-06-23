"""theme_registry.py — TEMA = tópico multi-schema. Cada tema é dono de UM schema de validação
(checks + thresholds + anti-patterns + DNA) e tem UM estagiário responsável. É o registry que
faz "estagiários separados por tema": o estagiário de black_wood_gold só conhece o schema dele.

Tema = DADO (não agente caro): o "estagiário" é um PERFIL (persona+modelo) que vira dispatch.
Right-sized: hoje há 4 presets reais (black_wood_gold, dark_walnut, hotel_boutique, warm_compact);
a estrutura suporta N. DNA canônico vem de .claude/memory/felipe_style_dna.md + os presets em
artifacts/reference_lab/themes/. stdlib only.

Cada check tem `kind`:
  - "deterministic": avaliado pelos números do render_fingerprint (gate = verdade).
  - "vision": uma pergunta pro modelo de visão (vision_describe).
  - "hybrid": número determinístico (suporte) + pergunta de visão (confirma).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
THEMES_DIR = ROOT / "artifacts/reference_lab/themes"
DNA_FILE = ROOT / ".claude/memory/felipe_style_dna.md"

# ---- estagiário (perfil) por tema: persona + modelo local de síntese ----
INTERNS = {
    "black_wood_gold": {"id": "intern-nero", "persona": "Nero — especialista no escuro premium "
                        "(black/wood/gold industrial boutique). Caça caverna e fake-gold.",
                        "model": "deepseek-r1:14b"},
    "dark_walnut": {"id": "intern-walnut", "persona": "Walnut — moody nogueira premium.",
                    "model": "deepseek-r1:14b"},
    "hotel_boutique": {"id": "intern-lobby", "persona": "Lobby — boutique quente equilibrado.",
                       "model": "deepseek-r1:14b"},
    "warm_compact": {"id": "intern-fendi", "persona": "Fendi — claro/quente compacto.",
                     "model": "deepseek-r1:14b"},
}

# DNA curto por tema (o canônico vivo em felipe_style_dna.md / presets). Embed = robusto a path.
_DNA = {
    "black_wood_gold": (
        "BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE: preto/grafite fosco como BASE quieta; madeira "
        "natural quente como ACENTO; pedra escura de veio dourado SUTIL como PROTAGONISTA; "
        "bronze discreto só pontuação; eletros inox dark REFLEXIVOS; LED 2700K. Escuro mas "
        "NÃO caverna (luz+reflexo+madeira compensam). Premium não-fake. 'Casa de gente rica'."),
}
_ANTI = {
    "black_wood_gold": [
        "caverna: tudo preto sem compensação de luz/reflexo (bloco morto)",
        "fake-luxury: veio dourado gritante / ouro espalhado / puxador dourado demais",
        "preto puro chapado [0,0,0] sem matiz nem reflexo",
        "LED frio 4000K+ (quebra a paleta quente)",
        "branco puro/chapado (cheira MDF barato)",
        "madeira na área molhada (parece fake)",
    ],
}

# ---- o SCHEMA de checks do black_wood_gold (o 'juiz do Felipe' operacionalizado) ----
# det_field aponta um campo do fingerprint (dot-path); warn/fail comparam; q = pergunta de visão.
# NB (lição da verificação): qwen2.5vl:7b super-dispara cave/fake-gold e perde blowout sutil.
# Princípio do projeto: gate DETERMINÍSTICO = verdade; visão = CONSULTIVA. Por isso:
#   - check com det_field => o número DECIDE (pode FAIL); a visão só pode escalar PASS->WARN.
#   - check só-visão => "advisory": cap em WARN (nunca derruba sozinho, porque é ruidoso).
_CHECKS_BWG = [
    {"id": "no_blowout", "label": "sem objeto estourado", "kind": "hybrid", "type": "bool",
     "q": "Há algum objeto BRANCO ESTOURADO, sem detalhe (uma superfície clara virando branco puro)?",
     "bad_answer": True, "det_field": "clipped_pct", "fail_above": 1.0, "warn_above": 0.1},
    {"id": "not_cave", "label": "escuro mas NÃO caverna", "kind": "hybrid", "type": "bool",
     "q": "Parece CAVERNA — escuro demais, o ambiente some no preto?",
     "bad_answer": True, "det_field": "exposure.mean_lum", "fail_below": 30, "warn_below": 42},
    {"id": "warmth", "label": "luz quente 2700K", "kind": "hybrid", "type": "str",
     "q": "A luz é QUENTE (âmbar/2700K) ou FRIA (azulada/branca)?", "good_contains": "quent",
     "det_field": "warmth", "fail_below": -0.01, "warn_below": 0.04},
    {"id": "warm_metals", "label": "metais bronze quente", "kind": "vision", "type": "str",
     "q": "Os metais (luminária/mesa/detalhes) são BRONZE/DOURADO quente ou PRATA/CROMO frio?",
     "good_contains": "bronze", "advisory": True},
    {"id": "wood_accent", "label": "madeira quente de acento", "kind": "vision", "type": "bool",
     "q": "Há MADEIRA natural quente visível como acento (tampo/painel/aparador)?",
     "good_answer": True, "advisory": True},
    {"id": "no_fake_gold", "label": "sem fake-luxury", "kind": "vision", "type": "bool",
     "q": "Há veio dourado EXAGERADO/brega ou ouro espalhado demais (luxo fake)?",
     "bad_answer": True, "advisory": True},
    {"id": "material_hierarchy", "label": "hierarquia de material", "kind": "vision", "type": "bool",
     "q": "A leitura é preto como BASE, madeira/pedra como acento e bronze só pontual (sim) ou está bagunçada (não)?",
     "good_answer": True, "advisory": True},
]

# default p/ temas sem schema próprio ainda (estrutura suporta, conteúdo evolui)
_CHECKS_DEFAULT = [
    {"id": "no_blowout", "label": "sem objeto estourado", "kind": "vision", "type": "bool",
     "q": "Há objeto branco estourado, sem detalhe?", "bad_answer": True, "support_field": "clipped_pct"},
    {"id": "exposure_ok", "label": "exposição ok", "kind": "hybrid", "type": "bool",
     "q": "Está escuro demais (caverna) ou claro/estourado demais?", "bad_answer": True,
     "det_field": "exposure.mean_lum", "fail_below": 20, "warn_below": 35},
    {"id": "palette_match", "label": "paleta do tema", "kind": "vision", "type": "bool",
     "q": "A paleta bate com o tema proposto?", "good_answer": True},
]
_THEME_CHECKS = {"black_wood_gold": _CHECKS_BWG}


def themes() -> list[str]:
    """Ids de tema conhecidos (presets em disco + os com schema embutido)."""
    disk = {p.stem.lower() for p in THEMES_DIR.glob("*.json")} if THEMES_DIR.exists() else set()
    known = set(INTERNS) | set(_THEME_CHECKS)
    # normaliza nomes de preset (BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE -> black_wood_gold via match)
    return sorted(known | {d for d in disk})


def resolve(theme_id: str) -> str:
    """Aceita aliases/nomes de preset → id canônico do registry."""
    t = (theme_id or "").lower()
    for canon in INTERNS:
        if canon in t or t in canon:
            return canon
    return t


def load_theme(theme_id: str) -> dict:
    """O tema como tópico: id, estagiário-dono, DNA, anti-patterns, checks (schema)."""
    tid = resolve(theme_id)
    return {
        "id": tid,
        "intern": INTERNS.get(tid, {"id": f"intern-{tid}", "persona": f"estagiário de {tid}",
                                    "model": "deepseek-r1:14b"}),
        "dna": _DNA.get(tid, f"tema {tid} (DNA ainda não destilado — usar default)"),
        "anti_patterns": _ANTI.get(tid, []),
        "checks": _THEME_CHECKS.get(tid, _CHECKS_DEFAULT),
    }


def vision_questions(theme: dict) -> list[dict]:
    """As perguntas de visão deste tema (checks kind vision|hybrid)."""
    return [{"key": c["id"], "q": c["q"], "type": c.get("type", "str")}
            for c in theme["checks"] if c["kind"] in ("vision", "hybrid")]


def _dig(d: dict, dotpath: str):
    cur = d
    for part in dotpath.split("."):
        cur = (cur or {}).get(part) if isinstance(cur, dict) else None
    return cur


def _vision_status(check: dict, vision_answers: dict) -> tuple[str | None, str]:
    """Status que a VISÃO sugere p/ o check (ou None se sem resposta). Nunca > WARN se advisory."""
    ans = vision_answers.get(check["id"])
    if ans is None:
        return None, ""
    a_str = str(ans).strip().lower()
    a_bool = ans is True or a_str in ("true", "sim", "yes")
    s = "PASS"
    if "bad_answer" in check and a_bool == bool(check["bad_answer"]):
        s = "FAIL"
    elif "good_answer" in check and a_bool != bool(check["good_answer"]):
        s = "WARN"
    elif "good_contains" in check and check["good_contains"] not in a_str:
        s = "WARN"
    if check.get("advisory") and s == "FAIL":   # visão ruidosa NÃO derruba sozinha
        s = "WARN"
    return s, f"visão:{ans}"


def eval_check(check: dict, fp: dict, vision_answers: dict) -> dict:
    """Avalia UM check → {id,label,status,basis,detail}. REGRA (gate determinístico = verdade):
    - com det_field: o NÚMERO decide FAIL/WARN/PASS; a visão só escala PASS->WARN (nunca FAIL).
    - só-visão (advisory): a visão sugere mas é capada em WARN (qwen2.5vl é ruidoso p/ isto).
    """
    cid = check["id"]
    order = {"FAIL": 3, "WARN": 2, "PASS": 1, "UNKNOWN": 0}
    vstatus, vdetail = _vision_status(check, vision_answers)
    # --- determinístico decide quando há det_field ---
    if check.get("det_field"):
        val = _dig(fp, check["det_field"])
        det = "PASS"
        if isinstance(val, (int, float)):
            if "fail_below" in check and val < check["fail_below"]:
                det = "FAIL"
            elif "fail_above" in check and val > check["fail_above"]:
                det = "FAIL"
            elif "warn_below" in check and val < check["warn_below"]:
                det = "WARN"
            elif "warn_above" in check and val > check["warn_above"]:
                det = "WARN"
        status = det
        if det == "PASS" and vstatus in ("WARN", "FAIL"):    # visão só escala PASS->WARN
            status = "WARN"
        det_detail = f"{check['det_field']}={val}"
        return {"id": cid, "label": check["label"], "status": status, "basis": "deterministic+vision",
                "detail": "; ".join(d for d in (det_detail, vdetail) if d)}
    # --- só-visão (advisory) ---
    if vstatus is None:
        return {"id": cid, "label": check["label"], "status": "UNKNOWN",
                "basis": "vision", "detail": "sem resposta de visão"}
    return {"id": cid, "label": check["label"], "status": vstatus, "basis": "vision(advisory)",
            "detail": vdetail}
