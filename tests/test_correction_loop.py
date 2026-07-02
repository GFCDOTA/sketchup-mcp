"""FP-033 — correction_loop state-machine tests (hermetic: injected detectors,
no SU/render/network; heartbeat disabled or mocked)."""
from __future__ import annotations

import copy
import json

from tools import correction_finding as cfind
from tools import correction_fixes as cfx
from tools import correction_loop as loop
from tools.correction_fixes import FixContext, FixResult


def _finding(type_="furniture_overlap", sev="FAIL", evidence="e"):
    return {"type": type_, "severity": sev, "source": "deterministic",
            "evidence": evidence}


def _box(module, x0, y0, w, d, z0=0.0, h=30.0):
    return {"module": module, "kind": module, "z0_in": z0, "h_in": h,
            "corners": [[x0, y0], [x0 + w, y0], [x0 + w, y0 + d], [x0, y0 + d]]}


_BIG_ROOM = [(-100.0, -100.0), (300.0, -100.0), (300.0, 300.0), (-100.0, 300.0)]


def _boxes_detector(ctx: FixContext):
    """Real furniture detector over the loop's working boxes."""
    pairs = cfx._overlapping_module_pairs(ctx.boxes or [])
    return [
        cfind.make_finding(
            type="furniture_overlap", severity="FAIL", source="deterministic",
            source_check="furniture_overlap_gate",
            evidence=f"{a} × {b}: {frac:.0%}")
        for a, b, frac in pairs
    ]


# --- acceptance: closes on a real synthetic overlap ---------------------------


def test_closes_on_synthetic_overlap_within_2_cycles(tmp_path):
    boxes = [_box("sofa", 0, 0, 40, 20), _box("mesa", 20, 0, 24, 24)]
    res = loop.run_loop(
        fixture="synthetic", detect=_boxes_detector, boxes=boxes,
        room_poly=_BIG_ROOM, out_dir=tmp_path, heartbeat=None,
        log=lambda m: None)
    assert res.state == loop.CLEAN
    assert res.cycles <= 2
    assert res.fixes_applied                      # a real nudge was applied
    # candidate + result persisted in the out dir, input untouched
    assert (tmp_path / "loop_result.json").exists()
    assert boxes[0]["corners"][0] == [0, 0]       # INPUT boxes never mutated


def test_input_consensus_never_mutated(tmp_path):
    con = {
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "w1", "start": [100.0, 0.0], "end": [100.0, 100.0]},
            {"id": "w2", "start": [101.5, 10.0], "end": [101.5, 90.0]},
        ],
        "openings": [{"id": "d1", "wall_id": "w1", "center": [100.0, 50.0]}],
    }
    before = copy.deepcopy(con)
    res = loop.run_loop(
        fixture="synthetic", detect=loop._consensus_detector, consensus=con,
        out_dir=tmp_path, heartbeat=None, log=lambda m: None)
    assert res.state == loop.CLEAN                # dedup fixed on the copy
    assert con == before                          # Hard Rule #3: input intact
    # the corrected candidate lives in the out dir instead
    cand = json.loads(
        (tmp_path / "consensus_candidate.json").read_text("utf-8"))
    assert {w["id"] for w in cand["walls"]} == {"w1"}


# --- stall ---------------------------------------------------------------------


def test_stops_on_stall_when_fix_changes_nothing(tmp_path):
    detect = lambda ctx: [_finding(evidence="same")]        # noqa: E731
    noop_fix = lambda ctx, f: FixResult(True, f["type"], changed=False)  # noqa: E731
    res = loop.run_loop(
        fixture="synthetic", detect=detect, boxes=[], out_dir=tmp_path,
        apply_fix=noop_fix, heartbeat=None, log=lambda m: None)
    assert res.state == loop.STALL
    assert res.cycles == 1


def test_stops_on_repeated_signature(tmp_path):
    # fixer claims change, but detection is identical next cycle -> STALL @2
    detect = lambda ctx: [_finding(evidence="stuck")]       # noqa: E731
    lying_fix = lambda ctx, f: FixResult(True, f["type"], changed=True,  # noqa: E731
                                         action="pretend")
    res = loop.run_loop(
        fixture="synthetic", detect=detect, boxes=[], out_dir=tmp_path,
        apply_fix=lying_fix, heartbeat=None, log=lambda m: None)
    assert res.state == loop.STALL
    assert res.cycles == 2
    assert "assinatura" in res.reason


# --- revert-if-worse -------------------------------------------------------------


def test_reverts_when_fix_worsens(tmp_path):
    def detect(ctx):
        n = 2 if (ctx.consensus or {}).get("poisoned") else 1
        return [_finding(evidence=f"f{i}") for i in range(n)]

    def bad_fix(ctx, f):
        ctx.consensus["poisoned"] = True          # makes detection worse
        return FixResult(True, f["type"], changed=True, action="poison")

    res = loop.run_loop(
        fixture="synthetic", detect=detect, consensus={}, out_dir=tmp_path,
        apply_fix=bad_fix, heartbeat=None, log=lambda m: None)
    assert res.state == loop.STALL
    assert "REVERTIDO" in res.reason
    assert res.fixes_applied == []                # worsening batch not kept


# --- routing: appearance & vision -----------------------------------------------


def test_appearance_finding_queues_visual_review_never_autofix(tmp_path):
    detect = lambda ctx: [_finding("floating_door", evidence="door")]  # noqa: E731
    calls = []

    def spy_fix(ctx, f):
        calls.append(f)
        return FixResult(True, f["type"], changed=True)

    res = loop.run_loop(
        fixture="synthetic", detect=detect, out_dir=tmp_path,
        apply_fix=spy_fix, heartbeat=None, log=lambda m: None)
    assert res.state == loop.NEEDS_FELIPE
    assert calls == []                            # NEVER auto-fixed
    rows = (tmp_path / "visual_review_queue.jsonl").read_text("utf-8").splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["type"] == "floating_door"


def test_vision_finding_queues_request_without_fabricating(tmp_path):
    detect = lambda ctx: [_finding("global_visual", "WARN", "blur")]  # noqa: E731
    res = loop.run_loop(
        fixture="synthetic", detect=detect, out_dir=tmp_path,
        heartbeat=None, log=lambda m: None)
    assert res.state == loop.PENDING_VISION
    rows = (tmp_path / "vision_requests.jsonl").read_text("utf-8").splitlines()
    assert len(rows) == 1                         # queued, nothing invented
    assert not (tmp_path / "visual_findings.json").exists()


def test_pending_vision_findings_reads_confirmed_and_tolerates_garbage(tmp_path):
    assert loop.pending_vision_findings(tmp_path) == []   # missing file -> []
    (tmp_path / "vision_confirmed.jsonl").write_text(
        json.dumps({"type": "wall_stub", "severity": "WARN",
                    "source": "deterministic", "evidence": "e"}) + "\n"
        + "not json\n", encoding="utf-8")
    out = loop.pending_vision_findings(tmp_path)
    assert len(out) == 1
    assert out[0]["type"] == "wall_stub"


def test_confirmed_vision_finding_reinjected_routes_needs_felipe(tmp_path):
    # the FP-032 eye confirmed an appearance defect (vision_queue_consumer wrote
    # vision_confirmed.jsonl) -> re-injected via detect -> Felipe, NEVER autofix
    confirmed = {"type": "floating_door", "severity": "FAIL",
                 "source": "claude_bridge", "source_check": "visual_oracle",
                 "evidence": "door floats at hall",
                 "consumed_at": "2026-07-01T12:00:00"}
    (tmp_path / "vision_confirmed.jsonl").write_text(
        json.dumps(confirmed) + "\n", encoding="utf-8")
    detect = lambda ctx: loop.pending_vision_findings(tmp_path)  # noqa: E731
    res = loop.run_loop(
        fixture="synthetic", detect=detect, out_dir=tmp_path,
        heartbeat=None, log=lambda m: None)
    assert res.state == loop.NEEDS_FELIPE
    assert res.fixes_applied == []                # appearance never auto-fixed
    rows = (tmp_path / "visual_review_queue.jsonl").read_text("utf-8").splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["type"] == "floating_door"


def test_confirmed_vision_type_never_requeues_to_the_eye(tmp_path):
    # anti-ping-pong: um wall_stub JÁ confirmado pelo olho (source_check
    # visual_oracle) não volta pra vision_requests.jsonl — o resíduo
    # qualitativo é do Felipe, senão request<->confirm nunca termina
    confirmed = {"type": "wall_stub", "severity": "WARN",
                 "source": "claude_bridge", "source_check": "visual_oracle",
                 "evidence": "texto livre do olho, não-determinístico",
                 "consumed_at": "2026-07-01T12:00:00"}
    (tmp_path / "vision_confirmed.jsonl").write_text(
        json.dumps(confirmed) + "\n", encoding="utf-8")
    detect = lambda ctx: loop.pending_vision_findings(tmp_path)  # noqa: E731
    res = loop.run_loop(
        fixture="synthetic", detect=detect, out_dir=tmp_path,
        heartbeat=None, log=lambda m: None)
    assert res.state == loop.NEEDS_FELIPE            # não PENDING_VISION
    assert not (tmp_path / "vision_requests.jsonl").exists()
    rows = (tmp_path / "visual_review_queue.jsonl").read_text(
        "utf-8").splitlines()
    assert len(rows) == 1


def test_ack_makes_confirmed_rows_single_shot(tmp_path):
    # uma confirmação alimenta EXATAMENTE um run: depois do ack, o próximo run
    # não re-injeta e CLEAN volta a ser alcançável no out dir persistente
    confirmed = {"type": "floating_door", "severity": "FAIL",
                 "source": "claude_bridge", "source_check": "visual_oracle",
                 "evidence": "door floats"}
    (tmp_path / "vision_confirmed.jsonl").write_text(
        json.dumps(confirmed) + "\n", encoding="utf-8")
    injected = loop.pending_vision_findings(tmp_path)
    assert len(injected) == 1
    loop.ack_confirmed_findings(tmp_path, injected)
    assert loop.pending_vision_findings(tmp_path) == []   # acked -> não volta
    res = loop.run_loop(
        fixture="synthetic",
        detect=lambda ctx: loop.pending_vision_findings(tmp_path),
        out_dir=tmp_path, heartbeat=None, log=lambda m: None)
    assert res.state == loop.CLEAN                    # alcançável de novo


def test_pending_vision_findings_dedups_duplicate_confirmations(tmp_path):
    row = {"type": "wall_stub", "severity": "WARN", "source": "claude_bridge",
           "source_check": "visual_oracle", "evidence": "e"}
    (tmp_path / "vision_confirmed.jsonl").write_text(
        json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    assert len(loop.pending_vision_findings(tmp_path)) == 1


def test_run_loop_purges_stale_outputs_from_previous_run(tmp_path):
    # out dir persistente entre tasks: cycle_*/ e consensus_candidate.json de um
    # run anterior seriam commitados como evidência do run atual — purgados no
    # início; as filas *.jsonl sobrevivem
    stale_cycle = tmp_path / "cycle_03"
    stale_cycle.mkdir(parents=True)
    (stale_cycle / "findings.json").write_text("[]\n", encoding="utf-8")
    (tmp_path / "consensus_candidate.json").write_text(
        '{"stale": true}\n', encoding="utf-8")
    (tmp_path / "vision_requests.jsonl").write_text(
        '{"type": "wall_stub"}\n', encoding="utf-8")
    res = loop.run_loop(
        fixture="synthetic", detect=lambda ctx: [], out_dir=tmp_path,
        heartbeat=None, log=lambda m: None)
    assert res.state == loop.CLEAN
    assert not stale_cycle.exists()                       # stale cycle purgado
    assert not (tmp_path / "consensus_candidate.json").exists()  # sem fix = sem candidata
    assert (tmp_path / "cycle_01" / "findings.json").exists()    # run atual
    assert (tmp_path / "vision_requests.jsonl").exists()         # fila intacta


def test_unfixable_autofix_escalates_to_felipe(tmp_path):
    # routed AUTOFIX but no handler -> honest escalation to the human queue
    detect = lambda ctx: [_finding("opening_host_mismatch", evidence="x")]  # noqa: E731
    res = loop.run_loop(
        fixture="synthetic", detect=detect, consensus={}, out_dir=tmp_path,
        heartbeat=None, log=lambda m: None)       # real cfx.apply: no handler
    assert res.state == loop.STALL                # nothing changed -> stop
    rows = (tmp_path / "visual_review_queue.jsonl").read_text("utf-8").splitlines()
    assert len(rows) == 1
    assert "escalated" in json.loads(rows[0])


# --- resilience ------------------------------------------------------------------


def test_heartbeat_offline_does_not_block(tmp_path):
    def dead_heartbeat(sid, cycle, stage):
        raise ConnectionError("bridge down")

    res = loop.run_loop(
        fixture="synthetic", detect=lambda ctx: [], out_dir=tmp_path,
        heartbeat=dead_heartbeat, log=lambda m: None)
    assert res.state == loop.CLEAN                # completed despite dead bridge


def test_max_cycles_is_anti_runaway(tmp_path):
    counter = {"n": 0}

    def shifting_detect(ctx):                     # new signature every cycle
        counter["n"] += 1
        return [_finding(evidence=f"shift{counter['n']}")]

    churn_fix = lambda ctx, f: FixResult(True, f["type"], changed=True,  # noqa: E731
                                         action="churn")
    res = loop.run_loop(
        fixture="synthetic", detect=shifting_detect, boxes=[], out_dir=tmp_path,
        max_cycles=3, apply_fix=churn_fix, heartbeat=None, log=lambda m: None)
    assert res.state == loop.MAX_CYCLES
    assert res.cycles == 3


def test_dry_run_reports_without_touching_state(tmp_path):
    boxes = [_box("sofa", 0, 0, 40, 20), _box("mesa", 20, 0, 24, 24)]
    before = copy.deepcopy(boxes)
    res = loop.run_loop(
        fixture="synthetic", detect=_boxes_detector, boxes=boxes,
        room_poly=_BIG_ROOM, out_dir=tmp_path, dry_run=True,
        heartbeat=None, log=lambda m: None)
    assert res.state == "DRY_RUN"
    assert boxes == before
    assert res.fixes_applied == []


def test_no_machine_appearance_verdict_in_loop_modules():
    import re
    from pathlib import Path
    pattern = re.compile(r"""['"](IMPROVED|SAME|WORSE)['"]""")
    for mod in ("correction_loop.py", "correction_fixes.py",
                "vision_queue_consumer.py"):
        text = (Path(loop.__file__).parent / mod).read_text(encoding="utf-8")
        assert not pattern.search(text), f"{mod} must never emit appearance verdicts"
