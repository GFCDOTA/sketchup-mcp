"""sketchup_basic_provider.py — RenderProvider FUNCIONAL via SketchUp 2026 (Fase 4).
Encapsula a receita de render que estava inline no PowerShell: copia a base->scratch
(NUNCA muta a base), monta o env (LAYOUT_BOXES/OUT/RENDER_*/LOG), lanca o SU via
PowerShell Start-Process (unica via que pega o desktop interativo p/ write_image), faz
poll do log, mata o SU e CONFERE o hash da base. Devolve RenderResult (status/timing/log).

renderer='layout'    -> place_layout_skp.rb  (shell da planta; env LAYOUT_AFTER_TOP/ISO + LAYOUT_ZOOM_GROUP)
renderer='furniture' -> build_furniture_skp.rb (movel standalone; env RENDER_TOP/FRONT/ISO, frame tight)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

from interior.renderers.render_provider import ROOT, RenderProvider, RenderRequest, RenderResult

SU_EXE = r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
BASE_SKP = ROOT / "artifacts/planta_74/planta_74.skp"
SCRATCH = ROOT / ".claude/scratch"
RB = {"layout": ROOT / "tools/place_layout_skp.rb",
      "furniture": ROOT / "tools/build_furniture_skp.rb"}
# render_type -> env var, por renderer
ENV_MAP = {
    "layout": {"top": "LAYOUT_AFTER_TOP", "iso": "LAYOUT_AFTER_ISO", "before": "LAYOUT_BEFORE"},
    "furniture": {"top": "RENDER_TOP", "iso": "RENDER_ISO", "front": "RENDER_FRONT"},
}


def _sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


class SketchUpBasicProvider(RenderProvider):
    name = "sketchup_basic"

    def __init__(self, su_exe=SU_EXE, base_skp=BASE_SKP):
        self.su_exe = Path(su_exe)
        self.base_skp = Path(base_skp)

    def available(self) -> bool:
        return self.su_exe.exists() and self.base_skp.exists()

    def render(self, req: RenderRequest, timeout_s: int = 230) -> RenderResult:
        if not self.available():
            return self.skipped(req, f"SU/base ausente ({self.su_exe})")
        if req.renderer not in RB:
            return RenderResult(status="fail", provider=self.name, error=f"renderer invalido: {req.renderer}")
        base = Path(req.base_skp) if req.base_skp else self.base_skp
        base_hash = _sha(base)
        SCRATCH.mkdir(parents=True, exist_ok=True)
        copy = SCRATCH / "provider_base_copy.skp"
        log = SCRATCH / f"provider_{req.label}_log.txt"
        for p in [log, Path(req.out_skp)] + [Path(v) for v in req.renders.values()]:
            try:
                Path(p).parent.mkdir(parents=True, exist_ok=True)
                if Path(p).exists():
                    Path(p).unlink()
            except OSError:
                pass
        import shutil
        shutil.copy2(base, copy)

        env = {"LAYOUT_BOXES": json.dumps(req.boxes or []),
               "LAYOUT_OUT": str(req.out_skp).replace("\\", "/"),
               "LAYOUT_LOG": str(log).replace("\\", "/")}
        emap = ENV_MAP[req.renderer]
        for rtype, path in req.renders.items():
            var = emap.get(rtype)
            if var:
                env[var] = str(path).replace("\\", "/")
        if req.renderer == "layout" and req.zoom_group:
            env["LAYOUT_ZOOM_GROUP"] = "1"

        # SU precisa do desktop interativo p/ write_image -> lancar via PowerShell Start-Process.
        # Passar o env pro powershell; Start-Process herda o environment block.
        full_env = dict(__import__("os").environ)
        full_env.update(env)
        ps = (f"Start-Process -FilePath '{self.su_exe}' "
              f"-ArgumentList '\"{copy}\"','-RubyStartup','\"{RB[req.renderer]}\"'")
        t0 = time.time()
        try:
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                           env=full_env, capture_output=True, timeout=60)
        except Exception as e:  # noqa: BLE001
            return RenderResult(status="fail", provider=self.name, error=f"launch: {e}")

        # poll do log (sinal de done) + grace
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if log.exists():
                time.sleep(2)
                break
            time.sleep(2)
        subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
        time.sleep(1)
        timing = round(time.time() - t0, 1)

        log_txt = log.read_text("utf-8", errors="ignore") if log.exists() else ""
        base_intact = _sha(base) == base_hash
        made = {k: v for k, v in req.renders.items() if Path(v).exists()}
        skp_ok = Path(req.out_skp).exists()
        status = "success" if (log_txt and "placed" in log_txt and skp_ok and base_intact) else "fail"
        err = ""
        if not base_intact:
            err = "BASE MUTADA (hash mudou)!"
            status = "fail"
        elif status == "fail":
            err = "sem log/placed ou .skp/render faltando"
        return RenderResult(status=status, provider=self.name,
                            skp=(str(req.out_skp) if skp_ok else None), renders=made,
                            timing_s=timing, base_intact=base_intact, log=log_txt[-400:], error=err)


if __name__ == "__main__":
    # PROVA: renderiza o criado close-up via o provider (mesmo resultado do fluxo inline)
    import sys
    sys.path.insert(0, str(ROOT))
    from tools.furniture_anatomy_spec import nightstand_spec
    from tools.nightstand_builder import build_nightstand, parts_to_boxes
    parts, _ = build_nightstand(nightstand_spec())
    boxes = parts_to_boxes(parts)
    out = ROOT / "artifacts/review/furniture/nightstand"
    req = RenderRequest(boxes=boxes, out_skp=str(SCRATCH / "provider_nightstand.skp"),
                        renderer="furniture", label="ns_provider",
                        renders={"iso": str(out / "nightstand_provider_iso.png")})
    res = SketchUpBasicProvider().render(req)
    print(f"status={res.status} provider={res.provider} timing={res.timing_s}s base_intact={res.base_intact}")
    print(f"renders={res.renders}")
    print(f"log_tail={res.log[-160:]!r}")
    if res.error:
        print(f"error={res.error}")
    sys.exit(0 if res.ok() else 1)
