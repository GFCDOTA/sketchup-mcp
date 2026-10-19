"""P3b-01: duas janelas simultaneas do SketchUp — (a) 'humano' com trabalho NAO salvo e (b) jobs do MCP.
Prova: o job roda so em (b); close/timeout/erro afetam so (b); (a) e o trabalho nao salvo sobrevivem; nenhum control file global.
uso (cwd = repo, PT_TO_M=0.0259): p3b_two_windows.py <saida_dir> <base.skp>"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tools.sketchup import jobs
from tools.sketchup.legacy_process import close_owned, launch_owned
from tools.sketchup.process import SketchUp

REPO = Path.cwd().resolve()
OUT = Path(sys.argv[1]).resolve()
BASE = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
su = SketchUp()
SU_EXE = str(su.loc.exe)
PLUGINS = Path(su.loc.plugins_dir)
res = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "steps": []}


def alive(pid):
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
    return f'"{pid}"' in out


def instances():
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH", "/FI", "IMAGENAME eq SketchUp.exe"], capture_output=True, text=True).stdout
    return sorted(int(ln.split('","')[1]) for ln in out.splitlines() if "SketchUp.exe" in ln)


def autorun_files():
    return sorted(str(p) for p in PLUGINS.glob("*control*")) if PLUGINS.exists() else []


def step(name, **data):
    res["steps"].append({"step": name, **data})
    print(name, json.dumps(data, default=str)[:300], flush=True)


assert instances() == [], f"ha SketchUp aberto antes do teste: {instances()} (o teste exige ambiente limpo)"
step("preflight", sketchup_instances=instances(), control_files_in_plugins=autorun_files())

# ---------------- (a) 'humano': janela com trabalho NAO salvo
human = OUT / "human.skp"
shutil.copy2(BASE, human)
hb = OUT / "heartbeat.json"
rb = OUT / "human_sim.rb"
rb.write_text("""require 'json'
UI.start_timer(2.0, false) do
  m = Sketchup.active_model
  m.start_operation('human edit', true)
  g = m.entities.add_group
  g.name = 'HUMAN_UNSAVED_WORK'
  g.entities.add_face([0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0])
  m.commit_operation
  hb = ENV['HEARTBEAT']
  UI.start_timer(1.0, true) do
    mm = Sketchup.active_model
    File.write(hb + '.tmp', JSON.generate({'t' => Time.now.to_f, 'path' => mm.path, 'modified' => mm.modified?,
                                           'groups' => mm.entities.grep(Sketchup::Group).map(&:name), 'count' => mm.entities.count}))
    File.rename(hb + '.tmp', hb) rescue nil
  end
end
""", encoding="utf-8")
env = {**os.environ, "HEARTBEAT": str(hb).replace("\\", "/")}
pa = subprocess.Popen([SU_EXE, str(human), "-RubyStartup", str(rb)], env=env, stdin=subprocess.DEVNULL,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
PID_A = pa.pid
for _ in range(40):
    if hb.exists():
        break
    time.sleep(1)
beat = lambda: json.loads(hb.read_text("utf-8"))  # noqa: E731
b0 = beat()
step("human_window_a", pid=PID_A, modified=b0["modified"], groups=b0["groups"], path=b0["path"], count=b0["count"])
assert b0["modified"] and "HUMAN_UNSAVED_WORK" in b0["groups"]


def a_intact(label):
    t0 = beat()["t"]
    time.sleep(2.5)
    b = beat()
    ok = alive(PID_A) and b["t"] > t0 and b["modified"] and b["groups"] == b0["groups"] and b["count"] == b0["count"] and b["path"] == b0["path"]
    step(f"a_intact_after_{label}", ok=ok, heartbeat_advanced=b["t"] > t0, modified=b["modified"], groups=b["groups"], alive=alive(PID_A))
    return ok


ok_all = []
inspect_target = OUT / "target.skp"
shutil.copy2(BASE, inspect_target)


async def mcp_session():
    params = StdioServerParameters(command=sys.executable, args=["-m", "tools.mcp_server.server"], cwd=str(REPO),
                                   env={**os.environ, "PYTHONPATH": str(REPO), "PT_TO_M": "0.0259"})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            call = lambda name, args, t=240: s.call_tool(name, args, read_timeout_seconds=timedelta(seconds=t))  # noqa: E731
            st = json.loads((await call("su_status", {})).content[0].text)
            step("mcp_status", instances=st.get("instances"), sees_a=any(i["pid"] == PID_A for i in st.get("instances", [])),
                 server_job=st.get("server_job"))
            ins = json.loads((await call("su_inspect", {"skp_path": str(inspect_target)})).content[0].text)
            pid_b = ins.get("pid")
            path_in_job = (ins.get("result") or {}).get("path")
            step("job_b_inspect", status=ins.get("status"), pid_b=pid_b, pid_b_is_not_a=pid_b != PID_A, model_path_in_job=path_in_job,
                 job_ran_on_copy_not_human=bool(path_in_job) and "human.skp" not in path_in_job and "_inspect_" in path_in_job)
            ok_all.append(a_intact("job_b"))
            # su_close sem confirm e em massa: recusado
            refused = json.loads((await call("su_close", {"all_instances": True})).content[0].text)
            step("close_all_without_confirm", status=refused.get("status"))
            ok_all.append(a_intact("close_refusal"))
            # su_close do PID de (b): so (b)
            closed = json.loads((await call("su_close", {"pid": pid_b, "force": True, "confirm": True})).content[0].text)
            time.sleep(2)
            step("close_pid_b", status=closed.get("status"), closed=closed.get("closed"), b_alive=alive(pid_b), a_alive=alive(PID_A))
            ok_all.append(a_intact("close_pid_b"))
            # su_close de um PID que e o humano... so por decisao explicita do chamador: a API pede o PID; recusa PID desconhecido
            unknown = json.loads((await call("su_close", {"pid": 999999, "confirm": True})).content[0].text)
            step("close_unknown_pid", status=unknown.get("status"))


asyncio.run(mcp_session())

# ---------------- timeout e erro de job: afetam so (b)
t1 = OUT / "timeout.skp"
shutil.copy2(BASE, t1)
r = jobs.inspect_model(str(t1), timeout_s=1, mode="interactive", out_dir=str(OUT / "timeout_job"))
pid_t = r.get("pid")
step("timeout_job_b", status=r.get("status"), reason=r.get("reason"), pid_b=pid_t, b_left_running=r.get("su_left_running"), elapsed_s=r.get("elapsed_s"))
if pid_t:
    jobs.close(pid=int(pid_t), force=True, confirm=True)
time.sleep(2)
step("timeout_cleanup", b_alive=alive(pid_t) if pid_t else None, a_alive=alive(PID_A))
ok_all.append(a_intact("timeout"))

bad = OUT / "corrupt.skp"
bad.write_bytes(b"isto nao e um skp" * 50)
r = jobs.inspect_model(str(bad), timeout_s=45, mode="interactive", out_dir=str(OUT / "error_job"))
pid_e = r.get("pid")
step("error_job_b", status=r.get("status"), reason=r.get("reason"), pid_b=pid_e, elapsed_s=r.get("elapsed_s"),
     no_positive_result="result" not in r or not (r.get("result") or {}).get("ok"))
if pid_e:
    jobs.close(pid=int(pid_e), force=True, confirm=True)
time.sleep(2)
ok_all.append(a_intact("error"))

# ---------------- CLIs legadas: launch_owned/close_owned mexem so no proprio PID
legacy_skp = OUT / "legacy.skp"
shutil.copy2(BASE, legacy_skp)
script = OUT / "noop.rb"
script.write_text("# noop\n", encoding="utf-8")
pid_l = launch_owned(Path(SU_EXE), legacy_skp, script, env=dict(os.environ))
time.sleep(8)
before = instances()
close_owned(pid_l)
time.sleep(3)
step("legacy_launch_close_owned", pid_legacy=pid_l, instances_before_close=before, legacy_alive_after=alive(pid_l), a_alive=alive(PID_A))
ok_all.append(a_intact("legacy_close_owned"))

step("final", control_files_in_plugins=autorun_files(), instances_before_cleanup=instances())
# limpeza: fecha (a), o NOSSO processo de teste, pelo PID
subprocess.run(["taskkill", "/PID", str(PID_A), "/F"], capture_output=True)
time.sleep(2)
res["a_intact_everywhere"] = all(ok_all)
res["checks_a_intact"] = len(ok_all)
res["a_closed_by_test_cleanup"] = not alive(PID_A)
res["instances_after_cleanup"] = instances()
(OUT / "two_windows.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
print("RESULT a_intact_everywhere =", res["a_intact_everywhere"], "checks", res["checks_a_intact"], "instances_after", res["instances_after_cleanup"])
