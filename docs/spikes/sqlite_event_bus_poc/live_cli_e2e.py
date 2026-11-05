"""Opt-in E2E: real Claude Code and Codex CLI, isolated SQLite queue; no GitHub writes."""
import argparse,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
from bus import Bus

SCHEMA={"type":"object","additionalProperties":False,"required":["verdict","observed","expected"],"properties":{"verdict":{"type":"string","enum":["APPROVE","REQUEST_CHANGES"]},"observed":{"type":"string"},"expected":{"type":"string"}}}
def command(kind, wd, bins):
    if kind=="IMPLEMENT":
        return [bins["claude"],"-p","--output-format","text","--permission-mode","dontAsk","--allowedTools","","--setting-sources","","--strict-mcp-config","--no-session-persistence"]
    return [bins["codex"],"exec","--sandbox","read-only","--skip-git-repo-check","--output-schema",str(wd/"schema.json"),"--output-last-message",str(wd/"review.json"),"-"]
def worker(bus,kind,wd,bins,timeout):
    job=bus.claim(kind,kind+"-worker",lease_seconds=timeout+60)
    if not job: raise RuntimeError("No job "+kind)
    payload=json.loads(job["payload"])
    prompt=('Return ONLY strict JSON {"artifact":"hello-world"}. Use NO tools or files.' if kind=="IMPLEMENT" else
        'Independently check this JSON. Approve iff observed == expected. Return strict JSON matching schema with fields verdict, observed, expected. Input: '+json.dumps(payload))
    env=os.environ.copy()
    for name in ("GH_TOKEN","GITHUB_TOKEN","GIT_ASKPASS","AWS_ACCESS_KEY_ID","AWS_SECRET_ACCESS_KEY"): env.pop(name,None)
    try:
        run=subprocess.run(command(kind,wd,bins),input=prompt,capture_output=True,text=True,cwd=wd,env=env,timeout=timeout)
        if run.returncode: raise RuntimeError(f"{kind} CLI error rc={run.returncode}; stderr tail: {run.stderr[-400:]}")
        raw=run.stdout if kind=="IMPLEMENT" else (wd/"review.json").read_text(encoding="utf-8")
        result=json.loads(raw.strip())
        if kind=="IMPLEMENT" and (not isinstance(result,dict) or set(result)!={"artifact"}): raise ValueError("invalid implementation JSON")
        if kind=="REVIEW" and (not isinstance(result,dict) or set(result)!={"verdict","observed","expected"} or result["verdict"] not in ("APPROVE","REQUEST_CHANGES")): raise ValueError("invalid review JSON")
        if not bus.finish(job,kind+"-worker",json.dumps(result)): raise RuntimeError("lease lost")
        return result
    except Exception as e:
        bus.fail(job,kind+"-worker",str(e)[:180])
        raise
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--run-live",action="store_true")
    ap.add_argument("--timeout",type=int,default=180)
    args=ap.parse_args()
    bins={name:shutil.which(name) for name in ("claude","codex")}
    print("CLI:",{k:("FOUND" if v else "MISSING") for k,v in bins.items()})
    if not args.run_live:
        print("No CLIs executed; pass --run-live explicitly")
        return 0
    if not all(bins.values()):
        print("BLOCKED: both authenticated CLIs are required",file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="eventbus-live-") as tmp:
        wd=Path(tmp)
        (wd/"schema.json").write_text(json.dumps(SCHEMA),encoding="utf-8")
        bus=Bus(wd/"queue.sqlite")
        bus.publish("lab:head1:implementation","IMPLEMENT",{"text":"Hello World"})
        implementation=worker(bus,"IMPLEMENT",wd,bins,args.timeout)
        bus.publish("lab:head1:review","REVIEW",{"observed":implementation["artifact"],"expected":"hello-world"})
        review=worker(bus,"REVIEW",wd,bins,args.timeout)
        ok=(implementation=={"artifact":"hello-world"} and review=={"verdict":"APPROVE","observed":"hello-world","expected":"hello-world"} and all(row["state"]=="DONE" for row in bus.rows()))
        print("CLAUDE:",implementation,"CODEX:",review)
        print("JOBS:",[(row["kind"],row["state"]) for row in bus.rows()])
        print("REAL_CLI_E2E:","PASS" if ok else "FAIL")
        return 0 if ok else 1
if __name__=="__main__": raise SystemExit(main())
