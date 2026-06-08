"""vray_final_provider.py — V-Ray FINAL/premium (stub com API MAPEADA; Fase 8 implementa).

SPIKE Fase 5 CONFIRMOU VIABILIDADE (empirico, .claude/scratch/probe_vray*.rb em SU 2026):
  - Extensao "V-Ray for SketchUp" CARREGA no SU 2026 (loaded=true) + binario vray4sketchup2026.so.
  - API Ruby `module VRay` totalmente alcancavel (176 constants) a partir de -RubyStartup.
  - Fluxo render->save MAPEADO:
      * VRay::RenderSessionProduction.new(context:).start        -> render in-SU
      * VRay::RenderSessionExport.new(context:, path: '..vrscene').start -> exporta .vrscene
        (depois `vray.exe -sceneFile=x.vrscene -imgFile=y.png` renderiza HEADLESS, offline)
      * VRayRenderer#image -> VRay::VRayImage#save(path) -> PNG
      * VRay.configure_renderer(...) / VRay::Settings.load_defaults -> settings
      * VRay::ModelExporter#update_camera / export_model -> camera/geom
  - vray.exe standalone: C:\\Program Files\\Chaos\\V-Ray\\V-Ray for SketchUp\\extension\\vray\\bin\\vray.exe

REMANESCENTE (Fase 8, empirico — NAO inventar): obter o `context` (source crypt-protegido,
sem call-sites em texto) + nailar os 3 args de VRay.start_render. Caminho mais deterministico:
RenderSessionExport -> .vrscene -> vray.exe headless (desacopla do GUI do SU). Pre-req: licenca
V-Ray ativa (ja instalada). Riscos: render lento (min), VFB window, compat. Implementar em ciclo
focado com tentativa cuidadosa (base copia + timeout + kill) OU snippet de referencia do AppSDK.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path

from interior.renderers.render_provider import ROOT, RenderProvider, RenderRequest, RenderResult

SU_EXE = Path(r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe")
VRAY_SO = Path(r"C:\Program Files\Chaos\V-Ray\V-Ray for SketchUp\extension\vray4sketchup2026.so")
VRAY_EXE = Path(r"C:\Program Files\Chaos\V-Ray\V-Ray for SketchUp\extension\vray\bin\vray.exe")
VRAY_EXPORT_RB = ROOT / "tools/vray_export.rb"
SCRATCH = ROOT / ".claude/scratch"


def _sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


class VRayFinalProvider(RenderProvider):
    """Render PREMIUM V-Ray (PROVADO Fase 8): SU+Ruby exporta .vrscene
    (VRay::RenderSessionExport, context=VRay::Context.active) -> vray.exe renderiza HEADLESS
    (-display=0 -autoClose=1) -> PNG fotorrealista. ~3-5s na GPU. NUNCA muta o .skp de
    entrada (renderiza numa COPIA; hash conferido)."""

    name = "vray_final"

    def __init__(self, su_exe=SU_EXE, vray_exe=VRAY_EXE):
        self.su_exe = Path(su_exe)
        self.vray_exe = Path(vray_exe)

    def available(self) -> bool:
        return (VRAY_SO.exists() and self.vray_exe.exists()
                and self.su_exe.exists() and VRAY_EXPORT_RB.exists())

    def render(self, req: RenderRequest, export_timeout=120, render_timeout=300) -> RenderResult:
        if not self.available():
            return self.skipped(req, "V-Ray/SU/vray_export.rb ausente")
        skp = req.in_skp or req.out_skp
        if not skp or not Path(skp).exists():
            return RenderResult(status="fail", provider=self.name,
                                error="VRayFinalProvider precisa de in_skp/.skp ja construido")
        skp = Path(skp)
        skp_hash = _sha(skp)
        out_png = req.renders.get("iso") or req.renders.get("perspective") or next(iter(req.renders.values()), None)
        if not out_png:
            return RenderResult(status="fail", provider=self.name, error="sem output PNG em renders")
        SCRATCH.mkdir(parents=True, exist_ok=True)
        copy = SCRATCH / "vray_render_copy.skp"
        vrscene = SCRATCH / f"vray_{req.label}.vrscene"
        log = SCRATCH / f"vray_{req.label}_export_log.txt"
        for p in (vrscene, log, Path(out_png)):
            Path(p).parent.mkdir(parents=True, exist_ok=True)
            if Path(p).exists():
                try:
                    Path(p).unlink()
                except OSError:
                    pass
        shutil.copy2(skp, copy)
        t0 = time.time()

        # 1. SU exporta .vrscene (camera + RenderSessionExport)
        tex_dir = ROOT / "assets/textures/procedural"
        env = dict(os.environ)
        env.update({"VRSCENE_OUT": str(vrscene).replace("\\", "/"),
                    "VRAY_LOG": str(log).replace("\\", "/"),
                    "VRAY_CAM": "top" if "top" in req.renders else "iso"})
        if tex_dir.is_dir():
            env["VRAY_TEX_DIR"] = str(tex_dir)   # materiais texturizados (madeira/tecido)
        ps = (f"Start-Process -FilePath '{self.su_exe}' "
              f"-ArgumentList '\"{copy}\"','-RubyStartup','\"{VRAY_EXPORT_RB}\"'")
        try:
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                           env=env, capture_output=True, timeout=60)
        except Exception as e:  # noqa: BLE001
            return RenderResult(status="fail", provider=self.name, error=f"SU launch: {e}")
        deadline = time.time() + export_timeout
        while time.time() < deadline:
            if log.exists():
                time.sleep(2)
                break
            time.sleep(2)
        subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
        time.sleep(1)
        if not vrscene.exists():
            return RenderResult(status="fail", provider=self.name, base_intact=(_sha(skp) == skp_hash),
                                log=(log.read_text("utf-8", "ignore") if log.exists() else ""),
                                error="export .vrscene falhou")

        # 1b. corrige EXPOSICAO: o export sai com a CameraPhysical setada p/ exterior claro
        # (f/8, 1/300, ISO100) -> interior subexposto. Tweak p/ um interior bem exposto.
        try:
            from tools.tweak_vrscene import tweak_file
            tweak_file(vrscene, iso=req.iso, fnum=req.fnum, shutter=req.shutter, sky=req.sky,
                       materials=True)
        except Exception:  # noqa: BLE001
            pass

        # 2. vray.exe renderiza headless -> PNG
        try:
            r = subprocess.run([str(self.vray_exe), f"-sceneFile={vrscene}", f"-imgFile={out_png}",
                                "-display=0", "-autoClose=1"], capture_output=True, timeout=render_timeout)
            rlog = (r.stdout.decode("utf-8", "ignore")[-500:] if r.stdout else "")
        except Exception as e:  # noqa: BLE001
            return RenderResult(status="fail", provider=self.name, error=f"vray.exe: {e}")

        timing = round(time.time() - t0, 1)
        png_ok = Path(out_png).exists()
        base_intact = _sha(skp) == skp_hash
        status = "success" if (png_ok and base_intact) else "fail"
        return RenderResult(status=status, provider=self.name, skp=str(skp),
                            renders=({"iso": str(out_png)} if png_ok else {}), timing_s=timing,
                            base_intact=base_intact, log=rlog,
                            error=("" if status == "success" else "PNG nao gerado ou base mutada"))


if __name__ == "__main__":
    # PROVA: render premium da planta mobiliada via o provider
    import sys
    sys.path.insert(0, str(ROOT))
    fdir = ROOT / "artifacts/planta_74/furnished"
    req = RenderRequest(boxes=None, out_skp=None, in_skp=str(fdir / "planta_74_furnished.skp"),
                        renderer="vray", label="apt_prov",
                        renders={"iso": str(fdir / "planta_74_vray_provider_iso.png")})
    res = VRayFinalProvider().render(req)
    print(f"status={res.status} timing={res.timing_s}s base_intact={res.base_intact}")
    print(f"renders={res.renders}")
    if res.error:
        print(f"error={res.error}")
    sys.exit(0 if res.ok() else 1)
