"""Repro: jobs.inspect_model num filho atribuído a um Job Object KILL_ON_JOB_CLOSE
(igual ao cliente MCP Python) com ou sem SILENT_BREAKAWAY_OK.
uso: job_repro.py <skp> <out_dir> plain|breakaway"""
import json, subprocess, sys
import win32api, win32con, win32job
skp, out, how = sys.argv[1:4]
job = win32job.CreateJobObject(None, "")
info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
flags = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
if how == "breakaway":
    flags |= win32job.JOB_OBJECT_LIMIT_BREAKAWAY_OK | win32job.JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK
info["BasicLimitInformation"]["LimitFlags"] |= flags
win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
code = ("import json,sys,time; time.sleep(1); from tools.sketchup import jobs; "
        f"r=jobs.inspect_model(r'{skp}', out_dir=r'{out}', timeout_s=90); "
        "print(json.dumps({k:r.get(k) for k in ('status','pid','elapsed_s')}))")
p = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                     creationflags=subprocess.CREATE_NO_WINDOW)
h = win32api.OpenProcess(win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, p.pid)
win32job.AssignProcessToJobObject(job, h)
o = p.stdout.read()
print(how, o.strip())
r = json.loads(o.strip().splitlines()[-1])
from tools.sketchup import jobs
alive = [x["pid"] for x in jobs.status()["instances"]]
print("SU vivo antes de fechar o job:", r.get("pid") in alive)
win32api.CloseHandle(job)
import time; time.sleep(3)
alive2 = [x["pid"] for x in jobs.status()["instances"]]
print("SU vivo DEPOIS de fechar o job:", r.get("pid") in alive2)
if r.get("pid") in alive2:
    print(jobs.close(pid=int(r["pid"]), force=True, confirm=True))
