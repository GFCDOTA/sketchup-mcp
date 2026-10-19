"""SU runner mode protocol — safe lifecycle for SketchUp subprocess.

Every Python launcher that calls `Popen` on `SketchUp.exe` should
import `parse_mode` and `should_terminate` from this module. The
safe default is `interactive` (do NOT terminate SU) to protect
concurrent human inspection sessions.

See CLAUDE.md §18, LL-015, FP-023 for the full protocol.

Usage
-----

```python
from tools.su_runner_safety import parse_mode, should_terminate, log_mode

mode = parse_mode()   # reads --mode / --no-terminate / RUN_MODE
log_mode(mode)        # prints [su-runner] mode=<X>; terminate_on_done=<bool>

if mode != "attach":
    proc = subprocess.Popen([SU, target_skp])
    # ... poll done marker ...
    if should_terminate(mode):
        proc.terminate()
        print(f"[su-runner] terminated own child PID {proc.pid}")
    else:
        print(f"[su-runner] artifact ready; SU left running ({proc.pid})")
```

Modes
-----

- `headless` / `ci` — MAY terminate only `proc.pid` (own child).
  NEVER `taskkill /IM SketchUp.exe` (would kill user's instances).
- `interactive` / `debug` — MUST NOT terminate. Done marker means
  "artifact ready", NOT "kill SU".
- `attach` / `manual` — NEVER touch any SU process. Runner reads
  files/markers only; no `Popen`.

Safe default
------------

When `RUN_MODE` is unset AND no CLI flag is given, default is
`interactive`. This protects any concurrent human SU session.
"""
from __future__ import annotations

import argparse
import os
import sys

MODES = ("headless", "ci", "interactive", "debug", "attach", "manual")
HEADLESS_MODES = frozenset({"headless", "ci"})
INTERACTIVE_MODES = frozenset({"interactive", "debug"})
ATTACH_MODES = frozenset({"attach", "manual"})


def parse_mode(
    *,
    argv: list[str] | None = None,
    env: dict[str, str] | None = None,
    default: str = "interactive",
) -> str:
    """Resolve runtime mode from (in priority order):

    1. ``--no-terminate`` CLI flag (forces ``interactive``).
    2. ``--mode <name>`` CLI flag.
    3. ``RUN_MODE`` environment variable.
    4. ``default`` argument (default: ``"interactive"``).

    Unknown values fall back to the safe default with a stderr
    warning.

    Other CLI args are left untouched so this can be called from
    a launcher that has its own argparse later.
    """
    if argv is None:
        argv = sys.argv[1:]
    if env is None:
        env = os.environ

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mode", default=None)
    parser.add_argument("--no-terminate", action="store_true")
    args, _ = parser.parse_known_args(argv)

    if args.no_terminate:
        return "interactive"
    if args.mode:
        if args.mode in MODES:
            return args.mode
        sys.stderr.write(
            f"[su-runner] WARN: unknown --mode {args.mode!r}; "
            f"falling back to {default!r}\n"
        )
        return default

    env_mode = env.get("RUN_MODE")
    if env_mode:
        if env_mode in MODES:
            return env_mode
        sys.stderr.write(
            f"[su-runner] WARN: unknown RUN_MODE={env_mode!r}; "
            f"falling back to {default!r}\n"
        )
    return default


def should_terminate(mode: str) -> bool:
    """True iff the runner may terminate its own child SU process.

    Even when True, the runner must terminate ONLY its own
    ``proc.pid``; never ``taskkill /IM SketchUp.exe`` (that would
    kill any concurrent human SU session — FP-019).
    """
    return mode in HEADLESS_MODES


def is_attach(mode: str) -> bool:
    """True iff the runner must NOT spawn or touch any SU process.

    In attach mode the runner only reads files/markers produced by
    a previous run or an external SU session.
    """
    return mode in ATTACH_MODES


def log_mode(mode: str, *, prefix: str = "[su-runner]") -> None:
    """Print the resolved mode + termination policy to stdout.

    Mandatory in every SU launcher so the user can see whether
    their parallel SU instance is at risk.
    """
    terminate = should_terminate(mode)
    print(
        f"{prefix} mode={mode}; "
        f"terminate_on_done={terminate}; "
        f"attach_only={is_attach(mode)}"
    )


# Self-test when run directly: smoke-validate the resolver
if __name__ == "__main__":
    cases = [
        (["--mode", "headless"], {}, "headless"),
        (["--mode", "interactive"], {}, "interactive"),
        (["--mode", "attach"], {}, "attach"),
        (["--no-terminate"], {}, "interactive"),
        ([], {"RUN_MODE": "ci"}, "ci"),
        ([], {"RUN_MODE": "manual"}, "manual"),
        ([], {}, "interactive"),
        (["--mode", "garbage"], {}, "interactive"),
        ([], {"RUN_MODE": "garbage"}, "interactive"),
    ]
    failures = 0
    for argv, env, expected in cases:
        actual = parse_mode(argv=argv, env=env)
        ok = actual == expected
        flag = "ok" if ok else "FAIL"
        print(f"  [{flag}] argv={argv} env={env} -> {actual} (expected {expected})")
        if not ok:
            failures += 1
    print(f"\n{len(cases) - failures}/{len(cases)} resolver cases pass")
    sys.exit(0 if failures == 0 else 1)
