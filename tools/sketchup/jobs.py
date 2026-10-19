"""Os verbos do especialista em SketchUp — o que vira tool `su_*` no MCP.

Cada função devolve um dict com `status`, nunca levanta para o chamador:
erro é dado (UNAVAILABLE / ERROR / FAILED / TIMEOUT / SU_EXITED), com o
motivo real. Nada aqui inventa sucesso: "o SketchUp abriu" não é "o job rodou",
e "o job rodou" só vale com o JSON de resultado na mão.

Quem decide estética não é este módulo: build/furnish/render mudam APARÊNCIA,
e o veredito IMPROVED/SAME/WORSE é do Felipe (VISUAL_REVIEW). O resultado
lembra isso em `visual_review`.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from tools.sketchup import paths
from tools.sketchup.batch import RUBY_DIR, resolve_mode, run_job, run_script
from tools.sketchup.ops import OpsInvalid, protection_params, validate
from tools.sketchup.process import SketchUp

REPO = paths.REPO_ROOT
CONSENSUS_DEFAULT = REPO / "fixtures" / "planta_74" / "consensus_with_human_walls_and_soft_barriers.json"
BASE_SKP_DEFAULT = REPO / "artifacts" / "planta_74" / "planta_74.skp"
PRESETS = ("top", "iso", "front", "back", "left", "right")
VISUAL_REVIEW = ("mudança de APARÊNCIA: o veredito IMPROVED/SAME/WORSE é do Felipe "
                 "(VISUAL_REVIEW) — nunca automático")
# Estado de prova das su_* que sobem o SketchUp: testadas só contra um dublê de
# Windows+SketchUp. Nenhuma rodou num SketchUp real ainda — quem consome (agente,
# harness) não pode tratá-las como capacidade comprovada. Muda só com evidência
# de um run real commitada em artifacts/review/.
PROOF_STATE = "UNVERIFIED_ON_SKETCHUP"


def _su(su: SketchUp | None) -> SketchUp:
    return su or SketchUp()


def _skp_in(skp_path: str | None) -> tuple[Path | None, dict | None]:
    if not skp_path:
        return None, {"status": "ERROR", "reason": "skp_path é obrigatório"}
    p = paths.resolve(skp_path)
    if p.suffix.lower() != ".skp" or not p.exists():
        return None, {"status": "ERROR", "reason": f"não é um .skp existente: {p}"}
    return p, None


def _working_copy(src: Path, dst: Path) -> Path:
    """O SketchUp abre a CÓPIA, nunca o original. No modo interactive a janela
    fica aberta depois do job: se fosse o original (às vezes o .skp canônico em
    artifacts/), um Ctrl+S do Felipe gravaria por cima a edição/os grupos
    escondidos. Com a cópia, o original nem chega a ser aberto."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def _out_dir(out_dir: str | None, job: str, *, inputs=()) -> tuple[Path | None, dict | None]:
    try:
        d = paths.check_output(out_dir, inputs=inputs) if out_dir else paths.default_out_dir(job)
    except paths.OutputPathRefused as e:
        return None, {"status": "REFUSED", "reason": str(e)}
    return d, None


# -- ciclo de vida ----------------------------------------------------------

def status(su: SketchUp | None = None) -> dict[str, Any]:
    su = _su(su)
    out = su.status()
    out["ruby_jobs"] = sorted(p.stem for p in RUBY_DIR.glob("*.rb") if not p.stem.startswith("skmcp_"))
    out["default_mode"] = resolve_mode()
    out["proof_state"] = PROOF_STATE
    out["status"] = "OK"
    return out


def open_model(skp_path: str, su: SketchUp | None = None) -> dict[str, Any]:
    p, err = _skp_in(skp_path)
    return err or _su(su).open(p)


def close(*, pid: int | None = None, all_instances: bool = False, force: bool = False,
          confirm: bool = False, su: SketchUp | None = None) -> dict[str, Any]:
    return _su(su).close(pid=pid, all_instances=all_instances, force=force, confirm=confirm)


# -- inspeção / render / edição (jobs Ruby versionados) ----------------------

def inspect_model(skp_path: str, *, max_depth: int = 2, out_dir: str | None = None,
                  mode: str | None = None, timeout_s: int = 180,
                  su: SketchUp | None = None) -> dict[str, Any]:
    p, err = _skp_in(skp_path)
    if err:
        return err
    d, err = _out_dir(out_dir, "inspect")
    if err:
        return err
    # mesmo sendo só leitura: em modo interactive a janela fica aberta, e um
    # Ctrl+S no original (às vezes o canônico) o regravaria — até convertendo a
    # versão do arquivo. O SketchUp abre a cópia.
    copy = _working_copy(p, d / f"_inspect_{p.name}")
    res = run_job(_su(su), "inspect_model", out_dir=d, skp_in=copy, timeout_s=timeout_s, mode=mode,
                  params={"max_depth": max_depth, **protection_params()})
    res["input_skp"] = str(p)
    return res


def _check_views(views: list[dict] | None) -> str | None:
    if views is None:
        return None
    if not isinstance(views, list) or not views:
        return "views precisa ser uma lista não vazia"
    for i, v in enumerate(views):
        if not isinstance(v, dict):
            return f"views[{i}] precisa ser objeto"
        if "preset" in v:
            if v["preset"] not in PRESETS:
                return f"views[{i}].preset inválido: {v['preset']!r} (válidos: {', '.join(PRESETS)})"
        else:
            for k in ("eye_m", "target_m"):
                c = v.get(k)
                if not (isinstance(c, (list, tuple)) and len(c) == 3
                        and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in c)):
                    return f"views[{i}] precisa de preset OU eye_m+target_m [x,y,z] em metros"
    return None


def render_views(skp_path: str, *, views: list[dict] | None = None, width: int = 1600,
                 height: int = 1200, hide_contains: list[str] | None = None,
                 focus_contains: str | None = None, out_dir: str | None = None,
                 mode: str | None = None, timeout_s: int = 240,
                 su: SketchUp | None = None) -> dict[str, Any]:
    p, err = _skp_in(skp_path)
    if err:
        return err
    bad = _check_views(views)
    if bad:
        return {"status": "ERROR", "reason": bad}
    if not (100 <= width <= 8000 and 100 <= height <= 8000):
        return {"status": "ERROR", "reason": "width/height entre 100 e 8000 px"}
    d, err = _out_dir(out_dir, "render")
    if err:
        return err
    params: dict[str, Any] = {"width": width, "height": height,
                              "hide_contains": hide_contains or [], "defer_s": 5}
    if views:
        params["views"] = views
    if focus_contains:
        params["focus_contains"] = focus_contains
    copy = _working_copy(p, d / f"_render_{p.name}")  # esconder grupos marca o modelo como modificado
    res = run_job(_su(su), "render_views", out_dir=d, skp_in=copy, timeout_s=timeout_s,
                  mode=mode, params=params)
    res["input_skp"] = str(p)
    if res.get("status") == "OK" and not res["result"].get("all_ok", False):
        res["status"] = "PARTIAL"  # alguma vista falhou: o resultado diz qual
    return res


def apply_edits(skp_path: str, ops: list[dict], *, out_path: str | None = None,
                mode: str | None = None, timeout_s: int = 240,
                su: SketchUp | None = None) -> dict[str, Any]:
    p, err = _skp_in(skp_path)
    if err:
        return err
    try:
        norm = validate(ops)
    except OpsInvalid as e:
        return {"status": "ERROR", "reason": "ops inválidas", "errors": e.errors}
    if out_path:
        try:
            out = paths.check_output(out_path, inputs=(p,))
        except paths.OutputPathRefused as e:
            return {"status": "REFUSED", "reason": str(e)}
        if out.suffix.lower() != ".skp":
            return {"status": "ERROR", "reason": f"out_path precisa terminar em .skp: {out}"}
        d = out.parent
    else:
        d = paths.default_out_dir("edit")
        out = d / f"{p.stem}_edited.skp"
    if out.exists():
        # a cópia o sobrescreveria, e uma falha depois o apagaria — destruindo um
        # arquivo que este job nunca criou
        return {"status": "REFUSED",
                "reason": f"out_path já existe ({out}); a edição sai sempre em arquivo novo"}
    _working_copy(p, out)
    # a cópia já existe, então existir não prova nada: a prova é o Ruby ter
    # salvo DEPOIS da cópia (mtime) e ter dito saved=true
    copied_at = out.stat().st_mtime_ns
    res = run_job(_su(su), "apply_edits", out_dir=d, skp_in=out, timeout_s=timeout_s, mode=mode,
                  params={"ops": norm, **protection_params()})
    res["input_skp"] = str(p)
    res["out_skp"] = str(out)
    if res.get("status") == "OK":
        saved = res["result"].get("saved") is True and out.stat().st_mtime_ns > copied_at
        if not saved:
            res.update(status="FAILED",
                       reason=f"o job disse ok mas {out} não foi regravado depois da cópia")
    else:
        _discard_unedited(out, res)
    return res


def _discard_unedited(out: Path, res: dict[str, Any]) -> None:
    """Cópia sem edição não pode parecer resultado. No modo interactive o SketchUp
    que recusou o lote AINDA tem a cópia aberta: no Windows o unlink falha
    (WinError 32) e antes estourava como erro da tool, deixando a cópia intacta
    no destino (L2 2026-10-19). Agora a recusa original é devolvida e a cópia
    ganha um marcador ao lado dizendo que NÃO é resultado."""
    try:
        out.unlink(missing_ok=True)
    except OSError as e:
        marker = out.with_name(out.name + ".NOT_A_RESULT.txt")
        marker.write_text(f"{out.name} é a cópia NÃO editada (o lote falhou: "
                          f"{res.get('reason') or (res.get('result') or {}).get('error')}). "
                          f"Ainda aberta no SketchUp PID {res.get('pid')}; apague depois de fechar.\n",
                          encoding="utf-8")
        res["unedited_copy_left_open"] = str(out)
        res["unedited_copy_marker"] = str(marker)
        res["cleanup_error"] = f"{type(e).__name__}: {e}"


# -- pipeline pesado (reuso dos launchers existentes) -------------------------

def build_shell(consensus_path: str | None = None, *, out_path: str | None = None,
                force: bool = False, mode: str | None = None, timeout_s: int = 240,
                su: SketchUp | None = None) -> dict[str, Any]:
    """consensus → shell .skp via `build_plan_shell_skp.run` + gates determinísticos.

    Nunca promove: o resultado vai para runs/; `promote_canonical` é o passo
    seguinte, depois dos gates e do VISUAL_REVIEW."""
    su = _su(su)
    why = su.unavailable()
    if why:
        return {"status": "UNAVAILABLE", "reason": why}
    if not su.system.exists(su.loc.plugins_dir / "autorun_consume.rb"):
        return {"status": "UNAVAILABLE",
                "reason": (f"o build do shell usa o plugin autorun_consume.rb, que não está em "
                           f"{su.loc.plugins_dir} (ele não é versionado no repo)")}
    con = paths.resolve(consensus_path) if consensus_path else CONSENSUS_DEFAULT
    if not con.exists():
        return {"status": "ERROR", "reason": f"consensus não encontrado: {con}"}
    try:
        out = (paths.check_output(out_path, inputs=(con,)) if out_path
               else paths.default_out_dir("build_shell") / "model.skp")
    except paths.OutputPathRefused as e:
        return {"status": "REFUSED", "reason": str(e)}
    try:
        mode = resolve_mode(mode)
    except ValueError as e:
        return {"status": "ERROR", "reason": str(e)}
    from tools import build_plan_shell_skp as bps  # shapely: só quando precisa

    res = bps.run(con, out, sketchup_exe=su.loc.exe, plugins_dir=su.loc.plugins_dir,
                  timeout_s=timeout_s, force_skp=force, mode=mode, plant_scale_only=True)
    out_d: dict[str, Any] = {"status": "OK" if res.get("ok") else "FAILED", "mode": mode,
                             "consensus": str(con), "build": res}
    if res.get("ok") and not res.get("skipped"):
        from tools.run_deterministic_gates import run_all

        out_d["gates"] = run_all(consensus_path=str(con), render_path=str(out.with_name("model_top.png")))
        out_d["next"] = ("gates PASS + VISUAL_REVIEW do Felipe → promote_canonical(src_final="
                         f"'{out.parent}')")
        out_d["visual_review"] = VISUAL_REVIEW
    return out_d


def furnish(*, consensus_path: str | None = None, base_skp: str | None = None,
            style: str | None = None, out_dir: str | None = None, mode: str | None = None,
            timeout_s: int = 300, su: SketchUp | None = None) -> dict[str, Any]:
    """Mobilia a planta: brains de layout (puros) → `place_layout_skp.rb` no shell.

    Diferente de `furnish_apartment.main`, não dá `taskkill /IM`: sobe a PRÓPRIA
    instância e só ela pode ser fechada (modo headless)."""
    su = _su(su)
    why = su.unavailable()
    if why:
        return {"status": "UNAVAILABLE", "reason": why}
    from core import scale

    if abs(scale.PT_TO_M - 0.0259) > 1e-6:
        return {"status": "ERROR",
                "reason": (f"PT_TO_M ativo = {scale.PT_TO_M}, a planta_74 exige 0.0259 — a mobília "
                           "sairia ~1.36x fora do shell. Suba o servidor com PT_TO_M=0.0259.")}
    con_p = paths.resolve(consensus_path) if consensus_path else CONSENSUS_DEFAULT
    base = paths.resolve(base_skp) if base_skp else BASE_SKP_DEFAULT
    for what, p in (("consensus", con_p), ("shell base", base)):
        if not p.exists():
            return {"status": "ERROR", "reason": f"{what} não encontrado: {p}"}
    d, err = _out_dir(out_dir, "furnish", inputs=(base,))
    if err:
        return err
    from tools.furnish_apartment import collect_boxes

    boxes, summary = collect_boxes(json.loads(con_p.read_text("utf-8")))
    if not boxes:
        return {"status": "FAILED", "reason": "nenhum cômodo gerou móveis", "rooms": summary}
    d.mkdir(parents=True, exist_ok=True)
    # o shell base costuma ser o .skp CANÔNICO (artifacts/): o SketchUp abre uma
    # cópia, nunca ele — em modo interactive a janela fica aberta depois do job
    base_copy = _working_copy(base, d / f"_furnish_base_{base.name}")
    files = {k: d / f"planta_74_furnished{suffix}" for k, suffix in (
        ("skp", ".skp"), ("before", "_before_top.png"), ("top", "_after_top.png"),
        ("iso", "_after_iso.png"), ("log", "_log.txt"))}
    for stale in files.values():  # out_dir reaproveitado: arquivo velho não pode parecer resultado
        stale.unlink(missing_ok=True)
    env = {
        "PT_TO_M": "0.0259",
        "LAYOUT_BOXES": json.dumps(boxes),
        "LAYOUT_TEX_DIR": str((REPO / "assets/textures/procedural").resolve()),
        "LAYOUT_OUT": str(files["skp"]).replace("\\", "/"),
        "LAYOUT_BEFORE": str(files["before"]).replace("\\", "/"),
        "LAYOUT_AFTER_TOP": str(files["top"]).replace("\\", "/"),
        "LAYOUT_AFTER_ISO": str(files["iso"]).replace("\\", "/"),
        "LAYOUT_LOG": str(files["log"]).replace("\\", "/"),
    }
    if style:
        from tools.style_spec import texture_env

        env["FURNISH_STYLE"] = style
        env.update(texture_env(style, (REPO / "assets/textures/procedural").resolve()))
    run = run_script(su, script=REPO / "tools" / "place_layout_skp.rb", done_marker=files["log"],
                     skp_in=base_copy, env_extra=env, timeout_s=timeout_s, mode=mode)
    out: dict[str, Any] = {**run, "boxes": len(boxes), "base_skp": str(base),
                           "rooms": [{"room_id": r[0], "name": r[1], "type": r[2], "result": r[3], "boxes": r[4]}
                                     for r in summary]}
    if run["status"] != "DONE":
        return out
    log = files["log"].read_text("utf-8", errors="replace")
    ok = files["skp"].exists() and files["skp"].stat().st_size > 0
    out.update(status="OK" if ok else "FAILED", log=log[-2000:],
               files={k: str(v) for k, v in files.items() if v.exists()},
               visual_review=VISUAL_REVIEW)
    if not ok:
        out["reason"] = "o builder terminou mas o .skp mobiliado não saiu (ou saiu com 0 byte)"
    return out


# V-Ray: o launcher legado (tools/render_scene_vray.py) matava o SketchUp por NOME
# DE IMAGEM (`taskkill /F /IM SketchUp.exe`) depois da exportação e escrevia dentro
# do scene_dir. Aqui a exportação passa por batch.run_script (a PRÓPRIA instância,
# fechada só pelo modo/PID dela), o scene_dir é só leitura e tudo sai no out_dir.
VRAY_EXPORT_RB = REPO / "tools" / "vray_export.rb"
VRAY_RECIPE = {"iso": 100, "fnum": 7.0, "shutter": 160, "sky": 0.3}  # receita interior (suite01)


def _vray_exe_run(cmd: list[str], timeout_s: int) -> dict[str, Any]:
    """vray.exe headless (não é o SketchUp). Isolado para os testes dublarem."""
    import subprocess

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s,  # noqa: S603
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"returncode": None, "timeout": True, "tail": ""}
    return {"returncode": r.returncode, "timeout": False, "tail": ((r.stdout or "") + (r.stderr or ""))[-800:]}


def _sha(p: Path) -> str | None:
    import hashlib

    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def render_vray(scene_dir: str, *, out_png: str | None = None, width: int = 1500,
                height: int = 1000, fov: float = 65, out_dir: str | None = None,
                mode: str | None = None, timeout_s: int = 240, render_timeout_s: int = 600,
                su: SketchUp | None = None) -> dict[str, Any]:
    """Render V-Ray de uma cena composta: `scene_dir` com scene.json (câmera em
    metros) + scene_closed.skp (modelo fechado). Exporta o .vrscene numa CÓPIA via
    -RubyStartup tools/vray_export.rb e renderiza com vray.exe headless.

    O scene_dir nunca é escrito; .vrscene, log e PNG saem em `out_dir` (default
    runs/planta_74/mcp/render_vray_<stamp>/). Nenhum SketchUp alheio é tocado."""
    su = _su(su)
    why = su.unavailable()
    if why:
        return {"status": "UNAVAILABLE", "reason": why}
    if not su.system.exists(su.loc.vray_exe):
        return {"status": "UNAVAILABLE", "reason": f"vray.exe não encontrado em {su.loc.vray_exe} (env VRAY_EXE)"}
    if not (100 <= width <= 8000 and 100 <= height <= 8000):
        return {"status": "ERROR", "reason": "width/height entre 100 e 8000 px"}
    if not (10 <= fov <= 120):
        return {"status": "ERROR", "reason": "fov entre 10 e 120 graus"}
    d = paths.resolve(scene_dir)
    scene_json, closed = d / "scene.json", d / "scene_closed.skp"
    for what, p in (("scene.json", scene_json), ("scene_closed.skp", closed)):
        if not p.exists():
            return {"status": "ERROR", "reason": f"{what} ausente em {d} (o modelo fechado vem do composer)"}
    try:
        cam = json.loads(scene_json.read_text("utf-8"))["camera"]
        eye, target = cam["eye"], cam["target"]
        assert len(eye) == 3 and len(target) == 3
    except (ValueError, KeyError, TypeError, AssertionError) as e:
        return {"status": "ERROR", "reason": f"scene.json sem camera.eye/target [x,y,z] em metros: {e}"}
    od, err = _out_dir(out_dir, "render_vray", inputs=(closed, scene_json))
    if err:
        return err
    if out_png:
        try:
            png = paths.check_output(out_png, inputs=(closed, scene_json))
        except paths.OutputPathRefused as e:
            return {"status": "REFUSED", "reason": str(e)}
        if png.suffix.lower() != ".png":
            return {"status": "ERROR", "reason": f"out_png precisa terminar em .png: {png}"}
    else:
        png = od / "vray.png"
    if png.exists():
        return {"status": "REFUSED", "reason": f"out_png já existe ({png}); render sai sempre em arquivo novo"}
    od.mkdir(parents=True, exist_ok=True)
    png.parent.mkdir(parents=True, exist_ok=True)
    before = {str(p): _sha(p) for p in (scene_json, closed)}
    copy = _working_copy(closed, od / f"_vray_{closed.name}")
    vrs, log = od / "scene.vrscene", od / "vray_export_log.txt"
    from core.scale import M_TO_IN

    fmt = lambda v: ",".join(f"{c * M_TO_IN:.2f}" for c in v)  # noqa: E731
    env = {"VRSCENE_OUT": str(vrs).replace("\\", "/"), "VRAY_LOG": str(log).replace("\\", "/"),
           "VRAY_EYE": fmt(eye), "VRAY_TARGET": fmt(target), "VRAY_FOV": str(fov),
           "VRAY_TEX_DIR": str((REPO / "assets/textures/procedural").resolve()).replace("\\", "/")}
    run = run_script(su, script=VRAY_EXPORT_RB, done_marker=log, skp_in=copy, env_extra=env,
                     timeout_s=timeout_s, mode=mode)
    out: dict[str, Any] = {**run, "scene_dir": str(d), "out_dir": str(od)}
    if run["status"] != "DONE":
        return out
    log_txt = log.read_text("utf-8", errors="replace")
    out["export_log"] = log_txt[-600:]
    if not vrs.exists() or vrs.stat().st_size == 0:
        out.update(status="FAILED", reason="vray_export.rb terminou sem .vrscene (V-Ray carregado no SketchUp?)")
        return out
    from tools.tweak_vrscene import tweak_file

    tweak_file(str(vrs), width=width, height=height, materials=True, **VRAY_RECIPE)
    r = _vray_exe_run([str(su.loc.vray_exe), f"-sceneFile={vrs}", f"-imgFile={png}",
                       "-display=0", "-autoClose=1"], render_timeout_s)
    out["vray"] = r
    out["inputs_intact"] = all(_sha(Path(p)) == h for p, h in before.items())
    if not png.exists() or png.stat().st_size == 0:
        out.update(status="FAILED", reason=("vray.exe estourou o tempo" if r["timeout"]
                                            else "vray.exe não produziu imagem (licença?)"))
        return out
    try:
        from PIL import Image

        im = Image.open(png)
        if im.mode == "RGBA":  # céu sai com alpha 0: achata (mesmo motivo do launcher legado)
            im.convert("RGB").save(png)
    except Exception:  # noqa: BLE001 — sem PIL o PNG continua válido, só com alpha
        pass
    out.update(status="OK" if out["inputs_intact"] else "FAILED", png=str(png),
               vrscene_bytes=vrs.stat().st_size, visual_review=VISUAL_REVIEW)
    if not out["inputs_intact"]:
        out["reason"] = "o scene_dir mudou durante o render — investigar antes de usar o PNG"
    return out


__all__ = ["status", "open_model", "close", "inspect_model", "render_views", "apply_edits",
           "build_shell", "furnish", "render_vray", "PRESETS"]
