"""FP-033 slice 3 — vision queue consumer: drain `vision_requests.jsonl` through
the FP-032 eye (`POST /ask-vision` on the :8765 bridge) and write back confirmed
findings for the next correction_loop cycle.

The loop (`tools/correction_loop`) NEVER fabricates a visual finding: it queues
a request and finishes PENDING_VISION. This consumer closes that gap:

    vision_requests.jsonl --drain--> POST /ask-vision --> vision_confirmed.jsonl

which `correction_loop.pending_vision_findings()` re-injects into DETECT.

Honesty contract (FP-032 parity by REUSE, not copy):
- renders must be EXPLICIT (`--render` / `image_paths`) -> otherwise
  BLOCKED_NEEDS_RENDER (no HTTP call at all). There is deliberately NO
  "newest PNG in artifacts/review" fallback: in a fresh NOC worktree every
  committed PNG has the same checkout mtime, so that pick is arbitrary and can
  hand the eye a stale before/after montage or a COMMITTED corrupted
  negative-dogfood render — findings fabricated by evidence selection.
- bridge offline/incompatible -> BLOCKED_NEEDS_FP032 (queue intact, ZERO
  fabricated findings — the provider's honest negatives pass straight through)
- an oracle FAIL only stands if the backend has a DISCRIMINATED
  negative_dogfood report (`run_skp_visual_review.promote_oracle_verdict` +
  `degrade_unproven_fail`); otherwise it is degraded to WARN — the same
  promotion rule as the runner
- the queue file is append-only: consumption is recorded in
  `vision_consumed.jsonl` (signatures), never by rewriting the queue

CLI:
    python -m tools.vision_queue_consumer --out runs/loop_x --fixture planta_74 \\
        --render <png> [--render <png>]... [--tier deep] [--bridge-url URL]

Exit codes: 0 = EMPTY/DRAINED, 3 = BLOCKED_*, 1 = unexpected error.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from tools.jsonl_io import append_jsonl, queue_key, read_jsonl

BACKEND = "claude_bridge_vision"


def _pending_requests(out_dir: Path) -> list[dict]:
    """Queue rows not yet consumed. The jsonl is an append-only log: re-runs of
    the loop append duplicate rows, so dedup by signature AND subtract what
    `vision_consumed.jsonl` already recorded."""
    consumed = {tuple(r.get("signature") or ()) for r in
                read_jsonl(out_dir / "vision_consumed.jsonl")}
    pending: list[dict] = []
    seen: set = set()
    for row in read_jsonl(out_dir / "vision_requests.jsonl"):
        sig = queue_key(row)
        if sig in consumed or sig in seen:
            continue
        seen.add(sig)
        pending.append(row)
    return pending


def _confirm_prompt(fixture: str, pending: list[dict]) -> str:
    """Context for the request (and the manual-review package on failure). The
    provider builds its own strict v1 extraction prompt over HTTP, but renders
    the same pending list into it via ``context["pending"]`` — the eye always
    sees WHICH findings it was asked to confirm/localize."""
    return (
        f"Confirm-or-localize task for fixture {fixture!r}: the deterministic "
        "correction loop queued the findings below as NEEDS_VISION (no "
        "deterministic measure exists). Look at the renders and report what "
        "you SEE as visual_findings.v1 — confirm, re-localize or drop each "
        "one; never invent a defect that is not visible.\n\n"
        "Pending findings:\n"
        + json.dumps(pending, indent=2, ensure_ascii=False) + "\n"
    )


def _degrade_unproven(vf: dict, discriminated: bool) -> dict:
    """FP-032 promotion parity (imported rules, not copies): an unproven backend
    cannot cast a hard FAIL — top level AND per-finding severities degrade."""
    from tools.run_skp_visual_review import degrade_unproven_fail, promote_oracle_verdict
    effective, note = promote_oracle_verdict(
        vf.get("top_level_verdict", "PASS"), discriminated)
    vf["top_level_verdict"] = effective
    if note:
        vf["promotion_note"] = note
    if not discriminated:
        for f in vf.get("findings", []) or []:
            if isinstance(f, dict):
                degrade_unproven_fail(f, key="severity")
    return vf


def drain(
    out_dir: Path,
    *,
    fixture: str,
    provider=None,
    image_paths: list[Path] | None = None,
    discrimination: Callable[[], dict | None] | None = None,
    now: str | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    """Drain the pending vision requests in `out_dir` through the FP-032 eye.

    One provider call per drain (all pending findings ride together). Every
    exit path writes `consumer_result.json`; only DRAINED touches
    `vision_consumed.jsonl` / `vision_confirmed.jsonl`.
    """
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if now is None:
        from datetime import datetime
        now = datetime.now().isoformat(timespec="seconds")

    def _result(status: str, **extra) -> dict:
        res = {"status": status, "fixture": fixture, "at": now, **extra}
        (out_dir / "consumer_result.json").write_text(
            json.dumps(res, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        detail = extra.get("detail")
        log(f"[vision-consumer] {fixture} -> {status}"
            + (f" ({detail})" if detail else ""))
        return res

    pending = _pending_requests(out_dir)
    if not pending:
        return _result("EMPTY", consumed=0, pending_left=0)

    # renders BEFORE any HTTP: no pixels -> nothing to show the eye. Explicit
    # only — an implicit repo-wide pick is not traceable to the current model
    # state (see module docstring), so its absence BLOCKS instead of guessing.
    images = [Path(p) for p in (image_paths or []) if Path(p).is_file()]
    if not images:
        return _result(
            "BLOCKED_NEEDS_RENDER",
            detail="no explicit render traceable to the current model state "
                   "(--render) — no HTTP attempted",
            pending_left=len(pending))

    if provider is None:
        from tools.oracle_providers import get_provider
        provider = get_provider(BACKEND)
    ok, reason = provider.probe()
    if not ok:
        return _result("BLOCKED_NEEDS_FP032", detail=reason,
                       pending_left=len(pending))

    from tools.oracle_providers import OracleRequest
    req = OracleRequest(
        prompt=_confirm_prompt(fixture, pending),
        image_paths=images,
        context={"fixture": fixture, "pending": pending},
        expected_schema={"schema_version": "visual_findings.v1"},
    )
    resp = provider.call(req, out_dir=out_dir)
    if resp.status != "ok":
        # honest negative (unavailable/incompatible/invalid_response): the
        # request stays in the queue, nothing is fabricated
        return _result("BLOCKED_NEEDS_FP032",
                       detail=f"{resp.status}: {resp.detail}",
                       pending_left=len(pending), provider_status=resp.status)

    vf = dict(resp.normalized_findings or {})
    if discrimination is not None:
        report = discrimination()
    else:
        from tools.run_skp_visual_review import load_latest_discrimination
        report = load_latest_discrimination(fixture, BACKEND)
    discriminated = bool(report and report.get("result") == "DISCRIMINATED")
    vf = _degrade_unproven(vf, discriminated)

    from tools import correction_finding as cfind
    confirmed = cfind.from_visual_findings_v1(vf)
    for f in confirmed:
        f["consumed_at"] = now
        f["fixture"] = fixture
        f["discriminated"] = discriminated
    # consumed BEFORE confirmed: the two appends are separate opens, and a
    # crash/timeout between them must not leave confirmed findings without a
    # consumption record — that would re-drain the same pending set (a second
    # call against the live :8765 + duplicated confirmed rows). Losing one
    # confirmation batch on crash is the cheaper failure: the request is
    # simply gone from the queue, nothing is duplicated or fabricated.
    append_jsonl(out_dir / "vision_consumed.jsonl", [
        {"signature": list(queue_key(p)), "consumed_at": now}
        for p in pending
    ])
    if confirmed:
        append_jsonl(out_dir / "vision_confirmed.jsonl", confirmed)
    return _result("DRAINED", consumed=len(pending), confirmed=len(confirmed),
                   pending_left=0, provider_status="ok",
                   discriminated=discriminated)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fixture", default="planta_74")
    ap.add_argument("--render", action="append", type=Path, default=None,
                    help="render(s) explícitos do estado ATUAL do modelo; "
                         "obrigatório pra drenar (sem render rastreável = "
                         "BLOCKED_NEEDS_RENDER, nunca um PNG arbitrário do repo)")
    ap.add_argument("--tier", default=None)
    ap.add_argument("--bridge-url", default=None)
    a = ap.parse_args()

    from tools.oracle_providers import get_provider
    provider = get_provider(BACKEND)
    if a.bridge_url and hasattr(provider, "url"):
        provider.url = a.bridge_url
    if a.tier and hasattr(provider, "tier"):
        provider.tier = a.tier

    res = drain(a.out, fixture=a.fixture, provider=provider,
                image_paths=a.render)
    status = res.get("status", "")
    if status in ("EMPTY", "DRAINED"):
        return 0
    if status.startswith("BLOCKED_"):
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
