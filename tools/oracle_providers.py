"""FP-030 — Pluggable visual oracle provider interface.

Defines a small abstraction that lets `run_skp_visual_review.py`
delegate visual judgment to different backends:

- `none` — explicit "no oracle attempted" path
- `chatgpt_bridge_image` — POST to the ChatGPT desktop bridge with
  multipart images; falls back to writing an `oracle_request_package/`
  for external manual review when the bridge cannot accept images
- `future_vision_api` — placeholder for a future Anthropic/OpenAI
  Vision API integration

Design rules

1. Providers MUST validate `OracleRequest.image_paths` exist before
   any network call.
2. Providers MUST distinguish three negative statuses:
   - `unavailable` (bridge/process not reachable)
   - `incompatible` (reachable but cannot accept images per its
     schema)
   - `invalid_response` (returned malformed JSON / missing keys)
3. Providers MUST NOT fabricate a verdict. If they cannot decide,
   they write a request package and return `status=incompatible`
   or `status=unavailable`.
4. The package writer is the universal escape hatch — even when
   the bridge is unusable, the operator gets a self-contained
   directory they can drop into ChatGPT manually.

Companion code: `tools/run_skp_visual_review.py` (orchestrator).
Tests: `tests/test_oracle_providers.py`.
"""
from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

ORACLE_BRIDGE_URL = "http://localhost:8765"
ORACLE_BRIDGE_HEALTH_TIMEOUT_SEC = 5
ORACLE_BRIDGE_CALL_TIMEOUT_SEC = 120

VISUAL_FINDINGS_SCHEMA_VERSION = "visual_findings.v1"


# ---- request / response types ---------------------------------------


@dataclass
class OracleRequest:
    """Self-validating request payload."""
    prompt: str
    image_paths: list[Path]
    context: dict
    expected_schema: dict | None = None

    def validate(self) -> None:
        if not self.prompt or not self.prompt.strip():
            raise ValueError("OracleRequest.prompt is empty")
        if not self.image_paths:
            raise ValueError("OracleRequest.image_paths is empty")
        missing = [str(p) for p in self.image_paths if not p.exists()]
        if missing:
            raise FileNotFoundError(
                f"OracleRequest references missing image paths: {missing}"
            )


@dataclass
class OracleResponse:
    """Uniform response across providers.

    `status` semantics:
    - `ok`                — provider returned a usable result; `raw` set,
                            `normalized_findings` set to a v1-shaped dict
    - `unavailable`       — provider could not be reached at runtime
    - `incompatible`      — provider reachable but cannot accept the
                            request shape (e.g. text-only bridge)
    - `invalid_response`  — provider returned but the payload could not be
                            parsed into the expected schema
    - `not_implemented`   — provider exists in the registry but is a stub
    """
    provider: str
    status: str
    detail: str = ""
    raw: dict | None = None
    normalized_findings: dict | None = None
    package_dir: Path | None = None


# ---- request package writer (universal escape hatch) ---------------


def write_oracle_request_package(
    out_dir: Path,
    request: OracleRequest,
    status: str,
    reason: str,
) -> Path:
    """Write a self-contained directory the operator can drop into
    ChatGPT (or any vision tool) manually.

    Structure:

    ```
    <out_dir>/oracle_request_package/
      prompt.md
      images/
        <copies of each image_paths file>
      context.json
      expected_schema.json
      README.md
    ```

    Returns the package root.
    """
    pkg = out_dir / "oracle_request_package"
    images_dir = pkg / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    (pkg / "prompt.md").write_text(request.prompt, encoding="utf-8")
    (pkg / "context.json").write_text(
        json.dumps(request.context, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if request.expected_schema is not None:
        (pkg / "expected_schema.json").write_text(
            json.dumps(request.expected_schema, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    for src in request.image_paths:
        shutil.copy2(src, images_dir / src.name)

    readme = [
        "# Oracle request package",
        "",
        f"Status: **{status}**",
        f"Reason: {reason}",
        "",
        "## How to use",
        "",
        "1. Open the destination (e.g. ChatGPT desktop, web).",
        "2. Paste the contents of `prompt.md`.",
        "3. Drag the three images from `images/` into the conversation.",
        "4. Optionally attach `context.json` with the geometry stats.",
        "5. Expect the reply to follow `expected_schema.json`",
        "   (`visual_findings.v1`).",
        "",
        "## Why this package exists",
        "",
        "The automated oracle path could not deliver visual judgment in",
        "this run (status above). To keep the validator honest, the request",
        "was written to disk so a human reviewer can stand in for the oracle.",
        "",
        "Once the bridge gains real image-attachment support OR a Vision API",
        "is plugged in, this package is no longer needed for that fixture.",
    ]
    (pkg / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    return pkg


# ---- provider base + registry ---------------------------------------


class OracleProvider:
    """Base class. Subclasses MUST implement `name`, `probe`, `call`."""
    name: str = "base"

    def probe(self) -> tuple[bool, str]:
        """Return (available, detail). MUST NOT raise."""
        raise NotImplementedError

    def call(self, req: OracleRequest, *, out_dir: Path) -> OracleResponse:
        """Run the request. MUST validate inputs first. MUST NOT
        fabricate verdicts.

        On failure, write an oracle_request_package to `out_dir`."""
        raise NotImplementedError


class NoneProvider(OracleProvider):
    """Explicit 'no oracle attempted' path. Always returns unavailable."""
    name = "none"

    def probe(self) -> tuple[bool, str]:
        return False, "--oracle none (no oracle attempted)"

    def call(self, req: OracleRequest, *, out_dir: Path) -> OracleResponse:
        return OracleResponse(
            provider=self.name,
            status="unavailable",
            detail="explicit none mode",
        )


class ChatGPTBridgeImageProvider(OracleProvider):
    """ChatGPT desktop bridge at localhost:8765.

    Current bridge contract (E:/chatgpt-bridge/bridge.py):
        POST /ask {prompt: str, timeout?: int}

    This provider tries multipart/form-data first (assuming a future
    bridge supports it). If the bridge rejects (404/422/400) OR the
    health probe shows it's text-only, returns `incompatible` and
    writes an `oracle_request_package/` for manual review.
    """
    name = "chatgpt_bridge_image"

    def __init__(self, url: str = ORACLE_BRIDGE_URL):
        self.url = url

    def probe(self) -> tuple[bool, str]:
        try:
            req = urllib.request.Request(f"{self.url}/health", method="GET")
            with urllib.request.urlopen(
                req, timeout=ORACLE_BRIDGE_HEALTH_TIMEOUT_SEC,
            ) as resp:
                if resp.status != 200:
                    return False, f"bridge /health returned {resp.status}"
                body = resp.read().decode("utf-8")
                # Heuristic: if the body advertises image capability, treat
                # as compatible. Otherwise we'll learn at call-time.
                return True, f"bridge healthy; body={body[:200]}"
        except (urllib.error.URLError, urllib.error.HTTPError,
                TimeoutError, OSError) as e:
            return False, f"bridge unreachable at {self.url}: {e!r}"

    def _attempt_call_with_images(self, req: OracleRequest) -> dict | None:
        """Try a multipart POST. Returns parsed JSON dict on success, None on
        non-fatal failure (so caller can switch to incompatible + package).

        Raises on truly unexpected exceptions.
        """
        # Build a multipart body. The current bridge does NOT accept this
        # — it expects {prompt: str}. So we expect 422 here and fall back.
        boundary = "----oracleboundary"
        parts: list[bytes] = []
        parts.append(
            f"--{boundary}\r\n".encode()
            + b'Content-Disposition: form-data; name="prompt"\r\n\r\n'
            + req.prompt.encode("utf-8")
            + b"\r\n"
        )
        ctx_json = json.dumps(req.context, ensure_ascii=False).encode("utf-8")
        parts.append(
            f"--{boundary}\r\n".encode()
            + b'Content-Disposition: form-data; name="context_json"\r\n\r\n'
            + ctx_json
            + b"\r\n"
        )
        for p in req.image_paths:
            parts.append(
                f"--{boundary}\r\n".encode()
                + f'Content-Disposition: form-data; name="image_{p.stem}"; '
                  f'filename="{p.name}"\r\n'.encode()
                + b"Content-Type: image/png\r\n\r\n"
                + p.read_bytes()
                + b"\r\n"
            )
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)

        http_req = urllib.request.Request(
            f"{self.url}/ask",
            data=body,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urllib.request.urlopen(
                http_req, timeout=ORACLE_BRIDGE_CALL_TIMEOUT_SEC,
            ) as resp:
                raw = resp.read().decode("utf-8")
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return None
        except urllib.error.HTTPError as e:
            # 422 (validation) or 400 = bridge does not accept images
            if e.code in {400, 422, 404}:
                return None
            raise
        except (urllib.error.URLError, OSError):
            return None

    def call(self, req: OracleRequest, *, out_dir: Path) -> OracleResponse:
        try:
            req.validate()
        except (ValueError, FileNotFoundError) as e:
            return OracleResponse(
                provider=self.name,
                status="invalid_response",  # really invalid_request, but keep
                detail=f"request validation failed: {e}",
            )

        available, detail = self.probe()
        if not available:
            pkg = write_oracle_request_package(
                out_dir, req, status="unavailable",
                reason=detail,
            )
            return OracleResponse(
                provider=self.name,
                status="unavailable",
                detail=detail,
                package_dir=pkg,
            )

        raw = self._attempt_call_with_images(req)
        if raw is None:
            # Bridge reachable but did not accept the image payload
            pkg = write_oracle_request_package(
                out_dir, req, status="incompatible",
                reason=(
                    "bridge rejected multipart/image payload; current "
                    "schema is text-only (POST /ask {prompt: str})"
                ),
            )
            return OracleResponse(
                provider=self.name,
                status="incompatible",
                detail="bridge schema is text-only; package written for manual review",
                package_dir=pkg,
            )

        normalized = _normalize_to_visual_findings(raw)
        if normalized is None:
            pkg = write_oracle_request_package(
                out_dir, req, status="invalid_response",
                reason="bridge returned JSON but did not match visual_findings.v1",
            )
            return OracleResponse(
                provider=self.name,
                status="invalid_response",
                detail="bridge response could not be normalized to v1 schema",
                raw=raw, package_dir=pkg,
            )

        return OracleResponse(
            provider=self.name,
            status="ok",
            detail="bridge returned valid visual_findings",
            raw=raw,
            normalized_findings=normalized,
        )


class FutureVisionAPIProvider(OracleProvider):
    """Stub for a future Anthropic/OpenAI Vision API integration.

    Intentionally not_implemented in this PR. Lives here so that
    `run_skp_visual_review.py --oracle future_vision_api` does NOT
    silently fall back to deterministic-only — it returns an
    explicit `not_implemented` status that the orchestrator treats
    as BLOCKED.
    """
    name = "future_vision_api"

    def probe(self) -> tuple[bool, str]:
        return False, "future_vision_api is not implemented in this build"

    def call(self, req: OracleRequest, *, out_dir: Path) -> OracleResponse:
        try:
            req.validate()
            pkg = write_oracle_request_package(
                out_dir, req, status="not_implemented",
                reason=(
                    "FutureVisionAPIProvider is a placeholder. "
                    "Plug an SDK (anthropic, openai, etc.) and replace "
                    "this provider."
                ),
            )
            return OracleResponse(
                provider=self.name,
                status="not_implemented",
                detail="stub provider — wire a real Vision API",
                package_dir=pkg,
            )
        except (ValueError, FileNotFoundError) as e:
            return OracleResponse(
                provider=self.name,
                status="invalid_response",
                detail=f"request validation failed: {e}",
            )


# ---- normalization ---------------------------------------------------


_AXIS_KEYS = {
    "wall_fidelity", "door_fidelity", "window_fidelity",
    "room_fidelity", "scale_rotation", "global_visual",
}


def _normalize_to_visual_findings(raw: dict) -> dict | None:
    """Coerce an oracle response into a visual_findings.v1 shape.

    Returns None if the payload lacks the minimum required structure
    (top_level_verdict + axes object with the 6 keys).
    """
    if not isinstance(raw, dict):
        return None
    verdict = raw.get("top_level_verdict")
    axes = raw.get("axes")
    if verdict not in {"PASS", "WARN", "FAIL"}:
        return None
    if not isinstance(axes, dict):
        return None
    if not _AXIS_KEYS.issubset(axes.keys()):
        return None

    out: dict[str, Any] = {
        "schema_version": VISUAL_FINDINGS_SCHEMA_VERSION,
        "top_level_verdict": verdict,
        "axes": {},
        "findings": [],
        "source": "oracle_bridge",
        "raw_confidence": raw.get("confidence"),
    }
    for k in _AXIS_KEYS:
        a = axes[k]
        if not isinstance(a, dict):
            return None
        v = a.get("verdict")
        if v not in {"PASS", "WARN", "FAIL"}:
            return None
        out["axes"][k] = {"verdict": v, "evidence": str(a.get("evidence", ""))}
    findings = raw.get("findings") or []
    if isinstance(findings, list):
        for f in findings:
            if not isinstance(f, dict):
                continue
            out["findings"].append({
                "id": str(f.get("id", "vf_oracle")),
                "severity": f.get("severity", "WARN"),
                "axis": f.get("axis", "global_visual"),
                "type": f.get("type", "other"),
                "location": f.get("location", ""),
                "evidence_image": f.get("evidence_image", ""),
                "evidence": f.get("evidence", ""),
            })
    return out


# ---- registry --------------------------------------------------------


_REGISTRY: dict[str, type[OracleProvider]] = {
    "none": NoneProvider,
    "chatgpt_bridge_image": ChatGPTBridgeImageProvider,
    "future_vision_api": FutureVisionAPIProvider,
}


def available_provider_names() -> list[str]:
    return sorted(_REGISTRY.keys())


def get_provider(name: str) -> OracleProvider:
    if name not in _REGISTRY:
        raise ValueError(
            f"unknown oracle provider {name!r}; available: "
            f"{available_provider_names()}"
        )
    return _REGISTRY[name]()
