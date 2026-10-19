"""FP-043/P5: perfis de especialista, roteamento e plano fail-closed (consultivo; nunca executa).

O especialista nao e um modulo Python: e um perfil delimitado (`tools/rooms/<comodo>/specialist.v1.json`) mais o
catalogo de capacidades (`tools/rooms/capability_catalog.v1.json`). Este modulo so LE metadados — nao importa
builders, nao abre SketchUp, nao gera Ruby. Resolve o comodo pelo registry existente (nada de segundo dispatch).

Fluxo de `plan(request)`: comodo -> perfil -> tecnica (binding) -> capacidade -> allowlist -> evidencia -> insumos.
Falta de capacidade, de ferramenta autorizada, de insumo ou pedido que altera arquitetura devolve um estado
`BLOCKED_*` com o motivo e o proximo passo; nunca uma caixa generica. O resultado `PLAN_READY_NOT_EXECUTED` e um plano
estruturado, nao uma autorizacao: execucao e responsabilidade do fluxo que liga capacidade + allowlist + confirmacao.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from tools.rooms import capability_catalog as cc
from tools.rooms.registry import ROOM_ALIASES, load_manifest

ROOT = Path(__file__).resolve().parents[2]
BLOCKED = "BLOCKED_CAPABILITY_MISSING"
PLAN_READY = "PLAN_READY_NOT_EXECUTED"
LENGTH_UNITS = ("m", "cm", "mm")
# Pedido que MEXE na arquitetura derivada do PDF (Hard Rule #1): verbo de alteracao ate 4 palavras de um elemento arquitetonico.
# Texto ja normalizado (minusculo, sem acento, hifen -> espaco). O gabinete tem as proprias portas: "porta do gabinete",
# "porta shaker" e "porta de correr" NAO sao arquitetura.
_ARCH_VERBS = (r"remov\w*|tir\w+|derrub\w*|demol\w*|apag\w*|delet\w*|exclu\w*|mov\w*|desloc\w*|abr\w*|fech\w*|quebr\w*|"
               r"alter\w*|modific\w*|troc\w*|ampli\w*|reduz\w*|cort\w*|fur\w*|shift\w*|open\w*|close\w*|break\w*|knock\w*|"
               r"cut\w*|change\w*|remove\w*|delete\w*|demolish\w*|move\w*")
_ARCH_NOUNS = (r"parede\w*|porta\w*|janela\w*|vao\w*|pilar\w*|pilares|viga\w*|laje\w*|muro\w*|shell|arquitetura|"
               r"wall\w*|door\w*|window\w*|opening\w*|column\w*|slab\w*|architecture|piso|floor")
_FILLER = r"(?:\W+(?:o|a|os|as|um|uma|uns|umas|de|do|da|dos|das|toda|todo|todas|todos|essa|esse|esta|este|aquela|aquele|the|an|this|that|my|our|all))*"
ARCHITECTURE_PATTERN = re.compile(rf"\b(?:{_ARCH_VERBS})\b{_FILLER}\W+\b(?:{_ARCH_NOUNS})\b")
_OWN_DOORS = re.compile(r"\bportas? (?:do|da|dos|das|de) (?:gabinete|armario|modulo|bancada|movel|correr)s?\b|\bportas? shaker\b")


def touches_architecture(text: str) -> bool:
    n = _OWN_DOORS.sub(" ", _norm(text))
    return bool(ARCHITECTURE_PATTERN.search(n))


def _norm(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", folded.lower().replace("-", " ")).strip()


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def room_key(room_or_alias: str) -> str:
    key = ROOM_ALIASES.get(_norm(room_or_alias).replace(" ", "_")) or ROOM_ALIASES.get(_norm(room_or_alias))
    if key is None:
        raise KeyError("UNSUPPORTED_ROOM_TYPE")
    return key


def profile_path(room: str, root: Path = ROOT) -> Path:
    return root / "tools/rooms" / room / "specialist.v1.json"


def load_profile(room_or_alias: str, root: Path = ROOT) -> dict:
    """Perfil validado pelo schema; o comodo e resolvido pelo registry (alias -> chave canonica)."""
    from jsonschema import Draft202012Validator

    room = room_key(room_or_alias)
    profile = _read(profile_path(room, root))
    schema = _read(root / "schemas/specialist_profile.v1.schema.json")
    errs = [e.message for e in Draft202012Validator(schema).iter_errors(profile)]
    if errs or profile["room"] != room:
        raise ValueError("INVALID_SPECIALIST_PROFILE_" + room + ": " + "; ".join(errs[:3]))
    return profile


def load_index(room: str, root: Path = ROOT) -> dict:
    return _read(root / "tools/rooms" / room / "knowledge/index.v1.json")


def verify_profiles(root: Path = ROOT) -> dict:
    """Gate dos perfis: schema, alias x registry, manifesto, indice por ID, capacidades e allowlist coerentes."""
    errors: dict[str, list[str]] = {}

    def flag(code: str, what: str) -> None:
        errors.setdefault(code, []).append(what)

    manifest = load_manifest()
    catalog = cc.load_catalog(root / "tools/rooms/capability_catalog.v1.json")
    cap_by = {c["id"]: c for c in catalog["capabilities"]}
    bind_ids = {b["id"] for b in catalog["bindings"]}
    env = _read(root / catalog["knowledge_catalogs"]["environment"])
    video = _read(root / catalog["knowledge_catalogs"]["video"])
    env_ids = {r["id"] for r in env["recipes"]}
    video_ids = {r["id"] for r in video["recipes"]}
    seen_rooms = []
    for room in cc.ROOMS:
        try:
            profile = load_profile(room, root)
        except (OSError, ValueError, KeyError) as exc:
            flag("PROFILE_INVALID_OR_MISSING", f"{room}: {exc}")
            continue
        seen_rooms.append(room)
        if set(profile["aliases"]) != {a for a, k in ROOM_ALIASES.items() if k == room}:
            flag("ALIASES_DIVERGE_FROM_REGISTRY", room)
        rec = manifest["rooms"][room]
        if profile["owner"] != rec["package"] or profile["state"] != rec["state"]:
            flag("PROFILE_DIVERGES_FROM_MANIFEST", room)
        if profile["execution_authorized"] is not False:
            flag("PROFILE_AUTHORIZES_EXECUTION", room)
        for sid in profile["source_ids"]:
            if sid not in env_ids:
                flag("PROFILE_SOURCE_UNKNOWN", f"{room}: {sid}")
        for rid in profile["recipe_ids"]:
            if rid not in video_ids:
                flag("PROFILE_RECIPE_UNKNOWN", f"{room}: {rid}")
        for cid in profile["capability_ids"]:
            if cid not in cap_by:
                flag("PROFILE_CAPABILITY_UNKNOWN", f"{room}: {cid}")
            else:
                for tool in cap_by[cid]["tools"]:
                    if tool not in profile["tool_allowlist"]:
                        flag("CAPABILITY_TOOL_NOT_IN_PROFILE_ALLOWLIST", f"{room}: {cid} {tool}")
        if profile["role"] in ("advisory", "reuse", "validation_only") and any(
                cap_by.get(c, {}).get("implementation", {}).get("state") == "IMPLEMENTED" and c.startswith(room)
                and profile["role"] != "validation_only" for c in profile["capability_ids"]):
            flag("ADVISORY_PROFILE_WITH_EXECUTABLE_CAPABILITY", room)
        if profile["role"] == "reuse" and profile["reuse_of"] not in cc.ROOMS:
            flag("REUSE_WITHOUT_TARGET", room)
        try:
            index = load_index(room, root)
        except OSError:
            flag("KNOWLEDGE_INDEX_MISSING", room)
            continue
        if index.get("room") != room:
            flag("KNOWLEDGE_INDEX_ROOM_MISMATCH", room)
        for rid in index["environment_recipes"]:
            if rid not in env_ids:
                flag("INDEX_RECIPE_UNKNOWN", f"{room}: {rid}")
        for rid in index["video_recipes"]:
            if rid not in video_ids:
                flag("INDEX_RECIPE_UNKNOWN", f"{room}: {rid}")
        if sorted(index["capabilities"]) != sorted(profile["capability_ids"]):
            flag("INDEX_CAPABILITIES_DIVERGE_FROM_PROFILE", room)
        for bid in index["bindings"]:
            if bid not in bind_ids:
                flag("INDEX_BINDING_UNKNOWN", f"{room}: {bid}")
        if "text" in index or "gui_workflow" in json.dumps(index):
            flag("INDEX_COPIES_RECIPE_TEXT", room)
    if seen_rooms != list(cc.ROOMS):
        flag("ROOM_COVERAGE", f"perfis presentes: {seen_rooms}")
    return {"result": "FAIL" if errors else "PASS", "errors": errors, "rooms": seen_rooms,
            "proof": "PERFIS_COERENTES_NAO_PROVAM_COMPORTAMENTO_DO_AGENTE"}


def _scores(text: str, root: Path = ROOT) -> dict[str, list[str]]:
    catalog = cc.load_catalog(root / "tools/rooms/capability_catalog.v1.json")
    env = _read(root / catalog["knowledge_catalogs"]["environment"])
    haystack = " " + _norm(text) + " "
    scores: dict[str, list[str]] = {}
    for r in env["rooms"]:
        key = {"laundry": "service"}.get(r["id"], r["id"])
        terms = {_norm(t) for t in r["routing_terms"]} | {_norm(a) for a, k in ROOM_ALIASES.items() if k == key}
        hits = sorted(t for t in terms if t and re.search(r"(?<![a-z0-9])" + re.escape(t) + r"s?(?![a-z0-9])", haystack))
        if hits:
            scores[key] = hits
    return scores


def route(text: str, room: str | None = None, root: Path = ROOT) -> dict:
    """Comodo do pedido. `room` explicito (alias do registry) vence; senao, pelos termos de roteamento do catalogo
    de conhecimento + aliases. Empate ou zero acerto = nao resolvido (nunca chuta). Se o `room` explicito nao tem
    nenhum termo no pedido e outro comodo tem, o pedido e de outro comodo: recusa (nao chama o vizinho)."""
    scores = _scores(text, root)
    if room:
        try:
            key = room_key(room)
        except KeyError:
            return {"state": "BLOCKED_ROOM_UNRESOLVED", "reason": f"comodo desconhecido: {room!r}", "candidates": []}
        hay = " " + _norm(text) + " "

        def named(k: str) -> bool:      # o pedido NOMEIA o comodo (alias do registry), nao so um termo generico como "porta"
            return any(re.search(r"(?<![a-z0-9])" + re.escape(_norm(a)) + r"s?(?![a-z0-9])", hay)
                       for a, kk in ROOM_ALIASES.items() if kk == k)
        others = sorted(k for k in scores if k != key and named(k))
        if others and not named(key):
            return {"state": "BLOCKED_ROOM_MISMATCH", "reason": f"o pedido nomeia {others} e nao {key}", "candidates": others}
        return {"state": "RESOLVED", "room": key, "via": "explicit", "matched": [room]}
    if not scores:
        return {"state": "BLOCKED_ROOM_UNRESOLVED", "reason": "nenhum termo de comodo no pedido", "candidates": []}
    top = max(len(v) for v in scores.values())
    best = sorted(k for k, v in scores.items() if len(v) == top)
    if len(best) != 1:
        return {"state": "BLOCKED_ROOM_UNRESOLVED", "reason": "pedido ambiguo entre comodos", "candidates": best}
    return {"state": "RESOLVED", "room": best[0], "via": "routing_terms", "matched": scores[best[0]]}


def _blocked(state: str, reason: str, next_step: str, **extra) -> dict:
    return {"state": state, "reason": reason, "next_step": next_step, "execution_authorized": False, **extra}


def _select_binding(bindings: list[dict], text: str, technique: str | None) -> tuple[list[dict], str]:
    if technique:
        chosen = [b for b in bindings if technique in b["recipe_ids"] or technique == b["id"]]
        return chosen, "technique"
    hay = " " + _norm(text) + " "
    chosen = []
    for b in bindings:
        for t in b.get("terms", []):
            t = _norm(t)
            if t and re.search(r"(?<![a-z0-9])" + re.escape(t), hay):
                chosen.append(b)
                break
    return chosen, "terms"


def plan(request: dict, root: Path = ROOT) -> dict:
    """Plano fail-closed. request: {text, room?, technique?, tool?, inputs?: {nome: {value, unit, origin}}, touches?: [..]}.
    Campos desconhecidos (ex.: texto de tutorial/PDF anexado) sao ignorados: nao ampliam allowlist nem direitos."""
    text = str(request.get("text") or "")
    norm_text = _norm(text)
    touches = {str(t).lower() for t in request.get("touches", [])}
    if touches & {"walls", "openings", "architecture"} or touches_architecture(text):
        return _blocked("BLOCKED_ARCHITECTURE_CHANGE", "o pedido altera arquitetura derivada do PDF (Hard Rule #1)",
                        "tratar como proposta ao Felipe; o especialista nao altera paredes, portas ou janelas")
    routed = route(text, request.get("room"), root)
    if routed["state"] != "RESOLVED":
        return _blocked(routed["state"], routed["reason"], "informar o comodo (ex.: cozinha, sala, quarto)", candidates=routed["candidates"])
    room = routed["room"]
    profile = load_profile(room, root)
    catalog = cc.load_catalog(root / "tools/rooms/capability_catalog.v1.json")
    base = {"room": room, "role": profile["role"], "profile": f"tools/rooms/{room}/specialist.v1.json"}

    tool = request.get("tool")
    if tool is not None and tool not in profile["tool_allowlist"]:
        return {**base, **_blocked("BLOCKED_TOOL_NOT_ALLOWED", f"ferramenta fora da allowlist do perfil {room}: {tool}",
                                   "usar uma ferramenta da allowlist ou registrar a capacidade (e sua autorizacao) no catalogo")}

    bindings = [b for b in catalog["bindings"] if b["room"] == room]
    chosen, _how = _select_binding(bindings, text, request.get("technique"))
    if not chosen:
        return {**base, **_blocked("BLOCKED_TECHNIQUE_UNRESOLVED", "nenhuma tecnica do catalogo casa com o pedido",
                                   "descrever a tecnica ou escolher uma das disponiveis", available=sorted(b["id"] for b in bindings))}
    # Varias tecnicas no mesmo pedido: TODAS precisam de capacidade (fail-closed). Ex.: "porta Shaker no armario" casa
    # "gabinete" (PLANNED) e "shaker" (ausente) -> bloqueado pela lacuna mais especifica (ausente antes de PLANNED).
    chosen = sorted(chosen, key=lambda b: (b["capability_id"] is not None, b["id"]))
    base["binding"] = chosen[0]["id"]
    base["recipes"] = sorted({r for b in chosen for r in b["recipe_ids"]})
    if len(chosen) > 1:
        base["also_matched"] = [b["id"] for b in chosen[1:]]
    caps_ready = []
    for binding in chosen:
        if binding["capability_id"] is None:
            return {**base, "binding": binding["id"], "recipes": binding["recipe_ids"],
                    **_blocked(BLOCKED, binding["gap"] or "capacidade ausente",
                               "registrar builder + fixture + teste da tecnica antes de pedir execucao",
                               gap=binding["gap"], knowledge_only=True)}
        cap = next(c for c in catalog["capabilities"] if c["id"] == binding["capability_id"])
        base["capability"] = {"id": cap["id"], "version": cap["version"], "implementation": cap["implementation"]["state"],
                              "validation": cap["validation"]["state"], "visual": cap["visual"]["state"]}
        if cap["implementation"]["state"] != "IMPLEMENTED":
            return {**base, **_blocked(BLOCKED, f"capacidade {cap['id']} esta {cap['implementation']['state']}",
                                       "implementar e validar a capacidade (L1 e L2) antes do plano executavel",
                                       gap="; ".join(cap["limitations"]) or None)}
        if cap["id"] not in profile["capability_ids"]:
            return {**base, **_blocked("BLOCKED_CAPABILITY_NOT_IN_PROFILE", f"{cap['id']} nao pertence ao perfil {room}",
                                       "outro comodo nao e chamado implicitamente; abrir o pedido no perfil dono")}
        outside = [t for t in cap["tools"] if t not in profile["tool_allowlist"]]
        if outside:
            return {**base, **_blocked("BLOCKED_TOOL_NOT_ALLOWED", f"ferramentas da capacidade fora da allowlist: {outside}",
                                       "corrigir a allowlist do perfil por revisao, nao pelo pedido")}
        stale = []
        for ev in cap["validation"]["evidence"]:
            for key, digest in ev["symbol_digests"].items():
                lang, _, ref = key.partition(":")
                if cc.symbol_digest({"lang": lang, "ref": ref}, root) != digest:
                    stale.append(key)
        if stale:
            return {**base, **_blocked("BLOCKED_EVIDENCE_STALE", f"o codigo mudou depois da prova: {stale}",
                                       "rodar de novo a validacao L2 na versao atual e atualizar o catalogo")}
        caps_ready.append(cap)
    params = list({p["name"]: p for c in caps_ready for p in c["parameters"]}.values())
    tools = list(dict.fromkeys(t for c in caps_ready for t in c["tools"]))
    cap = {"tools": tools, "parameters": params,
           "side_effects": "WRITES_WORKING_COPY" if any(c["side_effects"] != "NONE" for c in caps_ready) else "NONE",
           "preconditions": list(dict.fromkeys(x for c in caps_ready for x in c["preconditions"])),
           "invariants": list(dict.fromkeys(x for c in caps_ready for x in c["invariants"])),
           "validation": {"tests": list(dict.fromkeys(x for c in caps_ready for x in c["validation"]["tests"]))}}

    given = request.get("inputs") or {}
    missing = []
    for p in cap["parameters"]:
        item = given.get(p["name"])
        if not isinstance(item, dict) or item.get("value") in (None, "") or not item.get("unit") or not item.get("origin"):
            missing.append(p["name"])
            continue
        unit_ok = item["unit"] in LENGTH_UNITS if p["unit"] == "length" else item["unit"] == p["unit"]
        if not unit_ok or (item["origin"] != p["origin"] and p["origin"] != "default_declared"):
            missing.append(f"{p['name']} (esperado unit={p['unit']}, origin={p['origin']})")
    if missing:
        return {**base, **_blocked("BLOCKED_INPUT_INCOMPLETE", f"insumos sem valor/unidade/origem: {missing}",
                                   "informar cada medida com unidade e origem (pdf, consensus, user_request)", missing=missing)}
    return {**base, "state": PLAN_READY, "execution_authorized": False,
            "steps": [{"tool": t, "side_effects": cap["side_effects"]} for t in cap["tools"]],
            "preconditions": cap["preconditions"], "invariants": cap["invariants"],
            "validation_required": cap["validation"]["tests"], "rollback": "descartar a copia de trabalho; o original nunca e sobrescrito",
            "visual_review": "necessaria se a aparencia mudar (veredito e do Felipe)",
            "note": "plano estruturado, nao autorizacao de execucao"}
