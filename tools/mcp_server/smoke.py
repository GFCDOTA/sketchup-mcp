"""Smoke test do MCP da fatia 1 — exercita cada tool em processo.

Roda: python -m tools.mcp_server.smoke
Sai 0 se tudo ok; 1 se alguma asserção falhar.
"""

from __future__ import annotations

import asyncio
import sys

from tools.mcp_server import server as S

_fail: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = "ok " if cond else "FAIL"
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        _fail.append(name)


def main() -> int:
    print("== registro FastMCP ==")
    try:
        tools = asyncio.run(S.mcp.list_tools())
        names = sorted(t.name for t in tools)
    except Exception as e:  # noqa: BLE001
        names = []
        print("  (list_tools falhou:", e, ")")
    expected = {
        "list_capabilities", "run_deterministic_gates", "furniture_class_derive",
        "reference_to_grammar", "validate_grammar_spec", "room_gates",
        "kitchen_ergonomics_audit", "promote_canonical", "skp_inventory",
    }
    check("8+ tools registradas", len(names) >= 9, f"{names}")
    check("tools esperadas presentes", expected.issubset(set(names)),
          f"faltando: {expected - set(names)}")

    print("== list_capabilities ==")
    cap = S.list_capabilities()
    check("slice == 1", cap.get("slice") == 1)

    print("== furniture_class_derive ==")
    for kind in ("sofa", "bed", "armchair", "dining_table", "rack", "coffee_table"):
        r = S.furniture_class_derive(kind, archetype=None)
        gate = r.get("gate", {})
        check(f"{kind}: deriva + gate", "error" not in r and "result" in gate,
              f"gate={gate.get('result')} bbox={r.get('bbox_m')}")
    rs = S.furniture_class_derive("sofa", seats=3, archetype="lounge")
    check("sofa lounge 3-lugares", rs.get("gate", {}).get("result") in ("PASS", "WARN", "FAIL"),
          f"result={rs.get('gate', {}).get('result')}")
    check("kind inválido -> error", "error" in S.furniture_class_derive("foo"))

    print("== reference_to_grammar (contrato) ==")
    contract = S.reference_to_grammar(room_type="kitchen")
    check("modo contrato", contract.get("mode") == "contract")
    check("contrato tem tokens canônicos", len(contract.get("known_joinery_tokens", [])) > 0)
    check("contrato lista palette_roles", "countertop" in contract.get("palette_roles", []))

    print("== reference_to_grammar (normalize) ==")
    draft = {
        "reference": {"source": "pinterest", "note": "cozinha dois-tons madeira+fendi"},
        "style": "modern_compact_planned",
        "palette": {"base_cabinets": "warm_wood", "upper_cabinets": "off_white",
                    "countertop": "light_stone", "weird_role": "x"},
        "joinery_tokens": ["integrated_fridge_tower", "open_niche", "slab_doors", "totally_new_token"],
        "signature": "torre integrada + dois-tons + tampo fino contínuo",
    }
    norm = S.reference_to_grammar(room_type="kitchen", draft=draft, plant="planta_74", room_id="r004")
    vr = norm.get("vocab_report", {})
    syn = vr.get("synonyms_applied", {})
    check("modo normalized", norm.get("mode") == "normalized")
    check("colapsou integrated_fridge_tower->fridge_tower", syn.get("integrated_fridge_tower") == "fridge_tower")
    check("colapsou open_niche->upper_niche", syn.get("open_niche") == "upper_niche")
    check("flagou token desconhecido", "totally_new_token" in vr.get("unknown", []))
    check("flagou papel de paleta desconhecido", "weird_role" in vr.get("palette_roles_unknown", []))
    spec = norm.get("spec", {})
    check("fixed_anchors injetados do PDF", str(spec.get("fixed_anchors", {}).get("sink", "")).startswith("pdf_"))

    print("== validate_grammar_spec ==")
    v_ok = S.validate_grammar_spec(spec, room_id="r004")
    check("spec normalizada valida (WARN por token novo)", v_ok.get("result") in ("PASS", "WARN"),
          f"result={v_ok.get('result')} warns={len(v_ok.get('warnings', []))}")
    # FAIL: referência tentando mexer na POSIÇÃO
    bad = dict(spec)
    bad["fixed_anchors"] = {"_rule": "x", "sink": "mover pra parede norte", "doors": "pdf_doors"}
    v_bad = S.validate_grammar_spec(bad)
    check("FAIL quando referência mexe na posição", v_bad.get("result") == "FAIL",
          f"errors={v_bad.get('errors')}")
    # FAIL: campos obrigatórios faltando
    v_empty = S.validate_grammar_spec({"room": "kitchen"})
    check("FAIL quando faltam campos obrigatórios", v_empty.get("result") == "FAIL")

    print("== run_deterministic_gates ==")
    try:
        g = S.run_deterministic_gates(fixture="planta_74")
        check("gates rodaram", g.get("overall") in ("PASS", "FAIL", "INCOMPLETE"),
              f"overall={g.get('overall')} gates={list(g.get('gates', {}))}")
    except Exception as e:  # noqa: BLE001
        check("gates rodaram", False, f"exceção: {e!r}")

    print("== room_gates ==")
    rg = S.room_gates(room_id="r002", style="industrial")
    check("room_gates retornou (overlap/style ou error)",
          ("overlap" in rg) or ("style_coherence" in rg) or ("error" in rg),
          f"keys={list(rg)}")

    print("== kitchen_ergonomics_audit (pode estar ausente) ==")
    ke = S.kitchen_ergonomics_audit(room_id="r004")
    check("ergonomics responde com available", "available" in ke, f"available={ke.get('available')}")

    print("== promote_canonical (caminho de erro) ==")
    pc = S.promote_canonical(src_final="nope/does/not/exist", plant="planta_74")
    check("promote inexistente -> error", "error" in pc)

    print("== skp_inventory ==")
    try:
        inv = S.skp_inventory()
        check("inventário tem total", "total" in inv, f"total={inv.get('total')}")
    except Exception as e:  # noqa: BLE001
        check("inventário rodou", False, f"exceção: {e!r}")

    print()
    if _fail:
        print(f"SMOKE FAIL ({len(_fail)}): {_fail}")
        return 1
    print("SMOKE PASS — todas as tools ok.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
