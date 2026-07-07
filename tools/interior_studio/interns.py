"""interns.py — Estagiários do Arquiteto: validadores TEMÁTICOS de um furniture_program.

Cada estagiário é uma LENTE: recebe a proposta do Arquiteto (furniture_program) + o contexto do
cômodo e PROPÕE achados na sua especialidade — NUNCA muta nada. Substitui o achado monolítico do
auditor ("viola o gate — removeria=… injetaria=…") por vereditos legíveis POR TEMA, então fica óbvio
QUAL regra quebrou. 5 estagiários determinísticos (gate = verdade, idempotente) + 1 leve via LLM
(estilo, degrada p/ SKIPPED_OFFLINE se o Ollama estiver fora). stdlib only; sem clock/random.

Roster
- 🧭 pertencimento  — item é semanticamente de OUTRO cômodo? (cama na sala, cooktop no quarto)
- 📋 completude     — todos os CORE do cômodo estão presentes? (cozinha sem bancada/cooktop/geladeira)
- 🏷️ nomenclatura  — nome carrega prefixo de outro cômodo? (banheiro_armario dentro da cozinha)
- 📐 capacidade     — a mobília de PISO cabe no m² deixando circulação?
- ♻️ redundancia    — dois+ móveis fazendo a MESMA função num cômodo apertado?
- 🎨 estilo         — respeita o DNA (industrial boutique premium, black/wood/gold)? [LLM-leve]
"""
from __future__ import annotations

import json
import urllib.request

from tools.interior_studio import architect_program as ic_arch

# ---- roster meta (ordem = ordem de exibição no dashboard) ----
ROSTER = ["pertencimento", "completude", "nomenclatura", "capacidade", "redundancia", "estilo"]
LABELS = {
    "pertencimento": "🧭 Pertencimento", "completude": "📋 Completude",
    "nomenclatura": "🏷️ Nomenclatura", "capacidade": "📐 Capacidade",
    "redundancia": "♻️ Redundância", "estilo": "🎨 Estilo",
}
DESC = {
    "pertencimento": "item é semanticamente de outro cômodo",
    "completude": "todos os CORE do cômodo presentes",
    "nomenclatura": "nome com prefixo de outro cômodo / fora do canônico",
    "capacidade": "a mobília de piso cabe no m² com circulação",
    "redundancia": "dois+ móveis com a mesma função no cômodo",
    "estilo": "respeita o DNA industrial boutique (LLM-leve)",
}

# prefixo declara um cômodo (token inicial 'banheiro_…' => o Arquiteto quis dizer banheiro)
PREFIX_ROOM = {"banheiro": "banheiro", "banho": "banheiro", "lavabo": "banheiro",
               "cozinha": "cozinha", "sala": "sala", "suite": "suite", "quarto": "suite"}

# footprint de PISO (m²) por keyword (primeira match vence). Itens de parede/teto não disputam piso.
WALL_CEIL = ("pendant", "luminária", "luminaria", "sconce", "lustre", "lâmpada", "lampada",
             "lamp", "abajur", "espelho", "mirror", "quadro", "artwork", "arte", "poster",
             "cabide", "towel", "toalheiro", "prateleira", "nicho")
FOOTPRINT = [
    (("cama", "bed"), 3.2),
    (("sofa", "sofá"), 1.8),
    (("guarda", "wardrobe", "roupeiro", "closet"), 1.4),
    (("ilha", "island"), 1.4),
    (("mesa_jantar", "mesa_de_jantar", "dining", "jantar"), 1.4),
    (("gabinete", "armario", "armário", "buffet", "aparador", "pantry", "sobreposta",
      "bancada", "counter", "vanity"), 1.0),
    (("geladeira", "fridge", "refriger"), 0.5),
    (("coffee", "mesa_centro", "centro"), 0.4),
    (("desk", "escrivaninha", "workspace", "escritorio", "mesa", "table"), 0.8),
    (("chuveiro", "shower", "box"), 0.8),
    (("poltrona", "armchair", "cadeira", "chair", "banco", "bench", "bar", "puff"), 0.5),
    (("rack", "console", "estante", "painel", "home_theater"), 0.5),
    (("vaso", "privada", "sanitário", "sanitario", "toilet"), 0.4),
    (("pia", "cuba", "lavatório", "lavatorio", "vessel"), 0.4),
    (("cooktop", "fogão", "fogao", "stove", "forno", "oven"), 0.4),
    (("bidet", "bidê", "bide"), 0.3),
    (("criado", "nightstand", "cabeceira"), 0.2),
]
_FOOT_DEFAULT = 0.4   # item de piso desconhecido: estimativa modesta (não inflar capacidade)

FILL_WARN, FILL_FAIL = 0.55, 0.72   # fração do piso ocupada por mobília (deixa o resto p/ circular)

# função de uso (p/ redundância): cada item cai em NO MÁXIMO uma (ordem = prioridade).
FUNCTIONS = [
    ("dining_surface", ("mesa_jantar", "mesa_de_jantar", "dining", "jantar")),
    ("cooking",        ("cooktop", "fogão", "fogao", "stove", "forno", "oven")),
    ("cold_storage",   ("geladeira", "fridge", "refriger")),
    ("wash",           ("pia", "cuba", "lavatório", "lavatorio", "vessel")),
    ("media",          ("rack", "console", "painel", "home_theater", "estante", "tv")),
    ("storage",        ("guarda", "wardrobe", "roupeiro", "closet", "armario", "armário",
                        "gabinete", "buffet", "aparador", "pantry", "cristaleira",
                        "sobreposta", "storage", "gaveta", "criado", "nightstand", "cabeceira")),
    ("seating",        ("sofa", "sofá", "poltrona", "armchair", "cadeira", "chair",
                        "banco", "bench", "bar", "puff")),
    ("surface",        ("coffee", "mesa_centro", "centro", "mesa", "table", "desk", "escrivaninha")),
]
FUNC_LABEL = {"dining_surface": "mesa de jantar", "cooking": "cocção", "cold_storage": "refrigeração",
              "wash": "lavagem", "media": "mídia/TV", "storage": "armazenamento",
              "seating": "assento", "surface": "superfície de apoio"}


def _strip(name: str, room_key: str) -> str:
    """nome cru → minúsculo, sem prefixo de cômodo (reusa o stripper do gate do Arquiteto)."""
    return ic_arch._strip_room_prefix(str(name).strip().lower(), room_key)


def _footprint(name: str) -> float:
    if any(tok in name for tok in WALL_CEIL):
        return 0.0
    for kws, foot in FOOTPRINT:
        if any(k in name for k in kws):
            return foot
    return _FOOT_DEFAULT


def _function(name: str) -> str | None:
    for fn, kws in FUNCTIONS:
        if any(k in name for k in kws):
            return fn
    return None


def _cap(func: str, area: float) -> int:
    if func in ("dining_surface", "cooking", "cold_storage", "media"):
        return 1
    if func == "wash":
        return 2
    if func == "storage":
        return 1 if area < 6 else (2 if area < 12 else 3)
    if func == "seating":
        return 2 if area < 6 else (3 if area < 12 else 4)
    if func == "surface":
        return 2 if area < 10 else 3
    return 99


def _finding(intern: str, severity: str, title: str, detail: str, **extra) -> dict:
    f = {"intern": intern, "intern_label": LABELS[intern], "severity": severity,
         "title": title, "detail": detail}
    f.update(extra)
    return f


# ----------------------------- os 5 estagiários determinísticos -----------------------------
def intern_pertencimento(prog: dict) -> list[dict]:
    """Item semanticamente exclusivo de OUTRO cômodo (cama na sala, cooktop no quarto)."""
    env = prog.get("environment", "")
    excl = ic_arch.ROOM_EXCLUSIVE.get(env, [])
    bad = []
    for it in prog.get("items", []):
        raw = str(it.get("asset", "")).strip().lower()
        name = _strip(raw, env)
        if any(tok in name for tok in excl):
            bad.append(raw)
    if not bad:
        return []
    return [_finding("pertencimento", "high",
                     f"{prog.get('room_name', env)} — item de outro cômodo: {', '.join(bad)}",
                     f"Itens que pertencem a outro tipo de cômodo: {', '.join(bad)}. "
                     "Remover ou re-propor — o cômodo errado quebra o inventário.",
                     items=bad, suggest_remove=bad)]


def intern_completude(prog: dict) -> list[dict]:
    """Falta algum item CORE obrigatório do cômodo (cozinha sem bancada/cooktop/geladeira)."""
    env = prog.get("environment", "")
    core = ic_arch.CORE_BY_ROOM.get(env, [])
    if not core:
        return []
    names = [_strip(it.get("asset", ""), env) for it in prog.get("items", [])]
    missing = [label for canon, kws, label in core
               if not any(any(k in n for k in kws) for n in names)]
    if not missing:
        return []
    return [_finding("completude", "high",
                     f"{prog.get('room_name', env)} — falta CORE: {', '.join(missing)}",
                     f"O programa não inclui itens essenciais do cômodo: {', '.join(missing)}. "
                     "Re-propor com o Arquiteto endurecido (ou injetar pelo gate).",
                     items=missing, suggest_inject=missing)]


def intern_nomenclatura(prog: dict) -> list[dict]:
    """Nome carrega prefixo de OUTRO cômodo (banheiro_armario dentro da cozinha)."""
    env = prog.get("environment", "")
    bad = []
    for it in prog.get("items", []):
        raw = str(it.get("asset", "")).strip().lower()
        for tok, room in PREFIX_ROOM.items():
            if (raw.startswith(tok + "_") or raw.startswith(tok + "-") or raw.startswith(tok + " ")) \
                    and room != env:
                bad.append(raw)
                break
    if not bad:
        return []
    return [_finding("nomenclatura", "med",
                     f"{prog.get('room_name', env)} — nome com prefixo de outro cômodo: {', '.join(bad)}",
                     f"Itens nomeados com prefixo de outro cômodo: {', '.join(bad)}. "
                     "Renomear sem o prefixo (ex.: 'banheiro_armario' → 'armario') — sinal de que o "
                     "Arquiteto vazou de cômodo.",
                     items=bad)]


def intern_capacidade(prog: dict) -> list[dict]:
    """A mobília de PISO cabe no m² deixando circulação?"""
    area = float(prog.get("area_m2") or 0) or 0.0
    if area <= 0:
        return []
    env = prog.get("environment", "")
    floor = []
    for it in prog.get("items", []):
        name = _strip(it.get("asset", ""), env)
        foot = _footprint(name)
        if foot > 0:
            floor.append((str(it.get("asset", "")).strip().lower(), foot))
    used = round(sum(f for _, f in floor), 1)
    fill = used / area
    if fill < FILL_WARN:
        return []
    sev = "high" if fill >= FILL_FAIL else "med"
    pieces = ", ".join(f"{n} (~{f}m²)" for n, f in floor)
    return [_finding("capacidade", sev,
                     f"{prog.get('room_name', env)} — mobília ocupa ~{round(fill * 100)}% do piso "
                     f"({len(floor)} itens em {area} m²)",
                     f"Footprint de piso ~{used} m² de {area} m² ({round(fill * 100)}%); acima de "
                     f"~{round(FILL_WARN * 100)}% sufoca a circulação num apê compacto. Itens: {pieces}. "
                     "Cortar/embutir o supérfluo.",
                     fill=round(fill, 2), used_m2=used, area_m2=area)]


def intern_redundancia(prog: dict) -> list[dict]:
    """Dois+ móveis com a MESMA função num cômodo apertado (3 storages numa cozinha de 5 m²)."""
    area = float(prog.get("area_m2") or 0) or 99.0
    env = prog.get("environment", "")
    groups: dict[str, list[str]] = {}
    for it in prog.get("items", []):
        raw = str(it.get("asset", "")).strip().lower()
        fn = _function(_strip(raw, env))
        if fn:
            groups.setdefault(fn, []).append(raw)
    out = []
    for fn, members in groups.items():
        cap = _cap(fn, area)
        if len(members) > cap:
            out.append(_finding("redundancia", "med",
                                f"{prog.get('room_name', env)} — {len(members)} móveis de "
                                f"'{FUNC_LABEL.get(fn, fn)}' (cabe ~{cap} em {area} m²)",
                                f"Função '{FUNC_LABEL.get(fn, fn)}' repetida: {', '.join(members)}. "
                                f"Num cômodo de {area} m² ~{cap} resolve — consolidar pra não duplicar.",
                                items=members, function=fn))
    return out


# ----------------------------- estagiário de estilo (LLM-leve) -----------------------------
_OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"


def _ollama_up(timeout: int = 2) -> bool:
    try:
        urllib.request.urlopen(_OLLAMA_TAGS, timeout=timeout).read()
        return True
    except Exception:  # noqa: BLE001
        return False


STYLE_PROMPT = """Você é um ESTAGIÁRIO de estilo. O DNA do escritório (RESTRIÇÃO, não sugestão): industrial boutique premium — preto/madeira escura/dourado, marcenaria sóbria, sem brega.

COMODO: {room} ({area} m2)
ITENS PROPOSTOS: {items}

Algum item destoa do DNA (material/cor/acabamento brega ou genérico)? Responda APENAS JSON, nada fora:
{{"verdict":"PASS|WARN|FAIL","off_style":["item",...],"note":"1 linha curta"}}
PASS=tudo coerente; WARN=1-2 itens duvidosos; FAIL=destoa claramente."""


def intern_estilo(prog: dict, timeout: int = 60) -> list[dict]:
    """Veredito de coerência de estilo via LLM-leve (qwen). Degrada p/ [] se o Ollama estiver fora."""
    if not _ollama_up():
        return []
    items = ", ".join(str(it.get("asset", "")) for it in prog.get("items", []))
    if not items:
        return []
    prompt = STYLE_PROMPT.format(room=prog.get("room_name", prog.get("environment", "")),
                                 area=prog.get("area_m2", "?"), items=items)
    try:
        raw = ic_arch._ollama(ic_arch.MODELS["qwen"], prompt, timeout=timeout)
        v = ic_arch._extract_json(raw) or {}
    except Exception:  # noqa: BLE001
        return []
    verdict = str(v.get("verdict", "")).upper()
    if verdict not in ("WARN", "FAIL"):
        return []
    off = [str(x) for x in (v.get("off_style") or [])]
    note = str(v.get("note", "")).strip()
    env = prog.get("environment", "")
    return [_finding("estilo", "med" if verdict == "FAIL" else "low",
                     f"{prog.get('room_name', env)} — estilo {verdict}"
                     + (f": {', '.join(off)}" if off else ""),
                     f"{note or 'itens fora do DNA industrial boutique.'}"
                     + (f" Itens: {', '.join(off)}." if off else ""),
                     items=off, verdict=verdict)]


# ----------------------------- orquestração -----------------------------
def review_program(prog: dict, with_style: bool = True) -> dict:
    """Roda TODOS os estagiários sobre um furniture_program. Devolve um veredito estruturado
    (não muta). verdict = pior severidade encontrada (high→FAIL, med→WARN, low→WARN, vazio→PASS)."""
    findings: list[dict] = []
    findings += intern_pertencimento(prog)
    findings += intern_completude(prog)
    findings += intern_nomenclatura(prog)
    findings += intern_capacidade(prog)
    findings += intern_redundancia(prog)
    if with_style:
        findings += intern_estilo(prog)
    sev = {f["severity"] for f in findings}
    verdict = "FAIL" if "high" in sev else ("WARN" if sev else "PASS")
    return {"room_id": prog.get("room_id"), "environment": prog.get("environment"),
            "room_name": prog.get("room_name"), "verdict": verdict,
            "n_findings": len(findings), "findings": findings}


def gaps_for_program(prog: dict, with_style: bool = True) -> list[dict]:
    """Converte os achados dos estagiários em proposals `consistency_gap` (id determinístico por
    estagiário×cômodo) p/ o Auditor salvar e o Felipe aprovar/ignorar no dashboard."""
    subject = prog.get("room_id") or prog.get("environment") or "?"
    out = []
    for f in review_program(prog, with_style=with_style)["findings"]:
        g = {"id": f"gap_{f['intern']}_{subject}", "type": "consistency_gap",
             "kind": f"intern_{f['intern']}", "intern": f["intern"],
             "intern_label": f["intern_label"], "severity": f["severity"],
             "title": f["title"], "detail": f["detail"],
             "environment": prog.get("environment"), "room_name": prog.get("room_name"),
             "room_id": prog.get("room_id"),
             "source_worker": f"Estagiário · {f['intern_label']}"}
        for k in ("items", "suggest_remove", "suggest_inject", "fill", "function", "verdict"):
            if k in f:
                g[k] = f[k]
        out.append(g)
    return out


if __name__ == "__main__":
    import sys

    from tools.interior_studio import proposals as ic_proposals

    sys.stdout.reconfigure(encoding="utf-8")
    with_style = "--style" in sys.argv
    st = ic_proposals.state()
    progs = [p for p in st["pending"] + st["approved"] if p.get("type") == "furniture_program"]
    report = [review_program(p, with_style=with_style) for p in progs]
    print(json.dumps(report, ensure_ascii=False, indent=2))
