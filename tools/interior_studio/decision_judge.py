"""decision_judge.py — the OBJECTIVE judge façade of the semi-autonomous pipeline.

Fuses the deterministic checkers into ONE objective verdict on a proposal, with a
scalar confidence and a first-class INVALID class. This is the *judgment* half
(pure, no LLM, no network, no consensus I/O); the carteiro (`auto_decider.py`)
does the *gathering* (reads live geometry/overlap) and the *acting*.

Hard boundary — OBJECTIVE and TASTE never cross:
- ``interns.review_program`` is always called with ``with_style=False`` so the
  LLM STYLE intern (gosto/estético) NEVER enters an objective verdict.
- A taste/aesthetic proposal (e.g. a pending ``gap_estilo_*`` from an earlier
  ``with_style=True`` audit) is classified ``TASTE_REFUSED`` — the machine
  abstains; it must NOT be approved/rejected by a gate or the carteiro.

Conservative rule (Felipe, locked): auto-decidable == 100% clean == every
deterministic checker PASS with ZERO warn. Any WARN, or a required checker that
could not run, is BORDERLINE (→ gate mode B, commit 4). A deterministic FAIL is
OBJECTIVE_STRONG_FAIL. Malformed/irrecoverable is INVALID.

Verdict fusion is PURE: ``geometry`` / ``overlap`` are pre-computed verdict
strings ("PASS"|"WARN"|"FAIL") or ``None`` (== not evaluated / SKIPPED). classify
never touches the consensus itself — that keeps it deterministic and hermetically
testable. stdlib + interns only; no clock/random.
"""
from __future__ import annotations

from tools.interior_studio import interns as ic_interns

# ---- vocabulary ----------------------------------------------------------
STRONG_PASS = "OBJECTIVE_STRONG_PASS"
STRONG_FAIL = "OBJECTIVE_STRONG_FAIL"
BORDERLINE = "BORDERLINE"
INVALID = "INVALID"
TASTE_REFUSED = "TASTE_REFUSED"
CLASSIFICATIONS = (STRONG_PASS, STRONG_FAIL, BORDERLINE, INVALID, TASTE_REFUSED)

# fused objective verdict token (maps 1:1 to a classification)
_VERDICT_TO_CLASS = {
    "PASS": STRONG_PASS, "FAIL": STRONG_FAIL, "WARN": BORDERLINE,
    "INVALID": INVALID, "TASTE": TASTE_REFUSED,
}

# a proposal is gosto/estético (machine abstains) when a STRUCTURAL field says so.
# Keyed on intern/kind/type only (precise) — never on free-text title/detail.
_TASTE_MARKERS = ("estilo", "style", "taste", "gosto", "visual", "aparencia",
                  "aparência", "appearance", "aesthetic", "estetic")

_RAN = ("PASS", "WARN", "FAIL")


def _is_taste(gap: dict) -> bool:
    """A consistency_gap that is aesthetic/gosto — the machine must not touch it."""
    if str(gap.get("intern", "")).strip().lower() == "estilo":
        return True
    for field in ("kind", "type"):
        tok = str(gap.get(field, "")).strip().lower()
        if any(m in tok for m in _TASTE_MARKERS):
            return True
    return False


def _clean_coverage(ran: list[str], n_expected: int) -> tuple[float, float]:
    """cleanliness in [0,1] over the checks that RAN (PASS=1, WARN=0.5, FAIL=0)
    and coverage = ran/expected. SKIPPED checks are excluded from cleanliness and
    lower coverage — never fabricated as PASS."""
    if not ran:
        return 0.0, 0.0
    n_pass = ran.count("PASS")
    n_warn = ran.count("WARN")
    cleanliness = (n_pass + 0.5 * n_warn) / len(ran)
    coverage = len(ran) / n_expected if n_expected else 0.0
    return cleanliness, min(coverage, 1.0)


def _confidence(classification: str, ran: list[str], n_expected: int) -> float:
    """Honest scalar from the PASS/WARN/FAIL counts of the checks that ran.

    STRONG_PASS: cleanliness*coverage (→1.0 iff every expected check ran & passed).
    STRONG_FAIL: (1-cleanliness)*coverage (→1.0 iff every ran check FAILed).
    BORDERLINE:  cleanliness*coverage (informational; the gate acts on evidence,
                 not on this number).
    INVALID/TASTE: 0.0 — the machine makes no objective claim.
    """
    if classification in (INVALID, TASTE_REFUSED):
        return 0.0
    cleanliness, coverage = _clean_coverage(ran, n_expected)
    if classification == STRONG_FAIL:
        return round((1.0 - cleanliness) * coverage, 4)
    return round(cleanliness * coverage, 4)


def _gap_confidence(severity: str) -> float:
    """A consistency_gap carries ONE signal — the detector's severity. Confidence
    that the flagged objective finding is real (not confidence in an action)."""
    return {"high": 0.9, "med": 0.6, "low": 0.4}.get(
        str(severity).strip().lower(), 0.5)


def _result(classification, verdict, confidence, evidence, judge_verdicts,
            decision_type, decision_id) -> dict:
    return {"classification": classification, "verdict": verdict,
            "confidence": confidence, "evidence": evidence,
            "judge_verdicts": judge_verdicts, "decision_type": decision_type,
            "decision_id": decision_id}


# ---- furniture_program ---------------------------------------------------
def _classify_program(prop: dict, geometry, overlap) -> dict:
    did = str(prop.get("id", ""))
    items = prop.get("items")
    env = prop.get("environment")
    if not isinstance(items, list) or not items or not isinstance(env, str) or not env:
        return _result(INVALID, "INVALID", 0.0,
                       ["furniture_program malformado: items/environment ausentes"],
                       {"interns": "SKIPPED"}, "furniture_program", did)
    try:
        review = ic_interns.review_program(prop, with_style=False)
    except Exception as e:  # noqa: BLE001 — malformed program is INVALID, never a crash
        return _result(INVALID, "INVALID", 0.0,
                       [f"interns falhou: {e!r}"], {"interns": "ERROR"},
                       "furniture_program", did)

    interns_verdict = review["verdict"]                 # PASS | WARN | FAIL
    geom = geometry if geometry in _RAN else None
    ovl = overlap if overlap in _RAN else None
    judge = {"interns": interns_verdict,
             "geometry_sanity": geom or "SKIPPED",
             "furniture_overlap": ovl or "SKIPPED"}

    ran = [interns_verdict] + [v for v in (geom, ovl) if v is not None]
    n_expected = 3                                      # interns + geometry + overlap
    evidence = [f"{f['intern']}:{f['severity']} {f['title']}"
                for f in review.get("findings", [])]
    evidence.append(f"geometry_sanity={judge['geometry_sanity']}")
    evidence.append(f"furniture_overlap={judge['furniture_overlap']}")

    # precedence: FAIL decisive > WARN/incomplete-coverage BORDERLINE > clean STRONG_PASS
    if "FAIL" in ran:
        verdict = "FAIL"
    elif "WARN" in ran:
        verdict = "WARN"
    elif geom is None or ovl is None:                   # required gate could not run
        verdict = "WARN"                                # can't confirm 100% clean
        evidence.append("cobertura incompleta: gate obrigatório não rodou → borderline")
    else:
        verdict = "PASS"
    classification = _VERDICT_TO_CLASS[verdict]
    return _result(classification, verdict,
                   _confidence(classification, ran, n_expected),
                   evidence, judge, "furniture_program", did)


# ---- consistency_gap -----------------------------------------------------
def _classify_gap(prop: dict) -> dict:
    did = str(prop.get("id", ""))
    severity = str(prop.get("severity", "")).strip().lower()
    if _is_taste(prop):
        return _result(TASTE_REFUSED, "TASTE", 0.0,
                       [f"gap estético (gosto) — máquina não decide: {prop.get('title', did)}"],
                       {"objective": False,
                        "gap_kind": prop.get("kind") or prop.get("intern")},
                       "consistency_gap", did)
    if severity not in ("high", "med", "low"):
        return _result(INVALID, "INVALID", 0.0,
                       [f"gap malformado: severity inválida ({prop.get('severity')!r})"],
                       {"objective": True, "gap_severity": prop.get("severity")},
                       "consistency_gap", did)
    # objective gap: a FLAGGED problem is never "100% clean" → borderline (gate/human).
    # The machine never approves (acknowledges away) nor rejects (dismisses) a real
    # deterministic finding on its own say-so.
    evidence = [f"{prop.get('kind') or prop.get('intern')}:{severity} "
                f"{prop.get('title', '')}".strip()]
    if prop.get("detail"):
        evidence.append(str(prop["detail"]))
    return _result(BORDERLINE, "WARN", _gap_confidence(severity), evidence,
                   {"objective": True, "gap_severity": severity,
                    "gap_kind": prop.get("kind") or prop.get("intern")},
                   "consistency_gap", did)


# ---- public entry --------------------------------------------------------
def classify(proposal: dict, *, geometry: str | None = None,
             overlap: str | None = None) -> dict:
    """Objective verdict on a proposal. Returns
    {classification, verdict, confidence, evidence, judge_verdicts,
     decision_type, decision_id}.

    ``geometry`` / ``overlap``: pre-computed deterministic gate verdicts
    ("PASS"|"WARN"|"FAIL") for the proposal's room, or None (not evaluated →
    SKIPPED). Only consumed for furniture_program. TASTE (aesthetic) is refused;
    the machine never acts on it.
    """
    if not isinstance(proposal, dict):
        return _result(INVALID, "INVALID", 0.0, ["proposal não é um objeto"],
                       {}, "unknown", "")
    ptype = str(proposal.get("type", "")).strip()
    if ptype == "furniture_program":
        return _classify_program(proposal, geometry, overlap)
    if ptype == "consistency_gap":
        return _classify_gap(proposal)
    return _result(INVALID, "INVALID", 0.0,
                   [f"tipo de proposta desconhecido: {ptype!r}"],
                   {}, ptype or "unknown", str(proposal.get("id", "")))
