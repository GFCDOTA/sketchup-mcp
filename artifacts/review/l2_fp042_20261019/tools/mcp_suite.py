"""Bateria L2 de contratos su_* PELO TRANSPORTE MCP stdio (server real, processo novo
por chamada). Cada SketchUp que a chamada sobe é fechado pelo PID que ela devolve.
Base: um .skp mobiliado sintético (cópia). Resultados: <out>/<id>.json + suite.json.
uso: mcp_suite.py <base.skp> <out_dir>"""
import asyncio
import functools
print = functools.partial(print, flush=True)  # noqa: A001
import hashlib
import json
import os
import shutil
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tools.sketchup import jobs

BASE_SRC, OUT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
REPO = Path.cwd().resolve()
BASE = OUT / "base.skp"
shutil.copy2(BASE_SRC, BASE)
SOFA = OUT / "insert_sofa.skp"
shutil.copy2(REPO / "references/sofas/raw/modern_dark_gray.skp", SOFA)
ARCH = OUT / "insert_has_architecture.skp"
shutil.copy2(REPO / "runs/l2_fp042_20261019/S05_builders_isolated/builders.skp", ARCH)


def rel(p):
    return str(Path(p).resolve().relative_to(REPO)).replace("\\", "/")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).exists() else None


async def call(tool, args):
    params = StdioServerParameters(command=sys.executable, args=["-m", "tools.mcp_server.server"],
                                   cwd=str(REPO), env=dict(os.environ))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args, read_timeout_seconds=timedelta(seconds=900))
            txt = res.content[0].text if res.content else ""
            try:
                return json.loads(txt), res.isError
            except ValueError:
                return {"_raw": txt}, res.isError


def close_own(res):
    pid = res.get("pid") if isinstance(res, dict) else None
    if pid:
        return jobs.close(pid=int(pid), force=True, confirm=True)
    return None


RESULTS = []


async def run(tid, tool, args, check):
    res, is_err = await call(tool, args)
    closed = close_own(res)
    try:
        verdict, why = check(res)
    except Exception as e:  # noqa: BLE001
        verdict, why = "FAIL", f"check levantou {type(e).__name__}: {e}"
    rec = {"id": tid, "tool": tool, "args": args, "is_error": is_err, "status": res.get("status"),
           "reason": res.get("reason") or res.get("errors") or (res.get("result") or {}).get("error"),
           "verdict": verdict, "why": why, "closed": closed}
    (OUT / f"{tid}.json").write_text(json.dumps({**rec, "raw": res}, indent=1, ensure_ascii=False, default=str),
                                     encoding="utf-8")
    RESULTS.append(rec)
    print(f"{tid:5} {verdict:4} {tool:15} status={res.get('status')} :: {why}"[:300], flush=True)
    return res


def nodes_of(res):
    return {n["name"]: n for n in res["result"]["nodes"] if n["name"]}


async def inspect(p):
    res, _ = await call("su_inspect", {"skp_path": rel(p), "max_depth": 2})
    close_own(res)
    return res


def bb(n):
    return n["bbox_world_m"]


def approx(a, b, tol=0.0005):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


async def main():
    base_hash = sha(BASE)
    b0 = await run("I01", "su_inspect", {"skp_path": rel(BASE), "max_depth": 2},
                   lambda r: ("PASS", f"{len(r['result']['nodes'])} nós") if r["status"] == "OK" else ("FAIL", r))
    N0 = nodes_of(b0)
    cama, cr1 = N0["SUITE 02 · Cama"], N0["SUITE 02 · Criado-mudo 1"]
    shell = N0["PlanShell_Group"]
    o = lambda name: rel(OUT / name)  # noqa: E731

    # ---------------- positivos + reabertura ----------------
    r = await run("E01", "su_apply_edits", {"skp_path": rel(BASE), "out_path": o("E01_move.skp"), "ops": [
        {"op": "move", "target": {"name": "SUITE 02 · Cama"}, "by_m": [0.10, -0.05, 0.0]}]},
        lambda r: ("PASS", "salvo") if r["status"] == "OK" else ("FAIL", r.get("reason")))
    i = nodes_of(await inspect(OUT / "E01_move.skp"))
    c1 = i["SUITE 02 · Cama"]
    ok = approx(bb(c1)["min"], [bb(cama)["min"][0] + 0.10, bb(cama)["min"][1] - 0.05, bb(cama)["min"][2]]) \
        and approx(bb(c1)["size"], bb(cama)["size"]) and approx(bb(i["SUITE 02 · Guarda-roupa"])["min"], bb(N0["SUITE 02 · Guarda-roupa"])["min"]) \
        and approx(bb(i["PlanShell_Group"])["min"], bb(shell)["min"])
    RESULTS.append({"id": "E01r", "verdict": "PASS" if ok else "FAIL",
                    "why": f"reaberto: cama min {bb(cama)['min']} -> {bb(c1)['min']}; outros/shell intactos={ok}"})
    print("E01r", RESULTS[-1]["verdict"], RESULTS[-1]["why"])

    r = await run("E02", "su_apply_edits", {"skp_path": o("E01_move.skp"), "out_path": o("E02_move2.skp"), "ops": [
        {"op": "move", "target": {"name": "SUITE 02 · Cama"}, "by_m": [0.10, -0.05, 0.0]}]},
        lambda r: ("PASS", "salvo") if r["status"] == "OK" else ("FAIL", r.get("reason")))
    i2 = nodes_of(await inspect(OUT / "E02_move2.skp"))
    ok = approx(bb(i2["SUITE 02 · Cama"])["min"], [bb(cama)["min"][0] + 0.20, bb(cama)["min"][1] - 0.10, bb(cama)["min"][2]])
    RESULTS.append({"id": "E02r", "verdict": "PASS" if ok else "FAIL",
                    "why": f"move relativo reaplicado ACUMULA (esperado 2x): {bb(i2['SUITE 02 · Cama'])['min']}"})
    print("E02r", RESULTS[-1]["verdict"], RESULTS[-1]["why"])

    await run("E03", "su_apply_edits", {"skp_path": rel(BASE), "out_path": o("E03_rot.skp"), "ops": [
        {"op": "rotate", "target": {"name": "SUITE 02 · Criado-mudo 1"}, "degrees": 90}]},
        lambda r: ("PASS", "salvo") if r["status"] == "OK" else ("FAIL", r.get("reason")))
    i3 = nodes_of(await inspect(OUT / "E03_rot.skp"))
    a, b = bb(cr1), bb(i3["SUITE 02 · Criado-mudo 1"])
    ca = [(a["min"][k] + a["max"][k]) / 2 for k in range(3)]
    cb = [(b["min"][k] + b["max"][k]) / 2 for k in range(3)]
    ok = approx(ca, cb) and approx([a["size"][0], a["size"][1], a["size"][2]], [b["size"][1], b["size"][0], b["size"][2]])
    RESULTS.append({"id": "E03r", "verdict": "PASS" if ok else "FAIL",
                    "why": f"rotate 90 no centro: size {a['size']} -> {b['size']}, centro {ca} -> {cb}"})
    print("E03r", RESULTS[-1]["verdict"], RESULTS[-1]["why"])

    tex = rel(REPO / "assets/textures/procedural/wood_dark.png")
    await run("E04", "su_apply_edits", {"skp_path": rel(BASE), "out_path": o("E04_appearance.skp"), "ops": [
        {"op": "set_material", "target": {"name": "SUITE 02 · Guarda-roupa"}, "color": [200, 30, 30]},
        {"op": "set_material", "target": {"name": "SUITE 02 · Escrivaninha"}, "texture": tex, "texture_size_m": 0.6},
        {"op": "set_tag", "target": {"name": "SUITE 02 · rug"}, "tag": "L2_TESTE"},
        {"op": "set_hidden", "target": {"name": "SUITE 02 · Cadeira escrivaninha"}, "hidden": True},
        {"op": "set_material", "target": {"name": "PlanShell_Group"}, "color": [90, 90, 90]},
        {"op": "rename", "target": {"name": "SUITE 02 · Criado-mudo 2"}, "name": "SUITE 02 · Criado-mudo B"}]},
        lambda r: ("PASS", "salvo") if r["status"] == "OK" else ("FAIL", r.get("reason")))
    ir = await inspect(OUT / "E04_appearance.skp")
    i4 = nodes_of(ir)
    mats = {m["name"]: m for m in ir["result"]["materials"]}
    checks = {
        "cor": i4["SUITE 02 · Guarda-roupa"]["material"] == "skmcp_rgb_200_30_30" and mats["skmcp_rgb_200_30_30"]["rgb"] == [200, 30, 30],
        "textura": (mats.get(i4["SUITE 02 · Escrivaninha"]["material"] or "", {}).get("texture") == "wood_dark.png"),
        "tag": i4["SUITE 02 · rug"]["tag"] == "L2_TESTE",
        "hidden": i4["SUITE 02 · Cadeira escrivaninha"]["hidden"] is True,
        "shell_material_permitido": i4["PlanShell_Group"]["material"] == "skmcp_rgb_90_90_90",
        "shell_geometria_intacta": approx(bb(i4["PlanShell_Group"])["min"], bb(shell)["min"]) and approx(bb(i4["PlanShell_Group"])["max"], bb(shell)["max"]),
        "rename": "SUITE 02 · Criado-mudo B" in i4 and "SUITE 02 · Criado-mudo 2" not in i4,
    }
    RESULTS.append({"id": "E04r", "verdict": "PASS" if all(checks.values()) else "FAIL", "why": checks})
    print("E04r", RESULTS[-1]["verdict"], checks)

    # setter reaplicado = mesmo estado; sem material duplicado
    await run("E05", "su_apply_edits", {"skp_path": o("E04_appearance.skp"), "out_path": o("E05_reapply.skp"), "ops": [
        {"op": "set_material", "target": {"name": "SUITE 02 · Guarda-roupa"}, "color": [200, 30, 30]},
        {"op": "set_tag", "target": {"name": "SUITE 02 · rug"}, "tag": "L2_TESTE"},
        {"op": "set_hidden", "target": {"name": "SUITE 02 · Cadeira escrivaninha"}, "hidden": True}]},
        lambda r: ("PASS", "salvo") if r["status"] == "OK" else ("FAIL", r.get("reason")))
    ir5 = await inspect(OUT / "E05_reapply.skp")
    i5 = nodes_of(ir5)
    same = all(i5[k]["material"] == i4[k]["material"] and i5[k]["tag"] == i4[k]["tag"] and i5[k]["hidden"] == i4[k]["hidden"]
               for k in ("SUITE 02 · Guarda-roupa", "SUITE 02 · rug", "SUITE 02 · Cadeira escrivaninha"))
    nm4, nm5 = ir["result"]["counts"]["materials"], ir5["result"]["counts"]["materials"]
    nt4, nt5 = ir["result"]["counts"]["tags"], ir5["result"]["counts"]["tags"]
    RESULTS.append({"id": "E05r", "verdict": "PASS" if same and nm4 == nm5 and nt4 == nt5 else "FAIL",
                    "why": f"setters idempotentes: estado igual={same}; materiais {nm4}->{nm5}; tags {nt4}->{nt5}"})
    print("E05r", RESULTS[-1]["verdict"], RESULTS[-1]["why"])

    await run("E06", "su_apply_edits", {"skp_path": rel(BASE), "out_path": o("E06_insert.skp"), "ops": [
        {"op": "insert_component", "skp_path": rel(SOFA), "position_m": [1.0, 1.5, 0.0], "rotation_deg": 90,
         "name": "L2 sofa inserido", "tag": "L2_TESTE"}]},
        lambda r: ("PASS", "salvo") if r["status"] == "OK" else ("FAIL", r.get("reason")))
    i6r = await inspect(OUT / "E06_insert.skp")
    i6 = nodes_of(i6r)
    s = i6.get("L2 sofa inserido")
    ok = bool(s) and s["type"] == "component" and s["tag"] == "L2_TESTE" and approx(s["world_origin_m"], [1.0, 1.5, 0.0], 0.001)
    RESULTS.append({"id": "E06r", "verdict": "PASS" if ok else "FAIL",
                    "why": f"inserido: {s and {k: s[k] for k in ('type', 'tag', 'world_origin_m', 'definition')}}"})
    print("E06r", RESULTS[-1]["verdict"], RESULTS[-1]["why"])

    # ---------------- negativos ----------------
    def refused(expect_status=("ERROR", "REFUSED", "FAILED"), out=None):
        def chk(r):
            st = r.get("status")
            no_out = out is None or not Path(out).exists()
            okk = st in expect_status and no_out and sha(BASE) == base_hash
            return ("PASS" if okk else "FAIL"), f"status={st} saída_ausente={no_out} base_intacta={sha(BASE) == base_hash} :: {str(r.get('reason') or r.get('errors') or (r.get('result') or {}).get('error'))[:160]}"
        return chk

    neg = [
        ("N01", [{"op": "move", "target": {"name": "Nao Existe"}, "by_m": [0.1, 0, 0]}], "alvo inexistente"),
        ("N02", [{"op": "move", "target": {"name_contains": "Criado-mudo"}, "by_m": [0.1, 0, 0]}], "alvo ambíguo expect=one"),
        ("N03", [{"op": "move", "target": {"name": "PlanShell_Group"}, "by_m": [0.1, 0, 0]}], "move arquitetura por nome (validador)"),
        ("N04", [{"op": "move", "target": {"persistent_id": shell["pid"]}, "by_m": [0.1, 0, 0]}], "move arquitetura por persistent_id (guarda Ruby)"),
        ("N05", [{"op": "rotate", "target": {"name_contains": "Shell"}, "degrees": 5}], "rotate arquitetura por name_contains"),
        ("N06", [{"op": "delete", "target": {"name_contains": "Floor_Group"}}], "delete piso"),
        ("N07", [{"op": "rename", "target": {"name_contains": "WindowGlass"}, "name": "janela livre"}], "rename janela"),
        ("N08", [{"op": "rename", "target": {"name": "SUITE 02 · Cama"}, "name": "PlanShell_fake"}], "rename móvel p/ nome reservado"),
        ("N09", [{"op": "move", "target": {"name": "SUITE 02 · Cama"}}], "move sem by_m"),
        ("N10", [{"op": "set_material", "target": {"name": "SUITE 02 · Cama"}, "color": [300, 0, 0]}], "cor fora de 0-255"),
        ("N11", [{"op": "explode", "target": {"name": "SUITE 02 · Cama"}}], "op desconhecida"),
        ("N12", [{"op": "set_hidden", "target": {"name": "SUITE 02 · Cama"}, "hidden": True}] * 201, "201 ops"),
        ("N13", [{"op": "insert_component", "skp_path": rel(ARCH), "position_m": [0, 0, 0]}], "insert .skp que traz arquitetura"),
        ("N14", [{"op": "set_material", "target": {"name": "SUITE 02 · Cama"}, "color": [1, 2, 3]},
                 {"op": "move", "target": {"name": "SUITE 02 · Guarda-roupa"}, "by_m": [0.2, 0, 0]},
                 {"op": "move", "target": {"name": "Nao Existe"}, "by_m": [0.1, 0, 0]}], "lote falha no meio: atômico"),
        ("N15", [{"op": "move", "target": {"name_contains": "criado", "expect": "all"}, "by_m": [0.1, 0, 0]}],
         "alvo casa o móvel E a peça dentro dele (dupla translação)"),
    ]
    for tid, ops, what in neg:
        out = OUT / f"{tid}.skp"
        await run(tid, "su_apply_edits", {"skp_path": rel(BASE), "out_path": rel(out), "ops": ops}, refused(out=out))
        RESULTS[-1]["what"] = what

    await run("N16", "su_apply_edits", {"skp_path": "runs/nao_existe.skp", "out_path": o("N16.skp"),
                                        "ops": [{"op": "set_hidden", "target": {"name": "x"}, "hidden": True}]}, refused(out=OUT / "N16.skp"))
    await run("N17", "su_apply_edits", {"skp_path": rel(BASE), "out_path": "fixtures/quadrado/L2_nao_pode.skp",
                                        "ops": [{"op": "set_hidden", "target": {"name": "SUITE 02 · Cama"}, "hidden": True}]},
              refused(out=REPO / "fixtures/quadrado/L2_nao_pode.skp"))
    await run("N18", "su_apply_edits", {"skp_path": rel(BASE), "out_path": "artifacts/planta_74/L2_nao_pode.skp",
                                        "ops": [{"op": "set_hidden", "target": {"name": "SUITE 02 · Cama"}, "hidden": True}]},
              refused(out=REPO / "artifacts/planta_74/L2_nao_pode.skp"))
    e01_hash = sha(OUT / "E01_move.skp")
    await run("N19", "su_apply_edits", {"skp_path": rel(BASE), "out_path": o("E01_move.skp"),
                                        "ops": [{"op": "set_hidden", "target": {"name": "SUITE 02 · Cama"}, "hidden": True}]},
              lambda r: (("PASS" if r.get("status") == "REFUSED" and sha(OUT / "E01_move.skp") == e01_hash else "FAIL"),
                         f"destino existente: status={r.get('status')} intacto={sha(OUT / 'E01_move.skp') == e01_hash}"))
    await run("N20", "su_apply_edits", {"skp_path": rel(BASE), "out_path": rel(BASE),
                                        "ops": [{"op": "set_hidden", "target": {"name": "SUITE 02 · Cama"}, "hidden": True}]},
              lambda r: (("PASS" if r.get("status") == "REFUSED" and sha(BASE) == base_hash else "FAIL"),
                         f"destino = entrada: status={r.get('status')}"))
    await run("N21", "su_inspect", {"skp_path": "runs/nao_existe.skp"},
              lambda r: (("PASS" if r.get("status") == "ERROR" else "FAIL"), f"status={r.get('status')} {r.get('reason')}"))
    await run("N22", "su_render", {"skp_path": rel(BASE), "views": [{"preset": "diagonal"}]},
              lambda r: (("PASS" if r.get("status") == "ERROR" else "FAIL"), f"preset inválido: {r.get('reason')}"))
    await run("N23", "su_close", {"pid": 999999},
              lambda r: (("PASS" if r.get("status") == "ERROR" else "FAIL"), f"pid que não é SketchUp: {r.get('reason')}"))
    await run("N24", "su_close", {"all_instances": True},
              lambda r: (("PASS" if r.get("status") in ("NOTHING_TO_CLOSE", "CONFIRMATION_REQUIRED") else "FAIL"),
                         f"sem confirm não fecha: {r.get('status')} {r.get('would_close')}"))
    await run("N25", "su_render_vray", {"scene_dir": "runs/x"},
              lambda r: (("PASS" if r.get("status") == "REFUSED" else "FAIL"), "recusa com motivo"))
    for f in (REPO / "fixtures/quadrado/L2_nao_pode.skp", REPO / "artifacts/planta_74/L2_nao_pode.skp"):
        assert not f.exists(), f
    (OUT / "suite.json").write_text(json.dumps(RESULTS, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print("BASE intacta:", sha(BASE) == base_hash)
    print("TOTAL", len(RESULTS), "PASS", sum(r["verdict"] == "PASS" for r in RESULTS),
          "FAIL", [r["id"] for r in RESULTS if r["verdict"] != "PASS"])


asyncio.run(main())
