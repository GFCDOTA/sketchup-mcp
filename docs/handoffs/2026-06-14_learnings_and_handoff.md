# sketchup-mcp — HANDOFF + LEARNINGS

> **For:** the next maintainer / successor session.
> **What this is:** the durable record of how a PDF floor plan becomes a faithful SketchUp `.skp`, why each hard decision was made, and how to pick the work up without re-learning it the painful way.
> **Read this first, then `.ai_bridge/HANDOFF.md` for the live thread (branch, last commit, frozen recipes, open items).**

---

## 1. What this project is, and the unique thing it does

The product goal is narrow and hard: **take a PDF architectural floor plan and produce a SketchUp `.skp` 3D model that is *faithful* to it** — walls in the right place and thickness, doors and windows as real openings (with the wall mass below the sill and above the lintel preserved), rooms floored to the wall inner faces, soft barriers (peitoris, glass guard-rails) rendered honestly, and — optionally — the rooms auto-furnished.

Almost nobody does the faithful-floor-plan part. The achievement is not "draw some walls in 3D"; it's getting a model that a human, holding the source PDF, accepts as *the same plan*. That fidelity bar is what drove every architectural decision in here.

**The honest bottleneck, stated up front:** there is **no automated PDF→geometry extractor**. The input to the pipeline is a human-authored `consensus.json`. Raster + Hough-line detection was tried and rejected because it *fabricates false geometry* — and a lying extractor is worse than an honest human step (ADR-0001 keeps PDF→consensus a human step on purpose). Generalizing to a brand-new plan today depends on that authorship, not on a magic extractor. Do not "fix" this by shipping an auto-extractor that hallucinates.

**The throughline of the whole repo:** an LLM is the *engine*, but the surrounding engineering — deterministic verification, honest stop conditions, provenance rules — is what separates "toy that hallucinates" from "thing that runs unattended without corrupting state."

---

## 2. The pipeline, end to end

```
PDF floor plan
   │  (HUMAN authorship — no auto-extractor; raster/Hough fabricates false geometry)
   ▼
consensus.json   ← THE SINGLE SOURCE OF TRUTH
   │  walls, openings, rooms, soft_barriers — all in PDF-point coords
   │
   ├─► [Python phase]  tools/build_plan_shell_skp.py   (all 2D computational geometry)
   │      • per-wall axis-aligned footprint rectangles
   │      • shapely.unary_union → corners auto-resolve into ONE polygon (no per-wall pillars)
   │      • buffer(+eps)/buffer(-eps) MITRE close-gap pass (bridge sub-tolerance endpoint gaps)
   │      • subtract door/passage/glazed-balcony openings as 2D full-height carve rects
   │      • canonicalise axis-aligned rings (strip collinear redundant verts + corner "teeth")
   │      • filter slivers; compute room floor slabs reaching wall inner faces
   │      └─► emits  _shell_polygon.json  (outer+holes per piece)  +  window_apertures[]
   │
   └─► [Ruby phase]  build_plan_shell_skp.rb   (autorun SketchUp plugin — final assembly)
          • extrude the shell once
          • cut floors with hole topology
          • render soft barriers PER SEGMENT (provenance decides IF, type decides HOW)
          • carve WINDOWS as 3D post-extrude apertures (sill..head band), keeping
            peitoril (below sill) + verga (above lintel) mass intact; panel fallback if no host face
          └─► emits  geometry_report.json  +  iso/top/floors-only PNGs  +  *.proj.json projection sidecar
   │
   ▼
content-hash cache (keyed on consensus SHA256 + producing tool identity)
   │
   ▼
GATE-GUARDED PROMOTION → artifacts/<plant>/   (only if rebuilt-not-cached AND gates green AND suite passes)
   │
   ▼
VERIFICATION: deterministic gates (exit 0/1/3) + Visual Oracle (advisory) + human VISUAL_REVIEW
   │
   ▼
(optional)  auto-furnish layer → per-room "brains" → parametric furniture → scene gates
```

**Two routing keys drive the whole builder** (this decoupling is load-bearing — see §3):

- **`kind_v5`** — the *semantic* key (WHAT it is → HOW to carve): `door / passage / glazed_balcony` → 2D full-height carve; `window` → 3D post-extrude aperture.
- **`geometry_origin`** — the *provenance* key (WHERE it came from → whether to act at all): `svg_arc / svg_segments / human_annotation` → carve; `wall_gap` → leave alone (the gap is already in the wall data).

---

## 3. How it cracked the hard problem (domain learnings)

These are the insights that made faithful output possible. Most cost a real PR or rework.

### 3.1 Consensus is the single source of truth, and "never invent geometry" is mechanically enforced
If a wall/room/opening/barrier isn't in `consensus.json`, it never appears in the output. This is **Hard Rule #1** and it is enforced in code, not just documented: a host `wall_id` must exist; soft barriers render only when sourced via `barrier_type` / `human_confirmation` / `pdf_text`; unsourced input is *skipped*, and a detector FAILs if unsourced data ever becomes physical geometry. Honesty is itself a quality bar — see room_fidelity WARN in §3.9.

### 3.2 Real extractor data has NO shared endpoints — merge by overlap, not by vertex identity
planta_74 has **0 shared endpoints across 40 wall endpoints** — every one is unique (endpoint-share ratio 1.000). Walls that "look connected" in the PDF are actually `SNAP_EPS_PTS` apart. You **cannot** form corners from shared vertices. The solution: merge by 2D footprint **OVERLAP** via `shapely.unary_union`, then bridge the residual micro-gaps with a `buffer(+0.1pt)/buffer(-0.1pt)` round-trip.

### 3.3 The close-gap buffer MUST use mitre joins, not round
Buffer with default (round) joins replaces every right angle with a 16-segment fan — a simple room would end with ~64 perimeter verts instead of 4. Use `join_style=2` (mitre) with a `mitre_limit` so corners stay exact while only sub-eps gaps get bridged.

### 3.4 Orthogonal artifacts that `shapely.simplify` will NOT remove — two custom canonicalisers
- **Collinear redundant verts (FP-025 stepped-notch):** `unary_union` of two adjacent axis-aligned rectangles leaves collinear verts on the outer boundary — a clean 4-wall shell carries 12 outer verts (4 corners × 3) instead of 4. `_canonicalise_axis_aligned_ring` drops a vertex when `prev→cur` and `cur→nxt` share a cardinal direction.
- **Half-thickness corner "teeth" / toquinhos (~2.7pt):** survive both union *and* simplify and are *not* collinear-redundant. `_remove_small_teeth` detects a symmetric rectangular protrusion (two perpendicular turns, equal side lengths, opposite directions, depth < 3pt) and collapses it **without introducing a diagonal** — it explicitly requires the two side edges be equal length so the reconnected base stays axis-aligned.

### 3.5 Junction-aware extension — don't shoot stubs into open space (LL-017)
Extending every wall endpoint by half-thickness to close corners is wrong at **free** endpoints — it fires a half-thickness stub into empty space. Fix: per-endpoint junction classification — only extend an endpoint if a **perpendicular** neighbour's raw footprint (buffered by 0.5pt) contains it. **Parallel overlap must be explicitly skipped**, because a human-painted partition offset by ~thickness from a structural wall overlaps in 2D but extending into it would still create a stub.

### 3.6 Windows are the crown jewel: peitoril + verga via 3D post-extrude carve (ADR-007 / FP-024)
Carving a window full-height in 2D and re-stacking sill+glass+lintel bands produces three structurally-separate volumes that read as **"a shaft with infill," not "a wall with a window."** The only faithful path:
1. extrude the wall as a **solid first**, then
2. add a coplanar aperture rectangle on the host face and `pushpull(-thickness)` so SketchUp merges with the opposite face into a **real through-hole**, leaving the peitoril (mass below sill) and verga (mass above lintel) intact as the perimeter remainder.

Windows were moved **off the 2D carve path entirely** — that was the "shaft with infill" fix.

Three further window subtleties, each a real bug:
- **Use the HOST wall's own thickness, not the global.** After collinear walls were merged (FP-031 #28), each merged wall's thickness became the **mean** of its segments (e.g. 5.52pt vs global 5.40pt). `pushpull(-global_thickness)` then stops *short* of the far face → a blind dark pocket ("só o recorte, sem vidro", the BANHO 2 bug). Carve with the host wall's own thickness so the cut reaches and merges with the far face.
- **Carve on the RIGHT wall.** `find_wall_face_for_aperture` originally grabbed the first face merely spanning the aperture's x/y range — often a parallel facade — and carved the hole on the wrong wall (FP-031). Fix: the candidate face must sit at the host wall's **perpendicular position within tolerance**; if none matches, return `nil` so the caller falls back to a panel rather than inventing a hole in an unrelated wall.
- **Windows are not one component.** Narrow windows (width ≤ 1.20m) are physically *basculante* (awning) windows high on bathroom/service walls — high sill (1.50m, from **NBR norm, not the PDF**), wall below stays solid. Rendering branches on width into full sliding frame vs basculante sash, and the 3D carve height differs by type. And don't stretch one component to fit everything ("esticar fica uma merda") — use a parametric frame with **constant-profile** members (5cm frame width that never scales) where only the glass pane resizes.

### 3.7 Doors: orientation-dependent hinge mapping (the "floating doors" bug)
The door-leaf hinge pivot had a coordinate-mapping bug: for vertical walls it set **both** x and y to `hinge_along`, pivoting around an off-axis diagonal point and translating the leaf metres away. Correct mapping is orientation-dependent:
- horizontal wall: `hinge = (hinge_along, cross_base)`
- vertical wall: `hinge = (cross_base, hinge_along)`

### 3.8 Soft barriers: per-segment sweep + trust_human
- A naïve polyline-bbox for a peitoril running along one room edge produces a giant slab covering the whole room (the 2026-05-20 bug). Sweep a **thin slab per polyline SEGMENT**, perpendicular to its direction.
- **FP-006:** the vector extractor catches the building *outline* as a soft_barrier; midpoint-in-wall-footprint segments must be dropped. But a genuine human-confirmed peitoril *touches* the wall at its endpoints, so the 3-point sample false-positives on it. Fix: a **trust_human** exception — `geometry_origin=human_annotation` barriers are never dropped by overlap (restored sb005 after the wall-merge regen had knocked it out).

### 3.9 Room floors: free-space cell, tuck under wall, close with barriers
- Room polygons from consensus are **recessed** from wall faces → visible gray gap. Don't trust the polygon. Fill the **free-space cell** (envelope minus wall mass), bounded exactly by wall inner faces, then tuck the slab `0.4*thickness` **under** the wall (swept 0.3–0.6; ≤0.45 is the max tuck where two adjacent slabs `0.4+0.4=0.8<1.0` never overlap).
- Floors **leaked past the facade** where a balcony has a glass rail instead of a wall (the free-space cell ran to the outer edge of the transparent rail). Close the envelope with the **soft_barriers** (buffered polylines) AND subtract the barrier mass, so the slab stops at the rail's inner face.

### 3.10 SketchUp `add_face` "Duplicate points in array" — dedup at the right noise floors
Two distinct classes, two fixes — plus a final dedup:
- shapely union of float-noisy thicknesses (e.g. 5.399517 vs neighbour) emits two points <1e-3 pdf-pt apart at a corner → `_drop_coincident` at a 1e-3 tol noise floor (~3.5µm — removes only union noise; real verts are orders larger).
- real room polygons with literal repeated/closing vertices (one A.S./TERRACO room had 196 entries with duplicates) → `dedupe_consecutive_pts`.
- **`drop_collinear` can itself leave a zero-length edge** (two coincident adjacent verts) → a **FINAL** `dedupe_consecutive_pts` after collinear-drop is mandatory, or the whole room floor *silently disappears* (the terraço/r001 vanish bug).

### 3.11 Scale comes from a physical anchor, never default DPI (LL-006 / LL-021)
A PDF carries no universal scale. Guessing `0.0254/72` produced out-of-proportion output. Derive `PT_TO_M` from a real known dimension (`wall_thickness_pts / 0.19` for a ~19cm structural wall); if no anchor is declared, **BLOCK** rather than guess. This is "never fabricate" applied to a numeric constant. (See §6 for the multi-source-of-truth scale incident.)

---

## 4. Verification philosophy: "green tests are NOT visual proof"

This is the keystone, repeated everywhere: **a passing pytest and a true `gates_self_check` are NOT proof of fidelity.** They are orthogonal axes.

### 4.1 The explicit 3-layer eval model (`.claude/evals/eval_strategy.md`)
Each layer states its own blind spot:
- **Layer 1 — pytest contract suite:** proves the *builder code didn't regress*. Does NOT prove the model is faithful. (Pure-Python, SketchUp-independent, skips cleanly when SU absent.)
- **Layer 2 — `gates_self_check`:** 4 machine-readable booleans on SKP structural integrity in `geometry_report.json`: `plan_shell_group_exists`, `wall_shell_is_single_group`, `floors_separated_from_walls`, `default_material_faces_zero`. Proves *structure*, not placement ("não mede se a wall está no lugar certo").
- **Layer 3 — human rubric (`fidelity_rubric.md`):** appearance-vs-source judgment, **reserved for a human eye**.

Named anti-patterns: *eval cosmético, eval inflado, eval circular, skip-Camada-3.* The painful proof (LL-021 / LL-012, post-PR #194, 2026-05-27): `gates_self_check` was all-true while a human suspected an openings regression; only a fresh build + opening-count comparison could dismiss it. → **Constitution #8 "No SKP, no progress."**

### 4.2 The deterministic gate suite — one verdict, three exit codes
`tools/run_deterministic_gates.py` aggregates many small gates into ONE runnable suite emitting ONE verdict:
- **PASS = exit 0**
- **FAIL = exit 1** (ran and found a real discrepancy → "the geometry is wrong")
- **INCOMPLETE = exit 3** (couldn't run, missing input → "regenerate the sidecar"). Deliberately **3**, because argparse already uses 2 for usage errors.

CI and pre-commit gate on the **exit code, not stdout** — because a "loud print" still exits 0, and that is exactly how an unverified artifact ships as "green" (LL-035, below). **A gate that doesn't run is not a green gate.**

Gates included (consensus-only detectors run in milliseconds, no network/PIL/SU):
- `opening_host_audit`, `wall_overlap_audit` (duplicate/overlapping walls) — **run BEFORE trusting any render**.
- `overlay_diff` — projects consensus walls onto the render; prefers an **exact** pdf-pt→pixel Affine from the builder's `.proj.json` sidecar (`calibration='sidecar_exact'`, zero error), falls back to coloured-floor-bbox only for pre-sidecar renders. **Skips wall segments with `in_frame < 0.5`** ("cannot be judged, NOT reported as missing").
- `render_bbox_audit` (FAIL if content bbox comes within edge_min px of any frame edge — the clipped-render guard), `soft_barrier_source_audit`, `railing_exact_match_gate`, `parapet_not_railing_fallback_gate`, `position_fidelity_gate` (derives pt→m from observed door/window widths, robust to whatever `PT_TO_M` the build used), `wall_segment_coverage` (tolerates openings by sampling along the segment).
- `wall_exact_match_gate` — compares the **current consensus against a known-good BASELINE**, never against itself ("se o EXPECTED não tiver o teco, o gate herda a cegueira" — self-comparison is structurally blind to omissions).

### 4.3 The Visual Oracle — the ONE subjective gate, explicitly distrusted
`tools/run_skp_visual_review.py` consults a vision model over top/iso/side-by-side renders. Its verdict is the single subjective signal and is **never allowed to override** deterministic findings or known warnings:
```
final_verdict = worst(oracle_verdict, deterministic_verdict, carried_known_warnings_verdict)
```
An oracle PASS cannot beat a deterministic FAIL or a documented architectural WARN. Per-axis oracle PASS is **downgraded to WARN** where a fixture carries `known_warnings`, and the disagreement is routed to an auto-consult gate rather than silently picking a side.

### 4.4 negative_dogfood — proving the oracle actually discriminates
`tools/negative_dogfood.py` injects a deterministic **"erased wall"** corruption into the real planta_74 render and checks the oracle rates it worse. It proved the vision model gives **confident false PASSES**: with an exterior wall erased it returned `PASS, findings=[], confidence=high`, literally saying *"all walls appear correctly aligned and continuous."* A human sees the gap instantly.

Two methodology lessons baked in:
- A naïve single-image probe **saturated** the oracle at FAIL even on the **clean** baseline (over-pessimistic, hallucinated findings about an iso image never sent). A negative test is meaningless if the clean baseline doesn't PASS first. Fix: **production-input parity** — feed the exact pipeline inputs (top+iso+side_by_side+geometry context), corrupt only the top, add a finding-level secondary metric.
- If the clean baseline saturates, the result is `INCONCLUSIVE_CLEAN_SATURATED`, **never a pass.** "No verdict is ever fabricated."

### 4.5 visual_regression_gate — forcing a human to actually look
`tools/visual_regression_gate.py` builds a mandatory **PDF | BEFORE | AFTER** montage and writes a verdict scaffold with a hard-FAIL checklist and the literal instruction *"fill by LOOKING — not pytest/counts/exit-0."* It forces an IMPROVED/SAME/WORSE verdict from a human.

### 4.6 The gate-strictness philosophy
- **Pixel-perfect rendering is the WRONG hard gate** (GPU/driver/font/SU-version flakiness across CI vs local). Renders are **evidence for human review, not bit-exact diffs.**
- **Hard-block only categorical absurdities:** missing `.skp`/renders, `window_apertures_3d != count(kind=window)`, confirmed `floating_door` / `orphan_glass_panel`, any `gates_self_check` false.
- **Provenance-without-proof = WARN** (advisory), not FAIL.
- **`render_bbox_audit` segments non-background content and FAILs if its bbox comes within `edge_min` px of any frame edge** — born from the stale clipped-render incident; it would have caught the half-framed plant.
- **Pin known imperfections** in `known_warnings.json` so an oracle PASS can never silently erase a documented WARN and "green" never overstates fidelity.
- **Build geometry in isolated sub-groups** so boolean/pushpull can't re-find and extrude a face from an earlier piece (operation context isolation).
- **READ-FROM-MODEL, never hardcode (LL-014):** after a solid is built, query its *actual* face coordinates from the model before adding a coplanar cut — survives float drift between spec and built geometry.
- **Deterministic camera:** fit the camera to the **image aspect ratio** (not the window via `zoom_extents`, which clips the model in a fixed-aspect PNG), and write the exact projection sidecar so the pixel-overlay gate needs zero calibration.
- **Turn every postmortem finding into a permanent regression gate** (`render_bbox_audit` and `soft_barrier_source_audit` were each born from one specific review finding).

---

## 5. The agentic operating system (`.claude/`, the decision oracle, `.ai_bridge/`)

This is not product code — it's the agent's **operating system**, the steering layer that turns a generic coding agent into a disciplined operator for one hard goal.

### 5.1 `.claude/` — constitution, tiered memory, skills, evals
- **Thin bootloader:** root `CLAUDE.md` is short by design and `@import`s a **fixed ordered chain** every session: `constitution → memory/ → specs/ → evals/ → plans/`. Skills are auto-discovered (description always visible, body loads only on trigger phrase/path); many specs are on-demand. (`active_work.md` even ships a grep one-liner that checks every `@import`ed path resolves.)
- **Constitution (8 points), one precedence rule:** *"if this file conflicts with any other `.md`, this one wins; the other must change."* Changing it requires an explicit PR + justification, so it can't be edited away mid-session. Everything else is regulation derived from it. **#8 = "No SKP, no progress."**
- **Tiered memory by decay rate:** `project_context.md` (stable) · `current_state.md` (fast-decaying daily snapshot whose header orders re-verification via git/gh BEFORE any remote decision) · `lessons_learned.md` (permanent numbered LL-001..LL-037, each = a real cost) · `deprecated_context.md` (kept for traceability, labeled "do not follow") · the **GREEN/YELLOW/RED** autonomy framework.
- **GREEN/YELLOW/RED** with **7 concrete RED stop-criteria** (not vague "use judgment"): exposed creds · irreversible destructive op · declared goal change · unresolvable merge conflict · a red required check · a missing mandatory artifact · an operational limit.
- **"A valid stop":** completing a declared slice **is** a valid stop. Auto-continue only if the next item maps to one of 5 product-ROI categories. A verbal "don't stop" still passes the ROI filter (closing PR backlog counts; inventing a governance doc does not). This directly kills the agent's tendency to invent endless cleanup/audit cycles (LL-009: 3 hygiene passes all converging on "preserve" = bikeshed, PRs #73/#108).
- **Spec-Driven Development:** a contract-touching change needs a short spec (problem/proposal/test cases/acceptance/out-of-scope) BEFORE code; **a spec without a failing-then-passing test is an ADR on a shelf.** Named anti-patterns: fake harness, spec-without-harness, harness-without-real-application ("pretty demo"). Prove on a micro-fixture first, but **every experiment ends in an explicit verdict** (applied/rejected/blocked); tiered truth model (PDF vector > human annotation > agent inference > experimental hypothesis), tier-D never ships straight to production.
- **~15 skills**, each with a clear trigger, an explicit "when NOT to use," named anti-patterns, and related-skill links (no orphans). Hostile operational gotchas captured verbatim (e.g. gh-autopilot records the org's 366-day token limit and the exact Contents-RW-vs-Pull-requests-RW permission split; "validate auth with a REAL operation, not `gh auth login`").

### 5.2 The decision oracle / cockpit on `127.0.0.1:8765`
A local HTTP "decision oracle" lets autonomous sessions resolve real engineering forks **without bouncing to a human in chat** — the human is not a copy/paste relay.
- **Gate:** `tools/claude_bridge/server.py` exposes `POST /ask {prompt[,mode][,tier]} → {response}` and `GET /health`, answered by **`claude -p` headless (Opus 4.8, effort xhigh)**, authenticated by an OAuth subscription token (no API key, zero per-call cost). Drop-in for an earlier ChatGPT bridge that spoke the same contract — the engine is swappable at one function (`ask_claude`).
- **Asker:** `tools/ask_gpt_gate.py` packages context + one of 9 canonical triggers, probes the bridge, writes a question file, calls `/ask`, parses the structured verdict, writes a response file.
- **§6 helpers:** `gate_verdict.py` (parse Verdict/Confidence/Assumptions/Risks/Next-action), `gate_filefetch.py` (read-only allowlisted file fetch on MORE-INFO + Need-files), `consult_tier.py` (route purpose → fast Sonnet vs deep Opus).
- **Cockpit:** the same server self-serves `GET /` dashboard + `/sessions /events /heartbeat /status`, polling every 5s — **no external stack.** "If the page won't load, the service is down."
- **Policy "mode B" (delegated autonomy):** the oracle DECIDES everything except **VISUAL_REVIEW** — the **single human gate**, fired only when the plant's appearance changes and only a human eye can validate it vs the PDF. Verdict enum: `GO / NO-GO / MORE-INFO / VISUAL_REVIEW`. Offline → `SKIPPED_OFFLINE` (or `BLOCKED_BRIDGE_OFFLINE` under `--require-consult`), never a fabricated verdict.

Oracle hard-won rules:
- **Run the engine in a tempdir OUTSIDE the repo (LL-035).** `claude -p` from inside the repo loads the project `CLAUDE.md` and triggers the SessionStart hook — which boots the bridge — so **the oracle invokes itself infinitely.** Running with `cwd=tempfile.gettempdir()` breaks the recursion and dodges the per-project permission prompt. *The decision engine must not execute inside the environment whose lifecycle it controls.*
- **Claude consulting Claude is NOT independent.** Same model family shares blind spots and exhibits agreement bias. The original §6.1 "multi-oracle routing" was **deleted as fake independence**. Real ground truth is the **deterministic checks** (`overlay_diff`, `opening_host_audit`, pytest). What survived is cheaper: a **redteam mode** (`REDTEAM_PREFIX`) that forces the oracle to steelman the case AGAINST the option the asker already prefers, on the heaviest decisions.
- **Verdict + Confidence + Assumptions give it teeth (§6.4).** The oracle is blind to the repo (sees only the prompt), so any factual claim about something it can't see goes in `assumptions` (low/medium confidence), never stated as fact — the asker then knows exactly what to re-verify deterministically. Pure functions (`parse_verdict`, `resolve_tier`, `choose_gate_tier`, `_classify_gate_state`) keep this testable without I/O.
- **Tier by stakes:** fast tier for routine/triage/exploration; deep tier for judge-grade calls (merge, artifact approval, architectural, gate-conflict). Unknown purpose → **default deep** (fail-safe). The final-visual-verdict is **hard-pinned to deep** (`PINNED_DEEP_PURPOSES`) so it can never be cheapened.
- **Honest health states.** "UP/DOWN" is dishonest. The cockpit derives `ONLINE_ACTIVE / ONLINE_IDLE / BLOCKED / STALE_SOURCE / UNKNOWN` for the gate, and `STALLED / PARALYZED / OK` for sessions, using a **monotonic `cycle` token** as the progress signal that distinguishes "progressing" from "merely breathing."
- **Append-only audit core** (`audit.jsonl`): exact prompt + exact response + verdict + latency for every decision, enabling `audit_replay` to detect judgment drift. Best-effort writes; **secrets never enter the log** (token stays in env).
- **Default-deny file fetch:** paths must resolve inside the repo (blocks `../`), have an allowed text suffix, never match a secret name (`.oauth_token/.env/*.key/*.pem/*secret*`), with a byte cap. Read-only.
- **`DEFERRED` is not a mute button** (gate decision 2026-06-03, `_validly_deferred`): a DEFERRED must carry `why_not_fixed_yet` + `next_hypothesis` + `acceptance_criteria` AND an un-expired `review_by` date, else it auto-reopens as OPEN and counts as blocked (RED if HIGH).
- **A module is not done until an integration test proves the real caller uses it (LL-034).** The §6 framework once merged GREEN with passing unit tests while `ask_gpt_gate` never imported `parse_verdict`/redteam — dead code, caught by skeptical review + grep. *Green-unit ≠ live.* Required tests: `test_run_gate_online_parses_verdict`, `test_run_gate_sends_redteam`.

### 5.3 `.ai_bridge/` — cross-agent handoff + fidelity cycles
A **file-based** coordination layer for multiple agents (Claude sessions, a GPT-5 "judge," a peer-Claude, the human Felipe) without a shared live channel:
- **`HANDOFF.md`** — the durable "fio da meada" (thread between sessions): branch, last commit, status, frozen recipes, sentinels, queue. **Read first, written last.** A cold session resumes without the prior conversation's memory.
- **`questions/*` + `responses/*`** — timestamped async Q&A over the `:8765` gate.
- **`fidelity/verdicts/*.md`** (human-readable: judge quote, worst-cell, TOP3 fixes, OVERFIT_CHECK, exact before/after SHAs compared) + **`fidelity/ledger.jsonl`** (append-only machine log). Pinning the compared SHAs makes every verdict reproducible.
- **`noc/queue.jsonl`** → a NOC dispatcher (an actuator that *acts*): single-actuator lock with TTL, isolated worktree off the mainline, **never main / never auto-merge**, deterministic verify before keeping any change, appearance-changing work auto-enqueued to human VISUAL_REVIEW. Modes `--once / --dry-run / --loop` + append-only action ledger.

**The autonomous fidelity loop (`/loop`):** each wakeup = one cycle → run deterministic detectors → auto-fix what they catch → commit per slice → heartbeat to `:8765` with a monotonic cycle counter → log one status line (`PROGREDINDO / PATINANDO / BLOCKED`) → **stop only on RED / patinagem / NEEDS-HUMAN / exhausted backlog.** "Patinagem" (spinning) = 2 cycles with no new progress (same FAIL / nothing committed / repeating the same attempt) → STOP and report. *Stopping when the work is done is correct; continuing without ROI is wasted money.*

**Fidelity cycles** (the `FAIL → rule → fixture → gate → judge` loop): an external visual judge (GPT-5 via ChatGPT web) issues `WARN → IMPROVED → PASS` across numbered cycles. Every judge complaint must climb into a spec/constraint/generator/gate as a **general rule** — never a one-off local patch. **Generalization is the proof of a real fix** (the worst cell gets re-derived by the new rule with zero manual tweaks). Once PASS, **FREEZE**: any further change is a new formal cycle.

Hard-won `.ai_bridge` gotchas:
- **Image handoff to the web judge failed by every obvious route** — synthetic Ctrl+V doesn't carry the OS clipboard; CSP blocks fetch to localhost AND to raw.githubusercontent from inside the page; file_upload/upload_image refused; relaying base64 through an LLM corrupts it. **The one thing that worked: commit+push the PNG and give the judge the `raw.githubusercontent` URL** — GPT-5 (thinking) opens it via browsing and judges for real (cites GitHub as source). Requires a **public repo** and the image on a pushed branch. This is now the standard verdict-evidence workflow.
- **The "dead window" that blocked 3 V-Ray light cycles was `alpha=0` on the background**, not a lighting problem — the sky RGB was always there; the browser rendered transparent-as-white. One-line `_flatten_alpha` (RGBA→RGB) fixed it. **Lesson: when iteration stalls and no recipe helps, suspect the observation/measurement path (how the artifact is being VIEWED), not the thing being tuned.** The recipe was then frozen verbatim in HANDOFF.
- **A relative `scene_dir` is silent data loss with SketchUp:** SU resolves `model.save`/`write_image` against ITS OWN cwd, so the log says "saved" but the `.skp`/PNG never appear (a 0-byte `.skb` is the only symptom). `Path(scene_dir).resolve()` — **always pass absolute paths to an out-of-process tool.**
- **Removing a worktree silently breaks external launchers that hardcode its path.** Deleting `wt-dash` broke `SUBIR-COCKPIT.cmd`, `gate-watchdog.ps1`, `gate-watchdog-loop.ps1`, and the failure surfaced as a **misleading** "check your .oauth_token" error (the token was fine). **Rule: grep for references to a worktree path before removing it.**

---

## 6. Hard-won lessons (the transferable core)

The numbered lessons each cost a real PR/incident. The ones a successor must internalize:

| ID | The lesson |
|---|---|
| **LL-001** | **Rebuild-from-scratch corrupts the model; edit in-place.** V1 `entities.clear!` + rebuild made SketchUp close in seconds; V2 in-place edit (push_pull/add_face on the working `.skp`) opened correctly. Deprecated the whole `consume_consensus.rb` style. |
| **LL-006 / LL-021** | **Scale from a physical anchor, never default DPI.** Derive `PT_TO_M` from `wall_thickness / 0.19`; BLOCK if no anchor. (See also the scale-centralization handoff below.) |
| **LL-004** | **Honest WARN beats a forged PASS.** When the PDF has no wall between two open-plan rooms, `polygonize` closes 1 cell not 2 → `room_fidelity = WARN`, not FAIL. Inventing a wall to hit the room count would violate "never invent." Honesty is the quality bar. |
| **LL-031** | **A render gives confident FALSE PASS.** Detectors found 9/12 openings on the wrong host wall + 1 duplicate wall, yet the render "passed" (doors/panels don't use the host; the duplicate dissolved in the shell union). **Run deterministic detectors BEFORE trusting any render.** |
| **LL-032** | **Root-cause beats symptom-tweaking.** The wrong-host mess wasn't a hosting bug — it was **collinear fragmentation** (each architectural wall split into many short collinear segments with gaps at openings, so openings landed in gaps with no host). A collinear-merge + re-host collapsed planta_74 **35→19 walls**, fixed `opening_host` (0/12 FAIL), AND flipped 4 windows from panel-fallback to real carved apertures. One structural fix cascaded through the whole pipeline. (Data fix mutates a fixture → Hard Rule #3 → gated NEEDS-HUMAN, never auto-applied.) |
| **LL-033** | **Promoting a fixture is SUPPOSED to break tests that pinned the old (buggy) state — that's expected, not regression.** 6 tests pinned junction=27/free=43, n_walls≥30; re-pinned to junction=21/free=17, n_walls≥15 **only after verifying the invariant `junction+free == 2*walls`** and zero stub violations. Keep detector capture-behavior in **synthetic** fixtures so re-pinning the real-fixture test doesn't lose coverage. |
| **LL-034** | Three siblings: **(a)** "develop has feature X" / "the reviewer said X" is **hearsay until proven** — verify with `git merge-base --is-ancestor` + a detector, never with speech. **(b)** **Code ≠ running process** — a bridge change isn't live until you RESTART (`start.ps1`) + validate `/health`; a `mode:redteam` request was silently ignored because `:8765` still ran old code. **(c)** A gate module is **dead until an integration test proves the caller uses it.** |
| **LL-035** | **A gate that silently skips ships unverified work as "green."** The wall-presence gate only runs if a `<render>.proj.json` sidecar sits beside the render, but promotion never copied it → the canonical model sailed "PASS" with that gate **never executing**. Two fixes: **(1)** the sidecar is part of the deliverable (added to the promotion map); **(2)** enforce by **EXIT CODE** — `--render` given + sidecar missing ⇒ INCOMPLETE / exit 3 (a "loud print" still exits 0 and CI gates on the code). **"No silent caps."** |
| **LL-036** | **External review judges WHAT YOU SEND.** An external AI flagged 3 "critical" items; 2 were **STALE** — it had reviewed an old, misleadingly-named snapshot (`visual_loop_current`, with a clipped render) instead of the fixed canonical path. The lying "current" dir was deleted; each finding became a deterministic regression gate (`render_bbox_audit`, `soft_barrier_source_audit`). **Aim review at `artifacts/<plant>/`; verify every finding against the CURRENT canonical.** |
| **LL-037** | **A global on/off flag is a seesaw, not a fix.** One `SOFT_BARRIERS_MODE` flag rendered all 9 barriers identically → sessions oscillated "everything is a railing" ↔ "nothing is." Fix: **per-segment, provenance-driven** — provenance decides IF it renders, type decides HOW, **nothing global**. 8 unsourced barriers skipped; only the 1 documented barrier rendered. Backed by `railing_exact_match_gate` + `parapet_not_railing_fallback_gate`. |
| **LL-009** | **"Done is not stop" as an absolute is a failure mode.** 3 consecutive hygiene passes all converged on "preserve" = bikeshed (PRs #73/#108). A natural slice-complete IS a valid stop; auto-continue only behind 5 explicit product-ROI categories. Cleanup needs a real trigger (broken gate / duplicate ref / stray artifact / root script outside allowlist); archive-before-delete to a dated path; **never delete ground truth, canonical artifacts, baselines, or contract tests** even if they look unreferenced. |
| **Scale handoff** | **Multiple sources of truth for one constant silently corrupt the whole system.** `PT_TO_M` lived in one file, `PT_TO_IN` was copy-pasted across 6 files, `M()` had 2 copies — producing "shell at 0.0259 / furniture at 0.0352 / gate in yet another scale," which "burned entire sessions." Fix: single source `core/scale.py` (env-driven), re-exported for back-compat, plus a **repo-health gate that bans any module-level redefinition or the literal `0.19/5.4` outside that one file**, forcing every future branch to migrate at merge. Verified byte-identical (500 tests pass), 3× adversarially confirmed across independent angles. |
| **No-CI** | **Disciplined local runs are not a gate.** With no CI, two real breakages hid for months: a clean install couldn't even *collect* pytest because matplotlib/numpy weren't declared in pyproject (#225), and 4 consult tests were coupled to import-time-resolved paths (#226). Surfaced only on a clean venv. **Add at least a minimal GitHub Actions pytest workflow** (open backlog item). |
| **DIFF-004** | **Multi-agent worktree collisions are real.** During the cockpit build, sessions sharing one worktree moved the branch out from under each other ~5 times (near data-loss). Mitigated by isolated worktrees + rebase-before-push + a liveness orchestrator that surfaces PARALYZED/STALLED; root fix (per-`session_id` worktree lock) honestly logged as an **open follow-up, not faked as solved.** Run `git worktree list` before any branch/worktree op; run `fetch` → `rev-parse` **sequentially** (parallel rev-parse can read a stale ref). |

**ADR-0001** records the operating architecture: oracle at `:8765` backed by headless `claude -p`, the liveness orchestrator, deterministic ground-truth gates, and the human VISUAL_REVIEW gate. Its named non-obvious calls: keep PDF→consensus a **human** step (no lying extractor); run the oracle in a **tempdir outside the repo** (D1, anti-recursion); **don't build infra-for-infra** (D4 rejected a full Java/Spring stack for a localhost status page — the gate serves its own self-contained page; "if the page doesn't open, the gate is down").

---

## 7. The auto-furnish layer (interiors) — secondary, but real

A deterministic, geometry-driven engine that auto-furnishes room-by-room **with no 3D-asset download and no LLM at placement time**:
- `tools/room_type.py` classifies each room from its consensus **name** via auditable regex (SUITE→BEDROOM, SALA→LIVING; **UNKNOWN is never furnished** — Hard Rule #1), stamping `room_type_source='name_regex'`.
- `tools/furnish_apartment.py` dispatches each room to a per-type **brain** (BEDROOM `bedroom_designer`, LIVING `living_room`, KITCHEN, BATHROOM). Each brain builds a shapely spatial_model, generates candidate bounding-box placements against walls, scores with **HARD gates (binary, reject) + SOFT score (continuous, rank)**, and returns the best candidate + a full `ScoreBreakdown` (why it won, why others were rejected).
- The living-room brain (`interior/planners/living_room_planner.py`) is a **constraint SOLVER**: picks the TV wall via a `WallAffordanceMap` (TV only on a clean wall — **a door/window/passage/balcony DISQUALIFIES a wall**, a hard precondition not a soft penalty), then the sofa wall that opposes the TV normal, is out of circulation, and at ~1.8–5.0m viewing distance (`_sofa_perp` floats the sofa in deep rooms, anchors it in shallow ones).

Transferable furnish lessons: the vision oracle OK'd a **0.39m miniature sofa** → deterministic dimension/scale gate is the authority, human is the sole visual judge. **Placement and object-quality fail independently** (a parametric sofa can PASS as an object yet FAIL floating dead-center). Encode professional/ergonomic knowledge as **relational constraints (ratios)**, not absolute sizes ("only width scales with seats — never inflate depth/height"). Cross-class constraints are real (a 0.55m nightstand FAILS next to a low japandi platform bed — its top must be **derived** from the bed surface). Test against **synthetic parametric fixtures** (`fixtures/synthetic_rooms`: small/medium/large bedroom, long-narrow living) to surface the "narrow corridor" and "shallow room" generalization bugs the one real plan hid.

---

## 8. For a successor: how to pick it up

### 8.1 The hard rules (memorize these — they are constitutional)
1. **Never invent geometry.** Nothing enters the output that isn't in `consensus.json` with provenance. Unsourced → skipped, and a detector FAILs if it ever renders.
2. **No SKP, no progress (Constitution #8).** Every fidelity-affecting PR must emit a fresh `.skp` + renders + `regression_summary` with concrete per-axis evidence into a human-facing folder. "PASS — ok" = WARN; checklist theater is banned.
3. **A fixture-mutating fix is NEEDS-HUMAN.** Re-extracting / regenerating `consensus.json` mutates a fixture and is never auto-applied.
4. **Green tests are NOT visual proof.** Deterministic gates + structural booleans prove code/structure; only a human eye vs the PDF proves fidelity.
5. **VISUAL_REVIEW is the ONE human gate.** The agent decides everything else autonomously via the oracle; appearance judgments (IMPROVED/SAME/WORSE) are permanently human.
6. **Scale comes from a declared physical anchor or you BLOCK.** Single source `core/scale.py`; never redefine the literal `0.19/5.4`.
7. **A gate that didn't run is not green.** INCOMPLETE/exit 3 ≠ FAIL/exit 1 ≠ PASS/exit 0. Enforce by exit code, never by stdout.

### 8.2 Where things live
- **Builder (Python 2D):** `tools/build_plan_shell_skp.py` → emits `_shell_polygon.json` + `window_apertures`.
- **Builder (Ruby/SketchUp):** `build_plan_shell_skp.rb` (autorun plugin) → emits `geometry_report.json` + PNGs + `*.proj.json` sidecar.
- **Mirrored constants across the language boundary:** `CARVING_ORIGINS` exists in both `.py` and `.rb` with an explicit "kept in sync manually" comment pointing at its counterpart, plus matching `_floor_snap_coords/snap_coords`. When you can't share code, **name the mirror and make divergence loud.**
- **Deterministic gates:** `tools/run_deterministic_gates.py` (aggregator) + `overlay_diff`, `opening_host_audit`, `wall_overlap_audit`, `render_bbox_audit`, `soft_barrier_source_audit`, `railing_exact_match_gate`, `parapet_not_railing_fallback_gate`, `position_fidelity_gate`, `wall_exact_match_gate`, `wall_segment_coverage`.
- **Visual Oracle:** `tools/run_skp_visual_review.py`. **Discrimination proof:** `tools/negative_dogfood.py`. **Human-forcing montage:** `tools/visual_regression_gate.py`.
- **Decision oracle:** `tools/claude_bridge/server.py` (+ cockpit `GET /`); asker `tools/ask_gpt_gate.py`; helpers `gate_verdict.py` / `gate_filefetch.py` / `consult_tier.py`; audit `audit.jsonl`.
- **Cross-agent state:** `.ai_bridge/HANDOFF.md`, `questions/`, `responses/`, `fidelity/verdicts/`, `fidelity/ledger.jsonl`, `noc/queue.jsonl`.
- **Agent OS:** `.claude/` — `constitution.md`, `memory/` (`project_context.md`, `current_state.md`, `lessons_learned.md`, `deprecated_context.md`), `specs/`, `evals/eval_strategy.md`, `fidelity_rubric.md`, `skp_proof_of_progress_gate.md`, `known_warnings.json`, ~15 skills.
- **Interiors:** `tools/room_type.py`, `tools/furnish_apartment.py`, `interior/planners/`, `interior/composer/`, `interior/validators/`, `interior/class_specs/`, `references/design_rules`, `fixtures/synthetic_rooms`.
- **Canonical deliverable:** `artifacts/<plant>/` (e.g. planta_74). **Always point review here, never at a timestamped snapshot.**

### 8.3 First moves on a cold start
1. **Read `.ai_bridge/HANDOFF.md`** — branch, last commit, frozen recipes, queue. Then `.claude/memory/current_state.md` (and obey its re-verify-via-git/gh header before any remote action).
2. **Verify environment, don't assume:** run pytest in a **clean venv** (the no-CI lesson — undeclared deps / import-path coupling hide otherwise). Confirm any "branch has X" claim with `git merge-base --is-ancestor`, not recollection.
3. **Bring the oracle up:** `start.ps1`, then validate `GET /health` (it self-documents `ask_field`, `verdict_enum`, modes, tiers, endpoints — don't reverse-engineer the contract). Remember **code ≠ process**: restart after any bridge change.
4. **Run the deterministic gates BEFORE trusting any render:** `python tools/run_deterministic_gates.py --render <png>` and **gate on the exit code** (0 PASS / 1 FAIL / 3 INCOMPLETE). If you get exit 3, regenerate the `.proj.json` sidecar — that's "couldn't run," not "geometry wrong."
5. **For a fidelity-affecting change:** write the spec → failing-then-passing test → build → produce the `.skp` + renders + `visual_regression_gate` montage → run the gate suite → the Visual Oracle (advisory, `worst()`-aggregated) → escalate to the **human VISUAL_REVIEW** if appearance changed. Prove on a synthetic micro-fixture first; end every experiment with an explicit applied/rejected/blocked verdict.
6. **When you fix a postmortem finding, turn it into a permanent deterministic gate** so the bug class can't silently return.

### 8.4 Honest maturity caps (don't overstate)
- Deterministic-only confidence: **~70%.**
- Bridge + heuristics: **80–90%.**
- **Never claim 100%.** "Faithful" is honestly INCOMPLETE-able in places (e.g. open-plan rooms with no dividing wall → permanent WARN with written justification). Honest > complete. A passing test is explicitly **not** visual proof.

### 8.5 Known open follow-ups (logged, not faked as solved)
- Per-`session_id` worktree lock for multi-agent runs (DIFF-004 root fix).
- Minimal GitHub Actions pytest workflow (the no-CI lesson; #225/#226 in flight).

---

*If you remember one thing: the LLM is the engine, but the deterministic verification, the provenance rules, and the honest stop conditions are what keep this from being a toy that hallucinates. Run the detectors before you trust the picture, and let only a human eye certify that the picture matches the PDF.*
