"""FP-033 — closed correction loop: DETECT -> CLASSIFY -> FIX -> RE-CHECK.

The state machine that turns the `autonomous-fidelity-loop` protocol (prose a
session follows by hand) into a programmatic driver. Per cycle it detects typed
findings, routes them (`tools/finding_router`), applies deterministic fixes
(`tools/correction_fixes`) on a WORKING COPY, re-checks, and stops honestly:

    CLEAN            no findings — backlog exhausted, does not invent cycles
    STALL            same finding signature twice / fix worsened (reverted)
    NEEDS_FELIPE     only appearance-routed findings remain (queued, never auto)
    PENDING_VISION   only vision-routed findings remain (request queued for the
                     FP-032 eye; `tools/vision_queue_consumer` drains it via
                     POST /ask-vision and `pending_vision_findings` re-injects
                     the confirmed result — the loop itself NEVER fabricates a
                     visual finding)
    MAX_CYCLES       anti-runaway ceiling
    RED              unexpected error (surfaced, not swallowed)

Safety rails (workspace Hard Rules):
- The INPUT consensus/boxes are never mutated: the loop deep-copies and persists
  candidates to its own --out dir. Promotion to `fixtures/` stays human/NOC-gated.
- Appearance verdicts route NEEDS_FELIPE by the router's hard guard — this loop
  cannot emit IMPROVED/SAME/WORSE by construction.
- Heartbeat to the :8765 cockpit is best-effort: offline never blocks a cycle.
- Determinism: no clock/random in decisions; ordering is sorted & stable.

CLI (consensus-level gates; furniture gates via --room):
    python -m tools.correction_loop --fixture planta_74 --out runs/loop_x [--dry-run]
"""
from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from tools import correction_finding as cfind
from tools import correction_fixes as cfix
from tools import finding_router as frouter

REPO_ROOT = Path(__file__).resolve().parent.parent

CLEAN = "CLEAN"
STALL = "STALL"
NEEDS_FELIPE = "NEEDS_FELIPE"
PENDING_VISION = "PENDING_VISION"
MAX_CYCLES = "MAX_CYCLES"
RED = "RED"

BRIDGE_URL = "http://127.0.0.1:8765"


@dataclass
class LoopResult:
    state: str
    cycles: int
    reason: str
    fixes_applied: list[str] = field(default_factory=list)
    felipe_queued: int = 0
    vision_queued: int = 0
    final_findings: list[dict] = field(default_factory=list)


def _signature(findings: list[dict]) -> tuple:
    """Stable identity of a findings set (order-independent)."""
    return tuple(sorted(
        (f.get("type", "?"), f.get("severity", "?"),
         f.get("room", "") or "", f.get("evidence", "")[:80])
        for f in findings
    ))


def _badness(findings: list[dict]) -> tuple[int, int]:
    """(n_FAIL, n_WARN) — the loop's deterministic better/worse metric."""
    return (sum(1 for f in findings if f.get("severity") == "FAIL"),
            sum(1 for f in findings if f.get("severity") == "WARN"))


def _default_heartbeat(session_id: str, cycle: int, stage: str) -> None:
    """Best-effort ping to the :8765 cockpit. MUST never raise into the loop."""
    import urllib.request
    body = json.dumps({"session_id": session_id, "cycle": cycle,
                       "stage": stage}).encode("utf-8")
    req = urllib.request.Request(f"{BRIDGE_URL}/heartbeat", data=body,
                                 method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3):
        pass


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def run_loop(
    *,
    fixture: str,
    detect: Callable[[cfix.FixContext], list[dict]],
    consensus: dict | None = None,
    boxes: list[dict] | None = None,
    room_poly=None,
    out_dir: Path,
    max_cycles: int = 5,
    dry_run: bool = False,
    apply_fix: Callable[[cfix.FixContext, dict], cfix.FixResult] = cfix.apply,
    heartbeat: Callable[[str, int, str], None] | None = _default_heartbeat,
    log: Callable[[str], None] = print,
) -> LoopResult:
    """Run the loop on WORKING COPIES of consensus/boxes. `detect` is injected
    (spec: hermetic tests, no network/SU) and must return unified
    correction_findings (see tools/correction_finding)."""
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    sid = f"correction-loop:{fixture}"
    ctx = cfix.FixContext(
        consensus=copy.deepcopy(consensus) if consensus is not None else None,
        boxes=copy.deepcopy(boxes) if boxes is not None else None,
        room_poly=room_poly,
    )
    queued_felipe: set = set()
    queued_vision: set = set()
    fixes_applied: list[str] = []
    prev_sig: tuple | None = None

    def _beat(cycle: int, stage: str) -> None:
        if heartbeat is None:
            return
        try:
            heartbeat(sid, cycle, stage)
        except Exception:
            log(f"[loop] cycle {cycle}: heartbeat skipped (bridge offline)")

    def _queue(kind: str, findings: list[dict], seen: set) -> int:
        fresh = []
        for f in findings:
            key = (f.get("type"), f.get("room", ""), f.get("evidence", "")[:80])
            if key in seen:
                continue
            seen.add(key)
            fresh.append({**f, "queued_as": kind})
        if fresh:
            _append_jsonl(out_dir / f"{kind}.jsonl", fresh)
        return len(fresh)

    def _persist_cycle(cycle: int, findings: list[dict]) -> None:
        cdir = out_dir / f"cycle_{cycle:02d}"
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "findings.json").write_text(
            json.dumps(findings, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")

    def _finish(state: str, cycle: int, reason: str,
                findings: list[dict]) -> LoopResult:
        res = LoopResult(state=state, cycles=cycle, reason=reason,
                         fixes_applied=fixes_applied,
                         felipe_queued=len(queued_felipe),
                         vision_queued=len(queued_vision),
                         final_findings=findings)
        # the loop's OUTPUT candidate: final corrected state (input untouched);
        # promoting it to fixtures/ stays a gated human/NOC step (Hard Rule #3)
        if ctx.consensus is not None and fixes_applied and not dry_run:
            (out_dir / "consensus_candidate.json").write_text(
                json.dumps(ctx.consensus, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
        (out_dir / "loop_result.json").write_text(json.dumps({
            "fixture": fixture, "state": res.state, "cycles": res.cycles,
            "reason": res.reason, "fixes_applied": res.fixes_applied,
            "felipe_queued": res.felipe_queued,
            "vision_queued": res.vision_queued,
            "dry_run": dry_run,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        log(f"[loop] {fixture} -> {state} @cycle {cycle}: {reason}")
        return res

    try:
        for cycle in range(1, max_cycles + 1):
            _beat(cycle, "detect")
            findings = frouter.classified(detect(ctx))
            _persist_cycle(cycle, findings)
            if not findings:
                return _finish(CLEAN, cycle,
                               "sem findings — laço fechado, não invento ciclo",
                               [])

            sig = _signature(findings)
            if sig == prev_sig:
                return _finish(STALL, cycle,
                               "mesma assinatura do ciclo anterior — patinando, "
                               "não insisto no escuro", findings)
            prev_sig = sig

            autofix = [f for f in findings
                       if f["route"] == frouter.DETERMINISTIC_AUTOFIX]
            vision = [f for f in findings if f["route"] == frouter.NEEDS_VISION]
            felipe = [f for f in findings if f["route"] == frouter.NEEDS_FELIPE]

            if felipe:
                n = _queue("visual_review_queue", felipe, queued_felipe)
                if n:
                    log(f"[loop] cycle {cycle}: {n} finding(s) de aparência -> "
                        f"VISUAL_REVIEW_QUEUED (nunca auto)")
            if vision:
                n = _queue("vision_requests", vision, queued_vision)
                if n:
                    log(f"[loop] cycle {cycle}: {n} finding(s) qualitativos -> "
                        f"fila do olho FP-032")

            if not autofix:
                if vision:
                    return _finish(PENDING_VISION, cycle,
                                   "só restam findings de visão — pedido na fila "
                                   "do FP-032, nada fabricado", findings)
                return _finish(NEEDS_FELIPE, cycle,
                               "só restam findings de aparência — fila do Felipe",
                               findings)

            if dry_run:
                return _finish(
                    "DRY_RUN", cycle,
                    f"{len(autofix)} autofix aplicável(is): "
                    f"{sorted({f['type'] for f in autofix})} — dry-run, nada mudou",
                    findings)

            # FIX (on a snapshot so a worsening batch can be reverted whole)
            _beat(cycle, "fix")
            snapshot = (copy.deepcopy(ctx.consensus), copy.deepcopy(ctx.boxes))
            pre_badness = _badness(findings)
            applied_now: list[str] = []
            for f in sorted(autofix, key=lambda x: (
                    0 if x.get("severity") == "FAIL" else 1,
                    x.get("type", ""), x.get("evidence", ""))):
                fr = apply_fix(ctx, f)
                if fr.ok and fr.changed:
                    applied_now.append(f"{fr.finding_type}: {fr.action}")
                elif not fr.ok:
                    # honest escalation: could not fix deterministically
                    _queue("visual_review_queue",
                           [{**f, "escalated": fr.detail}], queued_felipe)
                    log(f"[loop] cycle {cycle}: '{f['type']}' não consertou "
                        f"honesto -> sobe pro Felipe ({fr.detail})")

            if not applied_now:
                return _finish(STALL, cycle,
                               "nenhum fix aplicável mudou o estado — parando",
                               findings)

            # RE-CHECK
            _beat(cycle, "recheck")
            post = frouter.classified(detect(ctx))
            if _badness(post) > pre_badness:
                ctx.consensus, ctx.boxes = snapshot   # revert whole batch
                return _finish(STALL, cycle,
                               "fix piorou a métrica determinística — REVERTIDO "
                               "(paridade com SAME/WORSE->revert)", findings)

            fixes_applied.extend(applied_now)
            log(f"[loop] cycle {cycle}: PROGRESS — {len(applied_now)} fix(es): "
                f"{'; '.join(applied_now)}")

        return _finish(MAX_CYCLES, max_cycles,
                       "teto de ciclos — anti-runaway", [])
    except Exception as e:  # honest RED: surface, never half-report CLEAN
        return _finish(RED, 0, f"{type(e).__name__}: {e}", [])


# --- real detector wiring (CLI) ----------------------------------------------


def _consensus_detector(_ctx: cfix.FixContext) -> list[dict]:
    """Consensus-only gates (pure, fast): opening_host + wall_overlap on the
    loop's WORKING COPY, so fixes are visible to the re-check."""
    from tools.opening_host_audit import audit_opening_hosts
    from tools.wall_overlap_audit import audit_wall_overlaps
    con = _ctx.consensus or {}
    return cfind.from_deterministic_gates({
        "opening_host": audit_opening_hosts(con),
        "wall_overlap": audit_wall_overlaps(con),
    })


def pending_vision_findings(out_dir: Path) -> list[dict]:
    """Confirmed visual findings from the FP-032 eye (`vision_confirmed.jsonl`,
    written by tools/vision_queue_consumer) — re-injected into the next DETECT.
    Keyed by out_dir, not fixture (spec:106 said fixture; every loop queue is
    already relative to --out, so the code wins). Missing file -> []."""
    p = Path(out_dir) / "vision_confirmed.jsonl"
    if not p.is_file():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue  # tolerant, same stance as the dispatcher's load_queue
        if isinstance(row, dict):
            out.append(row)
    return out


def _load_fixture_consensus(fixture: str) -> dict:
    base = REPO_ROOT / "fixtures" / fixture
    p = base / "consensus_with_human_walls_and_soft_barriers.json"
    if not p.exists():
        cands = sorted(base.glob("consensus*.json"))
        if not cands:
            raise FileNotFoundError(f"no consensus json for fixture {fixture!r}")
        p = cands[0]
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture", default="planta_74")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-cycles", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    res = run_loop(
        fixture=a.fixture,
        detect=lambda ctx: _consensus_detector(ctx) + pending_vision_findings(a.out),
        consensus=_load_fixture_consensus(a.fixture),
        out_dir=a.out,
        max_cycles=a.max_cycles,
        dry_run=a.dry_run,
    )
    print(f"[loop] state={res.state} cycles={res.cycles} "
          f"fixes={len(res.fixes_applied)} felipe_q={res.felipe_queued} "
          f"vision_q={res.vision_queued}")
    # exit-code convention (mirror run_deterministic_gates): 0 done-clean,
    # 1 stalled/error, 3 incomplete (queued for vision/human)
    return {CLEAN: 0, "DRY_RUN": 0, STALL: 1, RED: 1,
            NEEDS_FELIPE: 3, PENDING_VISION: 3, MAX_CYCLES: 3}.get(res.state, 1)


if __name__ == "__main__":
    raise SystemExit(main())
