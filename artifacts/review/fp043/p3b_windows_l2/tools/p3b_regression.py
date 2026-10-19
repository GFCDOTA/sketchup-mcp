"""P3b-02/03: operacoes POSITIVAS das su_* pelo cliente MCP real (stdio, 1 sessao) + modelos regressivos quadrado/planta_74.
uso (cwd = repo, PT_TO_M=0.0259 no ambiente do servidor): p3b_regression.py <saida_dir>
Nada canonico e substituido: tudo sai em runs/. Cada SketchUp subido e fechado pelo PID devolvido."""
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path.cwd().resolve()
OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
CANON = REPO / "artifacts/planta_74"
SC = Path(__file__).resolve().parent
summary = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "steps": [], "pids": []}
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731


def alive(pid):
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
    return f'"{pid}"' in out


def rec(name, ok, **data):
    summary["steps"].append({"step": name, "ok": bool(ok), **data})
    print(("PASS " if ok else "FAIL ") + name, json.dumps(data, default=str)[:260], flush=True)


def dump(name, obj):
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def strip_paths(x):
    if isinstance(x, dict):
        return {k: strip_paths(v) for k, v in x.items() if k not in ("consensus_path", "shell_json_path", "generated_at", "skp_path", "out_path", "path")}
    if isinstance(x, list):
        return [strip_paths(v) for v in x]
    return x


canon_before = {p.name: sha(p) for p in (CANON / "planta_74.skp", CANON / "geometry_report.json", CANON / "furnished/planta_74_furnished.skp")}


async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "tools.mcp_server.server"], cwd=str(REPO),
                                   env={**os.environ, "PYTHONPATH": str(REPO), "PT_TO_M": "0.0259"})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            async def call(name, args, t=900):
                res = await s.call_tool(name, args, read_timeout_seconds=timedelta(seconds=t))
                txt = res.content[0].text if res.content else ""
                try:
                    out = json.loads(txt)
                except ValueError:
                    out = {"_raw": txt}
                if isinstance(out, dict) and out.get("pid"):
                    summary["pids"].append(int(out["pid"]))
                    await s.call_tool("su_close", {"pid": int(out["pid"]), "force": True, "confirm": True})
                return out, bool(res.isError)

            tools = [t.name for t in (await s.list_tools()).tools]
            rec("tools_listed", len(tools) == 18, count=len(tools))
            st, _ = await call("su_status", {})
            dump("su_status", st)
            rec("su_status", bool(st.get("proof_state")) and st.get("server_job") is not None, instances=len(st.get("instances", [])), job=st.get("server_job"))

            # ---------------- planta_74: shell reconstruido (NAO substitui o canonico)
            pl = OUT / "planta" / "model.skp"
            b, err = await call("su_build_shell", {"out_path": str(pl), "force": True})
            dump("planta_build", b)
            rep = json.loads((pl.parent / "geometry_report.json").read_text("utf-8")) if (pl.parent / "geometry_report.json").exists() else None
            same_report = rep is not None and strip_paths(rep) == strip_paths(json.loads((CANON / "geometry_report.json").read_text("utf-8")))
            rec("planta_build_ok_and_report_equals_approved", b.get("status") == "OK" and same_report and pl.exists(), status=b.get("status"), same_report=same_report)
            gates = subprocess.run([sys.executable, "-m", "tools.run_deterministic_gates", "--fixture", "planta_74", "--report", str(pl.parent / "geometry_report.json")],
                                   capture_output=True, text=True, env={**os.environ, "PT_TO_M": "0.0259", "PYTHONPATH": str(REPO)})
            rec("planta_gates_with_report", "overall=PASS" in gates.stdout, tail=gates.stdout.strip().splitlines()[-7:])

            # ---------------- su_inspect do reconstruido x inspect aprovado (L2 FP-042 P01)
            ins, _ = await call("su_inspect", {"skp_path": str(pl), "max_depth": 3})
            dump("planta_inspect", ins)
            ref = json.loads((REPO / "artifacts/review/l2_fp042_20261019/P01_planta74_shell/inspect.json").read_text("utf-8"))["result"]
            key = lambda n: (n["path"], tuple(round(v, 3) for v in n["bbox_world_m"]["min"] + n["bbox_world_m"]["max"]))  # noqa: E731
            now = sorted(key(n) for n in ins["result"]["nodes"])
            old = sorted(key(n) for n in ref["nodes"])
            rec("planta_inspect_equals_approved_nodes", ins.get("status") == "OK" and now == old, nodes=len(now), bbox_m=ins["result"]["bbox_m"]["size"])

            # ---------------- su_render com preset valido: arquivo existe e tem conteudo
            rr, _ = await call("su_render", {"skp_path": str(pl), "views": [{"preset": "top"}, {"preset": "iso"}], "width": 1200, "height": 900,
                                             "out_dir": str(OUT / "render")})
            dump("render", rr)
            from PIL import Image
            imgs = []
            for v in (rr.get("result") or {}).get("views", []):
                p = Path(v.get("file") or v.get("path") or "")
                if p.exists():
                    im = Image.open(p).convert("RGB")
                    imgs.append({"file": p.name, "bytes": p.stat().st_size, "size": im.size, "colors": len(set(im.resize((64, 64)).getdata()))})
            rec("su_render_valid_preset_files_and_content", rr.get("status") == "OK" and len(imgs) == 2 and all(i["bytes"] > 10000 and i["colors"] > 5 for i in imgs), images=imgs)
            bad, _ = await call("su_render", {"skp_path": str(pl), "views": [{"preset": "nao_existe"}]})
            rec("su_render_invalid_preset_refused", bad.get("status") == "ERROR", status=bad.get("status"))

            # ---------------- su_furnish integrado
            fo = OUT / "furnish"
            fr, _ = await call("su_furnish", {"base_skp": str(pl), "out_dir": str(fo)})
            dump("furnish", fr)
            rec("su_furnish_integrated", fr.get("status") == "OK" and fr.get("boxes") == 402, status=fr.get("status"), boxes=fr.get("boxes"))
            furnished = Path((fr.get("files") or {}).get("skp") or fo / "planta_74_furnished.skp")
            fo = furnished.parent
            furnished_sha0 = sha(furnished)
            fins, _ = await call("su_inspect", {"skp_path": str(furnished), "max_depth": 3})
            dump("furnished_inspect", fins)
            rec("furnished_reopened_inspected", fins.get("status") == "OK", nodes=len(fins["result"]["nodes"]))

            # ---------------- su_apply_edits (positivo em movel; recusa em arquitetura)
            nodes = fins["result"]["nodes"]
            sofa = next((n for n in nodes if "sofa" in n["path"].lower() or "sofá" in n["path"].lower()), None) or next(n for n in nodes if " · " in n["path"] and not n["protected"])
            ed_out = OUT / "edits" / "edited.skp"
            ed, _ = await call("su_apply_edits", {"skp_path": str(furnished), "out_path": str(ed_out), "ops": [
                {"op": "set_tag", "target": {"persistent_id": sofa["pid"]}, "tag": "P3B_TESTE"},
                {"op": "move", "target": {"persistent_id": sofa["pid"]}, "by_m": [0.1, 0.0, 0.0]},
                {"op": "set_material", "target": {"persistent_id": sofa["pid"]}, "color": [200, 30, 30]}]})
            dump("apply_edits", ed)
            ei, _ = await call("su_inspect", {"skp_path": str(ed_out), "max_depth": 3})
            moved = next((n for n in ei["result"]["nodes"] if n["pid"] == sofa["pid"]), None)
            dx = round(moved["bbox_world_m"]["min"][0] - sofa["bbox_world_m"]["min"][0], 3) if moved else None
            rec("su_apply_edits_move_tag_material_reopened", ed.get("status") == "OK" and dx == 0.1 and moved["tag"] == "P3B_TESTE" and moved["material"],
                status=ed.get("status"), dx_m=dx, tag=moved and moved["tag"], material=moved and moved["material"], original_intact=sha(furnished) == furnished_sha0)
            shell_node = next(n for n in nodes if n["protected"])
            arch, _ = await call("su_apply_edits", {"skp_path": str(furnished), "out_path": str(OUT / "edits" / "arch.skp"),
                                                    "ops": [{"op": "delete", "target": {"persistent_id": shell_node["pid"]}}]})
            refusal = str((arch.get("result") or {}).get("error") or arch.get("reason"))
            archp = OUT / "edits" / "arch.skp"
            marker = archp.with_name(archp.name + ".NOT_A_RESULT.txt")
            rec("su_apply_edits_architecture_refused", arch.get("status") in ("FAILED", "REFUSED", "ERROR") and "Hard Rule #1" in refusal
                and (not archp.exists() or marker.exists()), status=arch.get("status"), reason=refusal[:140],
                unedited_copy="removed" if not archp.exists() else "left_with_NOT_A_RESULT_marker")

            # ---------------- su_open (janela mantida de proposito) + su_close so por PID
            scratch = OUT / "open_me.skp"
            shutil.copy2(pl, scratch)
            op = json.loads((await s.call_tool("su_open", {"skp_path": str(scratch)}, read_timeout_seconds=timedelta(seconds=120))).content[0].text)
            import time
            time.sleep(6)
            rec("su_open_keeps_window_open", op.get("status") == "OPENED" and alive(op["pid"]), pid=op.get("pid"), outside_job=op.get("outside_job"))
            cl = json.loads((await s.call_tool("su_close", {"pid": op["pid"], "force": True, "confirm": True})).content[0].text)
            time.sleep(2)
            rec("su_close_by_pid", cl.get("status") == "CLOSED" and not alive(op["pid"]), close_result=cl)
            refused = json.loads((await s.call_tool("su_close", {"all_instances": True})).content[0].text)
            rec("su_close_all_without_confirm_refused", refused.get("status") == "CONFIRMATION_REQUIRED")

            # ---------------- su_render_vray (se instalado)
            vray_ok = bool((st.get("vray") or {}).get("installed", st.get("vray_exe"))) if isinstance(st.get("vray"), dict) else None
            scene = Path("E:/Claude/apps/sketchup-mcp/runs/scenes/living_room_black_wood_gold_boutique")
            if scene.exists():
                vr, _ = await call("su_render_vray", {"scene_dir": str(scene), "width": 800, "height": 600}, t=900)
                dump("vray", vr)
                png = Path(vr.get("png") or "")
                rec("su_render_vray", vr.get("status") == "OK" and png.exists() and png.stat().st_size > 10000, status=vr.get("status"), png_bytes=png.stat().st_size if png.exists() else None,
                    reason=vr.get("reason"), vray_in_status=st.get("vray"))
            else:
                rec("su_render_vray", True, skipped="cena de referencia ausente nesta maquina")

            # ---------------- quadrado
            qd = OUT / "quadrado" / "model.skp"
            qb, _ = await call("su_build_shell", {"consensus_path": "fixtures/quadrado/consensus_with_window.json", "out_path": str(qd), "force": True})
            dump("quadrado_build", qb)
            qrep_p = qd.parent / "geometry_report.json"
            qrep = json.loads(qrep_p.read_text("utf-8")) if qrep_p.exists() else {}
            qg = subprocess.run([sys.executable, "-m", "tools.run_deterministic_gates", "--fixture", "quadrado", "--report", str(qrep_p)], capture_output=True, text=True,
                                env={k: v for k, v in os.environ.items() if k != "PT_TO_M"} | {"PYTHONPATH": str(REPO)})
            rec("quadrado_build_ok_and_gates", qb.get("status") == "OK" and "overall=PASS" in qg.stdout, status=qb.get("status"), tail=qg.stdout.strip().splitlines()[-7:])
            qi, _ = await call("su_inspect", {"skp_path": str(qd), "max_depth": 3})
            dump("quadrado_inspect", qi)
            size = qi["result"]["bbox_m"]["size"]
            base_q = json.loads((REPO / "artifacts/review/l2_fp042_20261019/S01_quadrado_shell/inspect.json").read_text("utf-8"))["result"]["bbox_m"]
            same_q = all(abs(a - b) < 1e-4 for a, b in zip(qi["result"]["bbox_m"]["min"] + qi["result"]["bbox_m"]["max"], base_q["min"] + base_q["max"]))
            rec("quadrado_reopened_scale_correct_and_equals_l2_baseline", qi.get("status") == "OK" and abs(size[0] - 4.19) < 0.01 and same_q, bbox_size_m=size,
                equals_fp042_l2_baseline=same_q, note="largura 4,19 m = 4,00 m livre + parede: escala padrao do quadrado (0,0352), nao a da planta_74; a janela sai ~5,7 cm da face sul (D-001)")
            # copia do quadrado para os testes condicionais de abertura 3D (D-001: divergencia transparente)
            qv3 = REPO / "runs" / "quadrado_v3_aperture"
            qv3.mkdir(parents=True, exist_ok=True)
            for n in ("geometry_report.json", "_shell_polygon.json"):
                if (qd.parent / n).exists():
                    shutil.copy2(qd.parent / n, qv3 / n)


asyncio.run(main())

# ---------------- controle negativo: modelo com fator de escala ERRADO deve reprovar no gate de escala independente
wrong = Path("E:/Claude/apps/sketchup-mcp/runs/l2_fp042_20261019/S01a_quadrado_shell_WRONG_SCALE/geometry_report.json")
if wrong.exists():
    neg = subprocess.run([sys.executable, "-m", "tools.run_deterministic_gates", "--fixture", "quadrado", "--report", str(wrong)], capture_output=True, text=True,
                         env={**{k: v for k, v in os.environ.items() if k != "PT_TO_M"}, "PYTHONPATH": str(REPO)})
    rec("scale_anchor_independent_rejects_wrong_scale_model", "scale_anchor: FAIL" in neg.stdout or "scale_anchor" in neg.stdout and "overall=FAIL" in neg.stdout,
        tail=neg.stdout.strip().splitlines()[-7:])

summary["canonical_before"] = canon_before
summary["canonical_after"] = {p.name: sha(p) for p in (CANON / "planta_74.skp", CANON / "geometry_report.json", CANON / "furnished/planta_74_furnished.skp")}
summary["canonical_intact"] = canon_before == summary["canonical_after"]
rec("canonicals_intact", summary["canonical_intact"], files=list(canon_before))
summary["ok"] = all(x["ok"] for x in summary["steps"])
dump("summary", summary)
print("TOTAL", len(summary["steps"]), "ok=", summary["ok"], flush=True)
