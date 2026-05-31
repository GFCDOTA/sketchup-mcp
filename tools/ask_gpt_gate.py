#!/usr/bin/env python3
"""LL-024 — GPT Auto-Consult Gate.

When the agent hits a real architectural / merge / WARN-carry decision,
this gate packages the context and sends it to the local ChatGPT bridge
at `localhost:8765/ask` automatically — so the user does NOT become a
copy/paste relay for the conversation.

The 9 canonical triggers (only one needs to apply):

1. `oracle_verdict_neq_final_verdict`         — oracle and final disagree
2. `oracle_pass_but_known_warnings`           — oracle PASS but baseline WARNs carry
3. `final_fail_non_obvious_fix`               — FAIL but no clear fix
4. `a_b_c_decision_with_tradeoff`             — multi-path call
5. `risk_of_inventing_geometry`               — Hard Rule #1 territory
6. `about_to_open_new_cycle_post_slice`       — slice complete, new cycle risk
7. `require_oracle_blocks_backend`            — --require-oracle BLOCKED
8. `big_pr_changes_gate_or_spec`              — friction tax risk
9. `user_requested_consult`                   — explicit user trigger

NOT consult when (per LL-024 spec):
- typo / doc-only trivial
- small evident test
- merge of small green PR
- local cleanup with no impact
- decision already covered by canonical rule
- loop that would repeat a previously answered question

Usage (CLI):

    python -m tools.ask_gpt_gate \\
        --trigger oracle_pass_but_known_warnings \\
        --context-file /tmp/ctx.json \\
        --question "Should PR #206 merge?" \\
        --questions-dir .ai_bridge/questions \\
        --responses-dir .ai_bridge/responses

Behaviour:
- Validates trigger is one of the 9 canonical types.
- Loads context JSON (free-shape; will be embedded in the question file).
- Writes `<questions-dir>/<UTC>_<trigger>.md` with the full prompt.
- Probes `localhost:8765/health`. If reachable, POSTs the prompt to
  `/ask` and saves the response to `<responses-dir>/<UTC>_<trigger>.md`.
- If bridge offline AND `--require-consult`: exits non-zero (3) with
  `BLOCKED_BRIDGE_OFFLINE`. The question file is still written for the
  operator to forward manually.
- If bridge offline AND no `--require-consult`: status is
  `GPT_CONSULT_SKIPPED_OFFLINE` and the question file alone is the
  evidence.

This is text-only — for image-based visual review, use the FP-030
Visual Oracle Gate (`tools/run_skp_visual_review.py --oracle ollama_vision`).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BRIDGE_URL = "http://localhost:8765"
BRIDGE_HEALTH_TIMEOUT_SEC = 5
BRIDGE_CALL_TIMEOUT_SEC = 120

CANONICAL_TRIGGERS = (
    "oracle_verdict_neq_final_verdict",
    "oracle_pass_but_known_warnings",
    "final_fail_non_obvious_fix",
    "a_b_c_decision_with_tradeoff",
    "risk_of_inventing_geometry",
    "about_to_open_new_cycle_post_slice",
    "require_oracle_blocks_backend",
    "big_pr_changes_gate_or_spec",
    "user_requested_consult",
)


# ---- types -----------------------------------------------------------


@dataclass
class GateInput:
    trigger: str
    question: str
    context: dict
    repo_state: dict | None = None

    def validate(self) -> None:
        if self.trigger not in CANONICAL_TRIGGERS:
            raise ValueError(
                f"unknown trigger {self.trigger!r}; expected one of: "
                f"{CANONICAL_TRIGGERS}"
            )
        if not self.question or not self.question.strip():
            raise ValueError("GateInput.question is empty")


@dataclass
class GateResult:
    status: str  # ok | SKIPPED_OFFLINE | BLOCKED_BRIDGE_OFFLINE | invalid
    detail: str
    question_path: Path | None = None
    response_path: Path | None = None
    raw_response: str | None = None


# ---- helpers ---------------------------------------------------------


def _now_utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def probe_bridge(url: str = BRIDGE_URL) -> tuple[bool, str]:
    """Health-check the ChatGPT bridge. Returns (available, detail)."""
    try:
        req = urllib.request.Request(f"{url}/health", method="GET")
        with urllib.request.urlopen(
            req, timeout=BRIDGE_HEALTH_TIMEOUT_SEC,
        ) as resp:
            ok = resp.status == 200
            body = resp.read().decode("utf-8", errors="replace")[:200]
            return ok, f"bridge /health returned {resp.status}; body={body}"
    except (urllib.error.URLError, urllib.error.HTTPError,
            TimeoutError, OSError) as e:
        return False, f"bridge unreachable at {url}: {e!r}"


def build_prompt(g: GateInput) -> str:
    """Render the full prompt sent to ChatGPT.

    Keeps the format predictable so the response is easier to act on
    later (and so the same prompt can be pasted manually if needed)."""
    parts = [
        "# GPT Auto-Consult Gate — context-driven question",
        "",
        f"## Trigger\n\n`{g.trigger}`",
        "",
    ]
    if g.repo_state:
        parts.extend([
            "## Repo state",
            "",
            "```json",
            json.dumps(g.repo_state, indent=2, ensure_ascii=False),
            "```",
            "",
        ])
    parts.extend([
        "## Context",
        "",
        "```json",
        json.dumps(g.context, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Question",
        "",
        g.question.strip(),
        "",
        "## Answer format",
        "",
        "Respond with a short structured answer:",
        "",
        "- **Verdict**: GO / NO-GO / MORE-INFO / VISUAL_REVIEW",
        "- **Confidence**: high / medium / low",
        "- **Reasoning**: 2-4 sentences",
        "- **Assumptions**: bullets — what you ASSUMED or could NOT verify",
        "- **Risks**: bullets, what could go wrong",
        "- **Suggested next action**: 1-2 lines",
        "",
        "No markdown fences around your response. No marketing fluff.",
    ])
    return "\n".join(parts)


def write_question_file(
    questions_dir: Path, g: GateInput, prompt: str, bridge_status: str,
) -> Path:
    questions_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{_now_utc_stamp()}_{g.trigger}"
    path = questions_dir / f"{stem}.md"
    content = (
        f"# GPT Auto-Consult — {g.trigger}\n\n"
        f"## Timestamp\n\n{_now_utc_iso()}\n\n"
        f"## Bridge status\n\n{bridge_status}\n\n"
        f"## Prompt sent (or that would have been sent)\n\n"
        f"---\n\n{prompt}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def write_response_file(
    responses_dir: Path, question_path: Path, raw: str,
) -> Path:
    responses_dir.mkdir(parents=True, exist_ok=True)
    stem = question_path.stem  # same timestamp + trigger
    path = responses_dir / f"{stem}.md"
    content = (
        f"# GPT response — {stem.split('_', 1)[-1]}\n\n"
        f"## Timestamp\n\n{_now_utc_iso()}\n\n"
        f"## Question file\n\n`{question_path}`\n\n"
        f"## Raw response\n\n---\n\n{raw}\n\n"
        f"## Decision taken\n\n"
        f"_To be filled by the agent or operator after acting on the response._\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def call_bridge(prompt: str, url: str = BRIDGE_URL) -> str:
    """POST {prompt} to /ask. Returns the response text or raises."""
    payload = {"prompt": prompt}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/ask",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=BRIDGE_CALL_TIMEOUT_SEC) as resp:
        body = resp.read().decode("utf-8")
    try:
        parsed = json.loads(body)
        return str(parsed.get("response", body))
    except json.JSONDecodeError:
        return body


# ---- main gate entry -------------------------------------------------


def run_gate(
    g: GateInput,
    *,
    questions_dir: Path,
    responses_dir: Path,
    require_consult: bool = False,
    url: str = BRIDGE_URL,
) -> GateResult:
    """Validate, probe, write, call. Returns GateResult.

    Honest about what happened — does not fabricate a response if the
    bridge is offline.
    """
    try:
        g.validate()
    except ValueError as e:
        return GateResult(
            status="invalid", detail=str(e),
        )

    prompt = build_prompt(g)
    available, detail = probe_bridge(url)

    if not available:
        bridge_status = f"OFFLINE — {detail}"
        question_path = write_question_file(
            questions_dir, g, prompt, bridge_status,
        )
        if require_consult:
            return GateResult(
                status="BLOCKED_BRIDGE_OFFLINE",
                detail=detail,
                question_path=question_path,
            )
        return GateResult(
            status="SKIPPED_OFFLINE",
            detail=detail,
            question_path=question_path,
        )

    # Bridge is up — record question first, then call
    bridge_status = f"ONLINE — {detail}"
    question_path = write_question_file(
        questions_dir, g, prompt, bridge_status,
    )
    try:
        raw = call_bridge(prompt, url=url)
    except (urllib.error.URLError, urllib.error.HTTPError,
            TimeoutError, OSError) as e:
        return GateResult(
            status="SKIPPED_OFFLINE",
            detail=f"bridge call failed: {e!r}",
            question_path=question_path,
        )
    response_path = write_response_file(responses_dir, question_path, raw)
    return GateResult(
        status="ok",
        detail="bridge responded",
        question_path=question_path,
        response_path=response_path,
        raw_response=raw,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trigger", required=True, choices=CANONICAL_TRIGGERS,
        help="One of the 9 canonical trigger types",
    )
    parser.add_argument(
        "--question", required=True,
        help="The specific question to ask",
    )
    parser.add_argument(
        "--context-file", type=Path,
        help="Path to a JSON file with the decision context (free shape)",
    )
    parser.add_argument(
        "--repo-state-file", type=Path,
        help="Optional path to a JSON file with repo state info "
             "(branch, develop_sha, pr)",
    )
    parser.add_argument(
        "--questions-dir", type=Path,
        default=REPO_ROOT / ".ai_bridge" / "questions",
    )
    parser.add_argument(
        "--responses-dir", type=Path,
        default=REPO_ROOT / ".ai_bridge" / "responses",
    )
    parser.add_argument(
        "--require-consult", action="store_true",
        help="If bridge offline, BLOCK with non-zero exit instead of "
             "writing SKIPPED_OFFLINE.",
    )
    parser.add_argument("--bridge-url", default=BRIDGE_URL)
    args = parser.parse_args()

    context: dict = {}
    if args.context_file and args.context_file.exists():
        context = json.loads(args.context_file.read_text(encoding="utf-8"))
    repo_state = None
    if args.repo_state_file and args.repo_state_file.exists():
        repo_state = json.loads(
            args.repo_state_file.read_text(encoding="utf-8")
        )

    g = GateInput(
        trigger=args.trigger,
        question=args.question,
        context=context,
        repo_state=repo_state,
    )
    result = run_gate(
        g,
        questions_dir=args.questions_dir,
        responses_dir=args.responses_dir,
        require_consult=args.require_consult,
        url=args.bridge_url,
    )

    # Report
    if result.question_path:
        print(f"[gate] question: {result.question_path}")
    if result.response_path:
        print(f"[gate] response: {result.response_path}")
    print(f"[gate] status: {result.status}")
    print(f"[gate] detail: {result.detail}")

    if result.status == "invalid":
        return 2
    if result.status == "BLOCKED_BRIDGE_OFFLINE":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
