#!/usr/bin/env python3
"""LL-024 — GPT Auto-Consult Gate.

When the agent hits a real architectural / merge / WARN-carry decision,
this gate packages the context and sends it to the local ChatGPT bridge
at `localhost:8765/ask` automatically — so the user does NOT become a
copy/paste relay for the conversation.

The 10 canonical triggers (only one needs to apply):

1. `oracle_verdict_neq_final_verdict`         — oracle and final disagree
2. `oracle_pass_but_known_warnings`           — oracle PASS but baseline WARNs carry
3. `final_fail_non_obvious_fix`               — FAIL but no clear fix
4. `a_b_c_decision_with_tradeoff`             — multi-path call
5. `risk_of_inventing_geometry`               — Hard Rule #1 territory
6. `about_to_open_new_cycle_post_slice`       — slice complete, new cycle risk
7. `require_oracle_blocks_backend`            — --require-oracle BLOCKED
8. `big_pr_changes_gate_or_spec`              — friction tax risk
9. `user_requested_consult`                   — explicit user trigger
10. `objective_gate_borderline`               — carteiro escalates a WARN (mode B)

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
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tools.consult_tier import choose_gate_tier
from tools.gate_verdict import parse_verdict

REPO_ROOT = Path(__file__).resolve().parent.parent

BRIDGE_URL = "http://localhost:8765"
BRIDGE_HEALTH_TIMEOUT_SEC = 5
BRIDGE_CALL_TIMEOUT_SEC = 260   # > server CLAUDE_TIMEOUT(240); Opus+xhigh is slow

# 10th trigger — the semi-autonomous carteiro (auto_decider) escalating a
# BORDERLINE objective decision (any deterministic WARN) to the delegated gate
# (mode B). Distinct from the 9 human/architectural triggers: it fires from a job,
# not a human, and carries the deterministic evidence (gates, fill%, overlap cm²)
# in the context so the oracle rules on measured facts, never on taste.
OBJECTIVE_GATE_BORDERLINE = "objective_gate_borderline"

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
    OBJECTIVE_GATE_BORDERLINE,
)

# Heavy/high-stakes triggers where one Claude consulting another risks agreement
# bias -> send mode=redteam so the oracle steelmans the opposition first (gate 6.2,
# a no-backend self-critique). The 6.1 multi-oracle router was deleted as fake
# independence / infra-for-infra (gate verdict GO/B, 2026-05-31).
REDTEAM_TRIGGERS = (
    "a_b_c_decision_with_tradeoff",
    "risk_of_inventing_geometry",
    "big_pr_changes_gate_or_spec",
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
    # §6.4 parsed structure (populated when the bridge responds) — gives the
    # verdict teeth: the asker can act on it programmatically instead of
    # re-reading prose.
    verdict: str | None = None
    confidence: str | None = None
    assumptions: list | None = None
    risks: list | None = None
    next_action: str | None = None


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
    parsed: dict | None = None,
) -> Path:
    responses_dir.mkdir(parents=True, exist_ok=True)
    stem = question_path.stem  # same timestamp + trigger
    path = responses_dir / f"{stem}.md"
    parsed_block = ""
    if parsed:
        asum = "; ".join(parsed.get("assumptions") or []) or "—"
        risks = "; ".join(parsed.get("risks") or []) or "—"
        parsed_block = (
            f"## Parsed verdict (§6.4)\n\n"
            f"- Verdict: {parsed.get('verdict') or '—'}\n"
            f"- Confidence: {parsed.get('confidence') or '—'}\n"
            f"- Assumptions: {asum}\n"
            f"- Risks: {risks}\n"
            f"- Next action: {parsed.get('next_action') or '—'}\n\n"
        )
    content = (
        f"# GPT response — {stem.split('_', 1)[-1]}\n\n"
        f"## Timestamp\n\n{_now_utc_iso()}\n\n"
        f"## Question file\n\n`{question_path}`\n\n"
        f"{parsed_block}"
        f"## Raw response\n\n---\n\n{raw}\n\n"
        f"## Decision taken\n\n"
        f"_To be filled by the agent or operator after acting on the response._\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def call_bridge(prompt: str, url: str = BRIDGE_URL, mode: str = "", tier: str = "") -> str:
    """POST {prompt[, mode][, tier]} to /ask. Returns the response text or raises.
    tier='fast' usa Sonnet+effort baixo (segundos); '' deixa o server escolher (deep)."""
    payload = {"prompt": prompt}
    if mode:
        payload["mode"] = mode
    if tier:
        payload["tier"] = tier
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
        # backend-agnóstico: :8765 devolve "response"; o GPT-no-Docker (:8899) "answer".
        return str(parsed.get("response") or parsed.get("answer") or body)
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
    tier: str = "",
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
    mode = "redteam" if g.trigger in REDTEAM_TRIGGERS else ""
    bridge_status = (f"ONLINE — {detail}" + (f" | mode={mode}" if mode else "")
                     + (f" | tier={tier}" if tier else ""))
    question_path = write_question_file(
        questions_dir, g, prompt, bridge_status,
    )
    try:
        raw = call_bridge(prompt, url=url, mode=mode, tier=tier)
    except (urllib.error.URLError, urllib.error.HTTPError,
            TimeoutError, OSError) as e:
        return GateResult(
            status="SKIPPED_OFFLINE",
            detail=f"bridge call failed: {e!r}",
            question_path=question_path,
        )
    parsed = parse_verdict(raw)
    response_path = write_response_file(
        responses_dir, question_path, raw, parsed,
    )
    return GateResult(
        status="ok",
        detail="bridge responded",
        question_path=question_path,
        response_path=response_path,
        raw_response=raw,
        verdict=parsed.get("verdict"),
        confidence=parsed.get("confidence"),
        assumptions=parsed.get("assumptions"),
        risks=parsed.get("risks"),
        next_action=parsed.get("next_action"),
    )


def consult_design_intent(
    question: str,
    context: dict | None = None,
    *,
    purpose: str = "design_intent",
    questions_dir: Path | None = None,
    responses_dir: Path | None = None,
    url: str = BRIDGE_URL,
    explicit_tier: str = "",
    user_override: bool = False,
) -> GateResult:
    """Consulta PRE-MOVEL ao oraculo (ciclo de mobiliario, ANTES do `.skp`).

    Este e o caminho do DesignIntentSpec / pre-movel: extrair design intent,
    transformar referencia visual em checklist, rascunhar regra de layout,
    triagem, preparar prompt. O tier sai de `choose_gate_tier(purpose)` —
    tipicamente FAST (Sonnet+low, segundos), por serem consultas baratas e
    repetitivas. Reusa `run_gate` (mesmo log/parse/audit).

    O trigger e `user_requested_consult` (fluxo dirigido pelo usuario) e o
    `purpose` viaja no `context` p/ rastreio no question file. O veredito visual
    FINAL NAO passa por aqui — ele e `deep` (ver choose_gate_tier / Hard rule).
    """
    tier = choose_gate_tier(
        purpose, explicit_tier=explicit_tier, user_override=user_override,
    )
    ctx = dict(context or {})
    ctx.setdefault("purpose", purpose)
    g = GateInput(
        trigger="user_requested_consult",
        question=question,
        context=ctx,
    )
    return run_gate(
        g,
        questions_dir=questions_dir or (REPO_ROOT / ".ai_bridge" / "questions"),
        responses_dir=responses_dir or (REPO_ROOT / ".ai_bridge" / "responses"),
        url=url,
        tier=tier,
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
    parser.add_argument(
        "--tier", choices=("fast", "deep"), default="",
        help="Tier do oraculo: 'fast' (Sonnet+effort baixo, segundos) p/ rotina/triagem; "
             "vazio ou 'deep' = Opus xhigh (default do server, o JUIZ). "
             "Se dado, VENCE o --purpose (override explicito do usuario).",
    )
    parser.add_argument(
        "--purpose", default="",
        help="Proposito da consulta -> roteia o tier automaticamente via "
             "choose_gate_tier. fast: design_intent, reference_to_checklist, "
             "layout_rule_draft, triage, prompt_prep, exploration. deep: "
             "final_visual_verdict (PINADO), merge_decision, artifact_approval, "
             "architectural_decision, gate_conflict. Vazio/desconhecido -> deep.",
    )
    args = parser.parse_args()

    # Roteamento de tier: --tier explicito vence; senao deriva do --purpose;
    # senao deep (default seguro). --tier conta como override explicito do usuario.
    tier = choose_gate_tier(
        args.purpose, explicit_tier=args.tier, user_override=bool(args.tier),
    )

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
        tier=tier,
    )

    # Report
    print(f"[gate] tier: {tier}"
          + (f" (purpose={args.purpose})" if args.purpose else "")
          + (" [user --tier override]" if args.tier else ""))
    if result.question_path:
        print(f"[gate] question: {result.question_path}")
    if result.response_path:
        print(f"[gate] response: {result.response_path}")
    print(f"[gate] status: {result.status}")
    print(f"[gate] detail: {result.detail}")
    if result.verdict:
        print(f"[gate] verdict: {result.verdict} "
              f"(confidence: {result.confidence or '—'})")

    if result.status == "invalid":
        return 2
    if result.status == "BLOCKED_BRIDGE_OFFLINE":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
