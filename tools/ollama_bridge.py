#!/usr/bin/env python3
"""STDLIB-only client for the local Ollama LLMs at 127.0.0.1:11434.

No third-party deps (urllib + base64 only) so the studio dashboard can import
it anywhere. Maps friendly role names to the installed models, supports text
and vision (image) prompts, and degrades gracefully when Ollama is offline or
slow instead of raising.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request

# host configurável: no container Docker, OLLAMA_HOST=http://host.docker.internal:11434 alcança o host
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

# Friendly role -> installed model name. Unknown roles fall through to being
# treated as a literal model name (see _resolve_model).
ROLE_MODEL: dict[str, str] = {
    "deepseek": "deepseek-r1:14b",
    "qwen": "qwen2.5-coder:14b",
    "llama": "llama3.1:8b",
    "vision": "qwen2.5vl:7b",
    "designer": "interior-designer:latest",
    "coder": "coder-assistant:latest",
}


def _resolve_model(role: str) -> str:
    """Map a role to a model name; fall back to the role string itself."""
    return ROLE_MODEL.get(role, role)


def _post_json(path: str, payload: dict, timeout: int) -> dict:
    """POST a JSON body to Ollama and return the decoded JSON response."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_HOST}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def available() -> list[str]:
    """Return installed model names (GET /api/tags, 3s timeout); [] if offline."""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return []
    return [m.get("name", "") for m in body.get("models", []) if m.get("name")]


def online() -> bool:
    """True if Ollama answers on :11434."""
    return bool(available())


def ask(
    role: str,
    prompt: str,
    image: str | None = None,
    timeout: int = 120,
) -> dict:
    """Run a one-shot generation; never raises on offline/timeout.

    Resolves `role` via ROLE_MODEL (or uses it as a literal model name). When
    `image` is given, reads the file and sends it base64-encoded for a vision
    model. Returns {"ok": True, "model": ..., "response": ...} or
    {"ok": False, "error": ...}.
    """
    model = _resolve_model(role)
    payload: dict = {"model": model, "prompt": prompt, "stream": False}

    if image is not None:
        try:
            with open(image, "rb") as fh:
                payload["images"] = [base64.b64encode(fh.read()).decode("ascii")]
        except OSError as exc:
            return {"ok": False, "error": f"cannot read image {image!r}: {exc}"}

    try:
        body = _post_json("/api/generate", payload, timeout)
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.code}: {exc.reason}"}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": f"ollama unreachable: {exc}"}
    except ValueError as exc:
        return {"ok": False, "error": f"bad response: {exc}"}

    return {
        "ok": True,
        "model": body.get("model", model),
        "response": body.get("response", ""),
    }


def _cli(argv: list[str]) -> int:
    """models | ask <role> <prompt...> | ask-img <role> <img> <prompt...>"""
    if not argv:
        print("usage: ollama_bridge.py models | ask <role> <prompt...> | "
              "ask-img <role> <img_path> <prompt...>", file=sys.stderr)
        return 2

    cmd = argv[0]
    if cmd == "models":
        names = available()
        print("\n".join(names) if names else "(ollama offline)")
        return 0 if names else 1

    if cmd == "ask":
        if len(argv) < 3:
            print("usage: ask <role> <prompt...>", file=sys.stderr)
            return 2
        out = ask(argv[1], " ".join(argv[2:]))
    elif cmd == "ask-img":
        if len(argv) < 4:
            print("usage: ask-img <role> <img_path> <prompt...>", file=sys.stderr)
            return 2
        out = ask(argv[1], " ".join(argv[3:]), image=argv[2])
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2

    if out["ok"]:
        print(out["response"])
        return 0
    print(f"ERROR: {out['error']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
