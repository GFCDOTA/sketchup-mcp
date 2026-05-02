"""CLI entry point for the planta validator.

Usage::

    # validate every pending entry once and exit
    python -m validator.run --once

    # poll the manifest every 30s and validate new entries as they appear
    python -m validator.run --watch

    # serve the FastAPI app on port 8770
    python -m validator.run --port 8770

    # with vision-LLM critique enabled (Ollama qwen2.5vl:7b)
    python -m validator.run --once --vision
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _cmd_once(args) -> int:
    from validator.pipeline import validate_pending
    out = validate_pending(REPO_ROOT, vision=args.vision,
                           limit=args.limit, force=args.force)
    print(f"validated {len(out)} entries")
    for r in out:
        v = r["validation"]
        scorer = v.get("scorer", "?")
        score = v.get("score", 0.0)
        n_issues = len(v.get("issues", []))
        print(f"  {r['id']}  scorer={scorer:<10} score={score:.3f} issues={n_issues}")
    return 0


def _cmd_watch(args) -> int:
    from tools.png_history import list_entries
    from validator.pipeline import validate_pending
    print(f"[watch] polling {REPO_ROOT/'runs/png_history/manifest.jsonl'} every {args.interval}s")
    seen_pending = -1
    while True:
        pending = sum(1 for e in list_entries() if e.get("validation") is None)
        if pending and pending != seen_pending:
            print(f"[watch] {pending} pending — validating")
            out = validate_pending(REPO_ROOT, vision=args.vision)
            print(f"[watch]   processed {len(out)}")
        seen_pending = pending
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n[watch] bye")
            return 0


def _cmd_serve(args) -> int:
    import uvicorn
    uvicorn.run(
        "validator.service:app",
        host=args.host, port=args.port,
        reload=False, log_level="info",
    )
    return 0


def _cmd_show(args) -> int:
    from tools.png_history import list_entries
    for e in list_entries():
        v = e.get("validation") or {}
        print(json.dumps({
            "id": e["id"],
            "kind": e.get("kind"),
            "score": v.get("score"),
            "issues": [i.get("code") for i in v.get("issues", [])],
        }, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="planta validator CLI")
    ap.add_argument("--port", type=int, default=None,
                    help="serve FastAPI on this port (e.g. 8770)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--once", action="store_true", help="validate all pending and exit")
    ap.add_argument("--watch", action="store_true", help="watch manifest and validate as it grows")
    ap.add_argument("--show", action="store_true", help="print one-line summary per entry")
    ap.add_argument("--interval", type=int, default=30, help="seconds between watch polls")
    ap.add_argument("--vision", action="store_true",
                    help="enable Ollama qwen2.5vl:7b critique")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap number of entries processed by --once")
    ap.add_argument("--force", action="store_true",
                    help="re-run scorer on entries already validated")
    args = ap.parse_args(argv)

    if args.show:
        return _cmd_show(args)
    if args.once:
        return _cmd_once(args)
    if args.watch:
        return _cmd_watch(args)
    if args.port is not None:
        return _cmd_serve(args)

    # default: print help
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
