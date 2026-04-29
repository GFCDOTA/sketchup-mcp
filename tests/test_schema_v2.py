"""Validate real observed_model.json outputs against the formal schema.

The contract is maintained in docs/schema/observed_model.schema.json (JSON
Schema Draft 2020-12). This test keeps the schema honest against the actual
pipeline output, not just prose: every run directory listed here was produced
by the pipeline, and each MUST validate cleanly.

Rules of engagement when this test fails:
- If the schema rejects a real output, the SCHEMA is wrong (loosen it).
  Do not mutate pipeline output to satisfy a draft schema.
- If a run directory has not been produced yet on this machine, the test
  is skipped (not failed), so fresh checkouts stay green.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]
SCHEMA = REPO / "docs" / "schema" / "observed_model.schema.json"

try:
    import jsonschema  # noqa: F401
    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover — exercised only when dep missing
    HAS_JSONSCHEMA = False


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
@pytest.mark.parametrize(
    "run_dir",
    [
        "runs/openings_refine_final",
        "runs/synth_studio",
        "runs/synth_2br",
        "runs/synth_3br",
        "runs/synth_lshape",
        "runs/raster_baseline_prefilter",
    ],
)
def test_observed_model_matches_schema_v2(run_dir: str) -> None:
    model_path = REPO / run_dir / "observed_model.json"
    if not model_path.exists():
        pytest.skip(f"{run_dir} not run yet on this machine")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    model = json.loads(model_path.read_text(encoding="utf-8"))

    import jsonschema as js
    # Raises jsonschema.ValidationError on mismatch with a pointer to the
    # offending path — the traceback itself is the useful artifact here.
    js.validate(instance=model, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_schema_itself_is_valid() -> None:
    """Guardrail: the schema must itself be a valid Draft 2020-12 document.

    Catches typos in $defs / $ref plumbing before they silently degrade
    validation into a permissive pass.
    """
    import jsonschema as js
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator_cls = js.validators.validator_for(schema)
    validator_cls.check_schema(schema)
