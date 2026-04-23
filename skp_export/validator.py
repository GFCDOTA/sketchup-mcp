"""Schema validation for ``observed_model.json`` (schema v2.x).

Wraps :mod:`jsonschema` with repo-specific conveniences: the schema file
lives alongside this module, and the helpers return a typed namedtuple
so callers can differentiate "valid" from "not even loadable".
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

try:
    import jsonschema
    from jsonschema import Draft7Validator
except ImportError:  # pragma: no cover - requirements-dev.txt must include this
    jsonschema = None  # type: ignore
    Draft7Validator = None  # type: ignore


SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "observed_model_v2.json"


@dataclass
class ValidationResult:
    """Outcome of validating one observed_model.json file."""

    valid: bool
    errors: List[str]
    data: Optional[dict] = None


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_file(path: Path) -> ValidationResult:
    """Validate an ``observed_model.json`` file. Returns all errors.

    If the file cannot be loaded, ``valid`` is False and ``errors``
    contains one explanatory line.
    """
    path = Path(path)
    if not path.is_file():
        return ValidationResult(valid=False, errors=[f"file not found: {path}"])

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ValidationResult(valid=False, errors=[f"invalid JSON: {exc}"])

    return validate_dict(data)


def validate_dict(data: dict) -> ValidationResult:
    """Validate an already-parsed dict against the v2 schema."""
    if jsonschema is None:  # pragma: no cover
        return ValidationResult(
            valid=False,
            errors=["jsonschema is not installed; add it to requirements-dev.txt"],
            data=data,
        )

    schema = _load_schema()
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if not errors:
        return ValidationResult(valid=True, errors=[], data=data)

    messages = []
    for err in errors:
        loc = "/".join(str(p) for p in err.path) or "<root>"
        messages.append(f"{loc}: {err.message}")
    return ValidationResult(valid=False, errors=messages, data=data)


def validate_run(run_dir: Path) -> ValidationResult:
    """Validate the observed_model.json inside a run directory."""
    return validate_file(Path(run_dir) / "observed_model.json")
