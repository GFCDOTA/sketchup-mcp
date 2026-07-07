# sketchup-mcp — HANDOFF (2026-06-28): the CI gate ("a esteira que se valida sozinha")

> **For:** the next maintainer / successor session.
> **What this is:** a **small, single-purpose** handoff for the `chore/ci-gate` branch. It closes the **oldest open follow-up** in the project — *"minimal GitHub Actions pytest workflow (the no-CI lesson) — still absent"* (logged in both the [2026-06-14](2026-06-14_learnings_and_handoff.md) and [2026-06-24](2026-06-24_interior_studio_and_class_program_handoff.md) handoffs). The repo now has CI again, as **one** focused gate.
> **Read order:** the **2026-06-24 doc** for the current mission/architecture (three-layer stack, the studio, the classes), then this. Everything in those docs is unchanged — this only adds the build gate on top.

---

## 0. TL;DR

- **Branch:** `chore/ci-gate` @ `b0f11e4` = `develop` (`e3b1fda`) **+ exactly one commit**. No divergence, fast-forwardable.
- **The one commit:** `chore(ci): add GitHub Actions gate (pytest + fidelity gates + MCP smoke)` — adds `.github/workflows/ci.yml` (79 lines) and a CI badge to `README.md`. That's the whole diff (2 files, +81).
- **`develop` currently has NO workflows** — earlier workflows ("CI" / "Repo Health" / "Quality Gates", last run 2026-05-26) were removed from the tree at some point. This re-introduces CI **from scratch, as a single legible file**, not a patch onto an existing one.
- **It is green-by-construction.** I ran all three jobs locally (Windows, py3.12, fresh venv) exactly as CI does — **all pass** (§3). The numbers in the commit message are real: **901 passed / 5 skipped**, **291 ruff findings** deferred.
- **It has not run in CI yet.** Triggers are `pull_request` + `push` on `develop|main` (plus `workflow_dispatch`). A push to the `chore/ci-gate` branch itself does **not** trigger it and there is **no open PR**, so the first real run happens when a PR is opened or the branch merges. **No PR is open** — Felipe to open/merge.
- **Next moves:** open PR `chore/ci-gate → develop`; on merge CI goes live and the badge resolves; then a **separate** chore for the 291 ruff findings (132 auto-fixable). See §5.

---

## 1. What the gate does

`.github/workflows/ci.yml` — three independent jobs, **all SketchUp-free** (every SU-dependent step degrades via `skipif`, so the runner never needs SU). Triggers on PR/push to `develop|main` and manual `workflow_dispatch`; `concurrency` cancels superseded runs on the same ref; `MPLBACKEND=Agg` forces matplotlib's headless backend (the runner has no `DISPLAY`).

| Job | What it proves | How |
|---|---|---|
| **`tests`** | the contract/gate suites hold | `pip install -e ".[dev]"` → `python -m pytest tests/ -q`, on a **matrix of py3.11 + py3.12** (`fail-fast: false`) |
| **`fidelity-gates`** | the deterministic detectors PASS on the canonical fixtures | `pip install -e .` → `python -m tools.run_deterministic_gates --fixture planta_74` then `--fixture quadrado`. **The exit code IS the gate** (`PASS=0 / FAIL=1 / INCOMPLETE=3`) — a gate that "couldn't run" is INCOMPLETE, never a silent green |
| **`mcp-server`** | the MCP slice-1 server actually speaks the protocol | `pip install -e ".[mcp]"` → `python -m tools.mcp_server.smoke` (in-process exercise of the **9 tools**) then `python -m tools.mcp_server.stdio_check` (real `initialize` / `tools-list` / `call_tool` handshake over stdio, the way Claude Code launches it) |

**Deliberately out of the gate (for now):** `ruff`. There are **291 pre-existing lint findings** — gating on them would block every PR. The commit message records this as a separate chore. (`ruff` is still installed via the `[dev]` extra, so a future job can flip it on once the backlog is cleared.)

`README.md` gains a status badge pointing at `?branch=develop`; it will read "no status" until the workflow exists on `develop` (i.e. after merge), then go green.

---

## 2. How it sits in the repo

- **Base:** `develop` @ `e3b1fda` ("chore(gitignore): ignora kanban/relay/inbox runtime…"). `chore/ci-gate` is develop + the single CI commit — `git log origin/develop..origin/chore/ci-gate` is exactly one line, and develop has nothing ci-gate lacks.
- **No conflict surface:** the commit only **adds** `.github/workflows/ci.yml` (new file) and appends two lines to `README.md`. Nothing else is touched.
- **Honors the branch rules** (CLAUDE.md Hard Rule #4): it's a `chore/<x>` branch off develop, destined for develop, never main directly.

> Note for archaeology: the 2026-05-26 runs of workflows named *CI / Repo Health / Quality Gates* came from workflow files that **no longer exist on develop**. Don't expect to find them — this `ci.yml` is the current, only CI. If you want the old hygiene/quality-gate jobs back, they'd be a new addition, not a revert.

---

## 3. Verification — run locally, all green (2026-06-28)

Reproduced every CI job in an isolated worktree (per the multi-agent worktree rule) on Windows, Python 3.12.10, a fresh venv, `MPLBACKEND=Agg`, installing `-e ".[dev,mcp]"`. CI runs ubuntu-latest, but the logic is platform-independent and SU-free, so this is a faithful preview:

| CI step | Command | Result |
|---|---|---|
| `tests` | `python -m pytest tests/ -q` | **901 passed, 5 skipped** in ~35 s. The 5 skips are SU-dependent (`test_window_aperture_geometry.py` — needs a built `quadrado_v3_aperture` / `geometry_report.json`), exactly the `skipif` degradation the commit promises |
| `fidelity-gates` (planta_74) | `python -m tools.run_deterministic_gates --fixture planta_74` | `overall=PASS` — `opening_host PASS (0/12)`, `wall_overlap PASS (0 pairs)`, **exit 0** |
| `fidelity-gates` (quadrado) | `… --fixture quadrado` | `overall=PASS` — `opening_host PASS (0/1)`, `wall_overlap PASS`, **exit 0** |
| `mcp-server` (smoke) | `python -m tools.mcp_server.smoke` | `SMOKE PASS` — all **9 tools** registered & exercised (`furniture_class_derive`, `kitchen_ergonomics_audit`, `list_capabilities`, `promote_canonical`, `reference_to_grammar`, `room_gates`, `run_deterministic_gates`, `skp_inventory`, `validate_grammar_spec`), **exit 0** |
| `mcp-server` (stdio) | `python -m tools.mcp_server.stdio_check` | `STDIO HANDSHAKE PASS` — `initialize` / `ListTools` / two `call_tool`s over real stdio, **exit 0** |
| (deferred) ruff | `python -m ruff check .` | **291 errors** (132 auto-fixable) — confirms the "kept out of the gate" claim |

Every claim in the commit message checks out. The gate is real, not aspirational.

---

## 4. Current state

- **Branch:** `chore/ci-gate` @ `b0f11e4`, pushed to origin, **no open PR**.
- **`develop`** @ `e3b1fda`, clean.
- **First CI run:** has **not happened** — the workflow only fires on PR/push to `develop|main` or manual dispatch, and none of those has occurred for this file yet. Expect the inaugural run the moment a PR is opened against develop (or on merge).
- Everything from the 2026-06-24 handoff (ports `:8765`/`:8782`/`:8783`, Ollama on `11434`, the 5 frozen furniture classes, the V-Ray recipe, the worktree-collision rule) is unchanged and out of scope here.

---

## 5. For a successor: next moves

1. **Open the PR** `chore/ci-gate → develop`. The inaugural CI run will execute on the PR. It should be green (§3 reproduces it), but watch for **ubuntu-vs-Windows** surprises (path separators, line endings, locale) — none expected, all steps are pure-Python and SU-free.
2. **On merge**, CI becomes live for every future PR/push to develop|main, and the README badge resolves from "no status" to green. This officially closes the long-standing **no-CI** follow-up.
3. **Then, separately**, tackle the deferred lint: a `chore/ruff-cleanup` that runs `ruff check --fix` (132 auto-fixable), reviews the rest by hand, and finally adds a `lint` job (or a step in `tests`) so ruff joins the gate. Don't fold it into this PR — keep the gate's introduction reviewable.
4. **Optional docs refresh** (also logged in the 2026-06-24 handoff §10.5, still open): `README.md` still claims "this repo is … not a Model-Context-Protocol server" and an outdated test count — both false now (slice-1 MCP server exists; `tests/` holds ~67 files / 901 cases). Good companion to the CI badge edit.

### Still open (unchanged from 2026-06-24, not addressed here)
- Per-`session_id` worktree lock (DIFF-004 root fix).
- Reference-learning path + full studio cycle automation (WIP).
- `current_state.md` / `.ai_bridge/HANDOFF.md` narrative staleness.

---

*One line to remember: the repo finally has a self-validating belt again — one file, three jobs, zero SketchUp, proven green before it ever ran. Merge it, then clear the ruff backlog as its own chore.*
