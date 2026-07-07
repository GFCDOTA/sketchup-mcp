"""FP-033 — finding router: classify a unified `correction_finding` into a route.

The router is the *new intelligence* of the closed correction loop. Given a typed
finding (from the deterministic gates OR from `visual_findings.v1` / FP-032), it
decides who acts:

- ``DETERMINISTIC_AUTOFIX`` — the loop fixes it itself (a registered, source-
  supported handler exists for this type; ``tools/correction_fixes.py``).
- ``NEEDS_VISION``          — no deterministic measure; needs the FP-032 visual ACL
  to confirm/localize, then the typed visual finding is re-injected next cycle.
- ``NEEDS_FELIPE``          — an APPEARANCE judgment, or a fix that would invent
  geometry / touch the builder/`.skp`. NEVER auto. Felipe (chrome-only) decides.

Honesty / safety rule: ``AUTOFIX_TYPES`` is an explicit WHITELIST. Any type not
recognized routes to ``NEEDS_FELIPE`` — the loop never auto-fixes something it does
not explicitly know how to fix deterministically. That is what stops a blind or
novel finding from triggering a phantom "correction".

Source-of-truth table: ``docs/specs/FP-033_closed_correction_loop.md`` §Algorithm.
Pure module — no I/O, deterministic, fully unit-testable without an SKP build.
"""
from __future__ import annotations

DETERMINISTIC_AUTOFIX = "DETERMINISTIC_AUTOFIX"
NEEDS_VISION = "NEEDS_VISION"
NEEDS_FELIPE = "NEEDS_FELIPE"
ROUTES = (DETERMINISTIC_AUTOFIX, NEEDS_VISION, NEEDS_FELIPE)

# Types the loop can fix deterministically, source-supported (consensus/brain only,
# never inventing walls/furniture). The router only says "auto-fixable in kind";
# `correction_fixes` must still have a real handler before one is applied.
AUTOFIX_TYPES = frozenset({
    "wall_overlap",            # duplicate/overlapping walls -> dedup consensus
    "opening_host_mismatch",   # opening hosted on wrong wall -> re-host (graph-based)
    "furniture_overlap",       # móvel-sobre-móvel -> re-run brain / documented nudge
    "outside_room",            # móvel fora do cômodo -> re-anchor ao cômodo
    "blocks_door",             # móvel na soleira -> clearance
    "degenerate_footprint",    # bbox degenerada -> regenera box do brain
    "degenerate_height",
    "absurd_bbox",             # escala explodida -> regenera box do brain
    "off_axis",                # eixo torto -> regenera box do brain
    "underground",             # z0 abaixo do piso -> re-assenta no piso
})

# Qualitative / residual types with NO deterministic measure: route to the FP-032
# eye, which confirms + localizes; the loop re-injects the typed visual finding.
NEEDS_VISION_TYPES = frozenset({
    "global_visual",
    "scale_rotation",
    "wall_stub",
})
# visual_findings.v1 axes that are inherently qualitative (route by axis too).
_VISION_AXES = frozenset({"global_visual", "scale_rotation"})

# Appearance / builder-touching / verdict types: ALWAYS Felipe, NEVER auto.
NEEDS_FELIPE_TYPES = frozenset({
    "position_fidelity",        # re-posicionar contra o PDF = aparência
    "floating_door",
    "orphan_glass",
    "orphan_glass_panel",
    "bad_window_aperture",
    "misplaced_window",
    "full_height_window_void",
    "misplaced_soft_barrier",
    "missing_wall_continuation",  # oracle-seen wall gap -> builder/.skp = aparência
    "global_visual_fail",         # oracle's top-level appearance FAIL
    "appearance_verdict",         # IMPROVED / SAME / WORSE — the human-only gate
})

# Hard guard: these NEVER leave NEEDS_FELIPE, whatever else matches. The final
# appearance verdict is the human's exclusive call (proven un-automatable).
_NEVER_AUTO = frozenset({"appearance_verdict"})


def _norm(value) -> str:
    return str(value or "").strip().lower()


def classify(finding: dict) -> str:
    """Return the route for a unified correction_finding. Pure.

    Precedence: hard-guard (never-auto) > deterministic whitelist > vision >
    explicit Felipe > safe default (NEEDS_FELIPE). An unknown type is never
    auto-fixed — it escalates to the human.

    Termination rule: a finding the eye itself already confirmed
    (``source_check == "visual_oracle"``, set by
    ``correction_finding.from_visual_findings_v1``) NEVER routes back to
    NEEDS_VISION — re-asking the eye about its own answer would ping-pong
    request<->confirm forever (each confirmation carries fresh evidence text,
    so the request signature is always "new"). Once seen, the residual
    qualitative call is the human's.
    """
    ftype = _norm((finding or {}).get("type"))
    axis = _norm((finding or {}).get("axis"))
    eye_confirmed = _norm((finding or {}).get("source_check")) == "visual_oracle"

    if ftype in _NEVER_AUTO:
        return NEEDS_FELIPE
    if ftype in AUTOFIX_TYPES:
        return DETERMINISTIC_AUTOFIX
    if ftype in NEEDS_VISION_TYPES or axis in _VISION_AXES:
        return NEEDS_FELIPE if eye_confirmed else NEEDS_VISION
    if ftype in NEEDS_FELIPE_TYPES:
        return NEEDS_FELIPE
    return NEEDS_FELIPE  # safe default: unknown/ambiguous -> human, never auto-fix


def route_reason(finding: dict) -> str:
    """One-line rationale for the chosen route (for the loop's per-cycle log)."""
    route = classify(finding)
    ftype = _norm((finding or {}).get("type")) or "?"
    return {
        DETERMINISTIC_AUTOFIX:
            f"'{ftype}': handler determinístico source-supported disponível",
        NEEDS_VISION:
            f"'{ftype}': qualitativo — precisa do olho FP-032 confirmar/localizar",
        NEEDS_FELIPE:
            f"'{ftype}': muda aparência / inventa geometria / é veredito — só Felipe",
    }[route]


def classified(findings: list[dict]) -> list[dict]:
    """Return copies of ``findings`` with ``route`` filled. Does NOT mutate input."""
    out: list[dict] = []
    for f in findings or []:
        g = dict(f)
        g["route"] = classify(g)
        out.append(g)
    return out
