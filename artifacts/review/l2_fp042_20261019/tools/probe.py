"""Roda geometry_probe.rb (scratch) numa CÓPIA do .skp, pelo mesmo batch.run_script
que os jobs su_* usam (PID próprio, -RubyStartup, resultado JSON atômico).
uso: probe.py <skp> <out_dir> '<json params>'"""
import json
import shutil
import sys
from pathlib import Path

from tools.sketchup.batch import RUBY_DIR, _slash, run_script
from tools.sketchup.process import SketchUp

skp, out_dir, params = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), json.loads(sys.argv[3])
out_dir.mkdir(parents=True, exist_ok=True)
copy = out_dir / f"_probe_{skp.name}"
shutil.copy2(skp, copy)
pp, rp = out_dir / "probe_params.json", out_dir / "probe_result.json"
pp.write_text(json.dumps(params, indent=1), encoding="utf-8")
run = run_script(SketchUp(), script=Path(__file__).with_name("geometry_probe.rb"), done_marker=rp,
                 skp_in=copy, mode="interactive", timeout_s=int(params.get("timeout_s", 180)),
                 env_extra={"SKMCP_PARAMS": _slash(pp), "SKMCP_RESULT": _slash(rp), "SKMCP_QUIT": "0",
                            "SKMCP_RUBY_DIR": _slash(RUBY_DIR)})
(out_dir / "probe_run.json").write_text(json.dumps(run, indent=1, default=str), encoding="utf-8")
print(json.dumps(run, default=str))
