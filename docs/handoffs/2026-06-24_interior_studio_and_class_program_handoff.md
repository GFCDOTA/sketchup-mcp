# sketchup-mcp — HANDOFF (2026-06-24): the interior studio + the furniture-class program

> **For:** the next maintainer / successor session.
> **What this is:** an **incremental** handoff covering the ~2 weeks and ~280 commits since
> [`2026-06-14_learnings_and_handoff.md`](2026-06-14_learnings_and_handoff.md). It records the **mission pivot** — from "produce a faithful empty `.skp` shell" to "shell **+** a procedurally-learned, judge-validated furniture program **+** a photoreal interior render," driven by a small **multi-agent design studio**.
> **Read order:** the **2026-06-14 doc first** — the PDF→`.skp` pipeline, the "green tests ≠ visual proof" verification philosophy, the deterministic gate suite, the decision oracle (`:8765`), and the agentic OS (`.claude/`) are all **still in force and unchanged**. This doc only adds the new layers on top. Then `.ai_bridge/HANDOFF.md` for the live thread.

---

## 0. TL;DR — what changed since 2026-06-14

- **The mission pivoted (Felipe, ~2026-06-12).** The goal is no longer just the faithful shell. It is now also: **learn each piece of furniture as a procedural CLASS** (not overfit one nice example) and **render the furnished room photorealistically** — toward a sellable interior product. The shell pipeline is the *foundation*; the new value sits on top.
- **A furniture-class program shipped — 5 classes FROZEN.** sofa · armchair · bed · coffee-table · rack, each taken **WARN → PASS → FREEZE** through a formal cycle method judged by an external GPT judge. See §2.
- **A multi-agent "interior studio" exists** — a local team (Architect / Auditor / Render-Judges) coordinated by a live dashboard on **`:8782`**, all backed by **local Ollama models** (free compute). The agents **propose; Felipe approves; nothing mutates state autonomously**. See §3.
- **The V-Ray photoreal pipeline is PROVEN** — a photorealistic living-room render of planta_74 in ~68 s, frozen recipe, theme skin-swap. See §4.
- **New supporting infra:** a **RAG project-memory** with a `:8765` search endpoint (§5), a **real MCP server** (slice 1, FastMCP, 9 pure tools — §6), a **web "vitrine"** that explains the system to laypeople (`:8783` — §7), and **packaging** formalized into `core*`/`interior*`/`tools*` (§8).
- **Current state:** branch `develop` @ `b511f82`, clean, **no open PRs**. Several long-running services and ports now coexist (§9). Still **no CI**.

---

## 1. The mission pivot (read this to reset your mental model)

The 2026-06-14 handoff framed the unique thing as: *take a PDF floor plan and produce a faithful empty `.skp` shell.* That is **done and stable** (`artifacts/planta_74/planta_74.skp`, VISUAL_REVIEW = IMPROVED). Felipe then redirected the mission:

> "Stop *furnishing a room* / chasing one render. **Learn the CLASS of each piece of furniture procedurally** (sofa → armchair → bed → table → rack…), with a formal program: no overfit, form before detail, every improvement climbs into a spec/constraint/generator/gate, proof by generalization."

So the product is now a **three-layer stack**:

```
LAYER 1  faithful SHELL          ← the 2026-06-14 pipeline (consensus.json → .skp). UNCHANGED, stable.
LAYER 2  furnished ROOM          ← furniture CLASSES (procedural, judge-frozen) + a per-room program
                                    proposed by an Architect agent and approved by Felipe.
LAYER 3  photoreal RENDER        ← V-Ray, themed (skin-swap), light recipe frozen.
```

**What carries over unchanged (do not relearn the hard way):** every Hard Rule and every lesson in the 2026-06-14 doc still holds — *never invent geometry*, *windows preserve peitoril+verga*, *no SKP no progress*, *green tests ≠ visual proof*, *VISUAL_REVIEW is the one human gate*, *scale from a physical anchor*, *a gate that didn't run is not green*, *run deterministic detectors before trusting a render*. The studio layer **inherits** this discipline: its agents *propose*, deterministic gates are the *truth*, and only a human eye certifies appearance.

---

## 2. The furniture-class program ("ARQUITETO DE CLASSE")

The core idea: a "class" is **not** one good example with knobs. It is the **ergonomic ranges + relational constraints + archetypes + anti-regression blocks + scale model** that make *any* derived instance read as the same family. Encoded so a generator derives every cell with **zero manual tweaks** — generalization is the proof.

### 2.1 The cycle method (WARN → PASS → FREEZE)
Each class is taken through numbered cycles, each ending in an **explicit GPT-judge verdict** (ChatGPT GPT-5 "thinking," judging real rendered evidence via a pushed `raw.githubusercontent` URL — the image-handoff trick from the 2026-06-14 doc). The loop is the same `FAIL → rule → fixture → gate → judge` loop used for fidelity: **every judge complaint must climb into a spec/constraint/generator/gate as a general rule, never a one-off patch.** When the judge says "I'd freeze the FORM; further gains are another stage (bevel/material/scene)," the class **FREEZES** — any later shape change is a **new formal cycle**, never a casual edit.

### 2.2 The 5 frozen classes (all PASS @ cycle002)
Each has an executable class module (`tools/<x>_class.py`), a builder (`tools/<x>_builder.py` or `build_<x>`), a spec (`interior/class_specs/`), and a judge verdict (`.ai_bridge/fidelity/verdicts/<X>-CLASS_cycle002.md`). Each carries a **sentinel** — a worst-case stress cell kept to test future changes (never a cell to patch locally):

| Class | Module | What the class encodes | Sentinel cell |
|---|---|---|---|
| **Sofa** | `tools/sofa_class.py` | seat ranges, 9 relations, archetypes formal/standard/lounge, width *always derived* = N·per_seat + 2·arm; chaise as deck-L | `chaise-plinth` |
| **Armchair** | `tools/armchair_class.py` | "presença do braço" (arm + 0.06·wrap ≥ 0.17); shell-wraparound (U-shell, shoulders wrap); emancipated from the sofa | `lounge-highback` |
| **Bed** | `tools/bed_class.py` | discrete BR SKUs (no interpolation), mattress dominance, anti-throne headboard, base grammar per archetype (plinth/legs/box + saia/sapata) | `queen-box-legs` |
| **Coffee table** | `tools/coffee_table_class.py` | **satellite of the sofa** (length 0.58·sofa, top = seat − drop), octagon/chamfer for organic, saturation ≥2.6 m | `organic@formal-2l` |
| **Rack/media** | `tools/rack_class.py` | **satellite of the TV** (length = tv + 2·clearance, capped 2.60 m), esbeltez, floating/credenza/storage facades, TV center 0.80–1.25 m | `floating@tv75` |

### 2.3 Two institutional patterns the program established (apply to all future classes)
- **Satellite-by-derivation: "the principal class derives the ruler; the satellite adapts."** The coffee table derives from the sofa; the **nightstand** from the bed surface (`nightstand_satellite_gate`); the **rack** from the TV + the sofa viewing line (`tv_satellite_gate` + a sofa-distance/tilt gate). A satellite never sets its own dimensions in a vacuum.
- **"Satellite VISIBLE in the matrix" = institutional pattern.** The class **matrix/showroom** generator (e.g. `tools/sofa_class_matrix.py`, `build_matrix_skp --skp`) emits a 3×3 grid of derived cells for the judge — *zero manual tweaks*, which is the generalization proof. For the rack, the matrix now **draws a translucent TV proxy + a line of sight**, so the judge can validate the TV↔rack↔viewing derivation for real. Retrofit visible satellites into older matrices when they reopen.

### 2.4 Where the judgment history lives
- `HISTORICO_SOFA.json` (repo root) — the master audit trail of the sofa's evolution: recurring judge critiques (resolved/mitigated per cycle), `Parametros_bloqueados` (anti-regression locks: `backrest_rake=10°`, `cushion_bevel=0.04`, …), and a per-cycle log. The template every other class's history follows.
- `.ai_bridge/fidelity/verdicts/*-CLASS_cycle00{1,2,3}.md` — the verdicts themselves (judge quote, gates derived PASS / sabotages FAIL, fixes applied, sentinel).

### 2.5 Learning a class FROM a reference image (the next frontier)
A parallel path learns a class from curated reference pins, **without copying pixels**:
- `tools/reference_grammar.py` — normalizes a reference into canonical **design-grammar tokens** (language, not geometry). **Inviolable contract:** *the reference dictates LANGUAGE; the PDF/consensus dictates POSITION* — a reference never moves a wall, door, window, or plumbing point (`fixed_anchors`).
- `tools/reference_db.py` (SQLite index of `artifacts/reference_lab/`), `tools/style_spec.py` (kind→rgb/texture/kelvin style grammar), `tools/style_coherence_gate.py` (style consistency across a room).
- Skills: `joinery-ergonomics-reference`, `planned-joinery-translator`, `reference-to-joinery-translator` (`loose_object → planned_niche_system`: a free-standing fridge becomes an integrated tower + filler + breathing gap).
- **Transferable lesson:** encode professional knowledge as **relational constraints (ratios)**, not absolute sizes; only width scales with seats — never inflate depth/height; cross-class constraints are real and must be *derived*, not pinned.

---

## 3. The interior studio (the multi-agent design team)

A small local team that designs the furnished room. **The governing principle: every agent PROPOSES; deterministic gates are the truth; Felipe approves; nothing mutates state autonomously.** It is the LAYER-2 analogue of the LAYER-1 decision oracle — same "agent decides technical, human owns the visual" philosophy.

### 3.1 The dashboard — `tools/studio_dashboard.py` (`:8782`)
A stdlib `ThreadingHTTPServer` (no external deps; `python tools/studio_dashboard.py [--port 8782]`). It's the live cockpit for the studio: agent status cards + conversation arrows, a backlog kanban, the reference pack with curator buttons (👍/👎/⭐/🚫), the proposals queue (pending → approved/rejected), the learning log, the render gallery, and the cycles. Real-time feed comes from `tools/studio_log.py` (append-only `artifacts/reference_lab/studio_activity.jsonl`; `post()` / `talk()`). It also serves the vitrine pages (Map/Flow/How-it-works) on the same port. Model status is injected from `ollama_bridge` (green dot = model online). **Live.**

### 3.2 The agents (code in `tools/interior_studio/`, roles in `.claude/agents/`)
- **Architect — `architect_program.py`.** Local LLM (deepseek-r1:14b) **proposes a per-room furniture program** from room dims (consensus) + Felipe's "DNA" (industrial-boutique, black/wood/gold) + existing assets. It **never writes state** — `propose_and_save()` drops a proposal into `.ai_bridge/proposals/pending/`. A deterministic gate `normalize_program()` (SPEC-C) enforces invariants *around* the LLM: **CORE injection** (a sala must have a sofa, a kitchen a cooktop/fridge/counter…), **cross-room removal** (no bed in the living room), **prefix-stripping** (`banheiro_cooktop` → `cooktop`). The LLM is the engine; the gate is the guardrail. Pattern: *"deepseek thinks, qwen formats"* (qwen reformats deepseek's reasoning when JSON parse fails).
- **Consistency/Gap Auditor — `auditor.py`.** A **deterministic** worker that proposes, never mutates. Runs after state changes and writes `consistency_gap` proposals (idempotent: clears stale gaps). Replaced one monolithic gate with **6 legible thematic lenses** (SPEC-D): 🧭 pertencimento (item belongs to another room?), 📋 completude (CORE present?), 🏷️ nomenclatura (wrong-room prefix?), 📐 capacidade (floor fill > 55% WARN / 72% FAIL?), ♻️ redundância (>1 same-function item?), 🎨 estilo (respects DNA? — the only LLM-lite lens).
- **Render Judges / "JUÍZES DE RENDER" — `render_judge.py` + `interns.py`.** Bridge the "a local agent can't *see* an image" gap by translating a render into **structured facts** in 3 layers: (1) a **deterministic fingerprint** (luminance, exposure p95/contrast, clipped %, near-black %, warmth, 4-color palette — `render_fingerprint.py`); (2) a **local vision pass** (qwen2.5-vl) answering theme questions (e.g. `crushed_shadows?` for the black/wood/gold theme — `vision_describe.py`); (3) a **scoped synthesis** (deepseek) giving a 0–10 taste score + next action, grounded in the facts, *not* the raw pixels. Verdicts append to `.ai_bridge/interior_studio/render_judge_verdicts.jsonl`. These are *local advisory* judges — the **final** visual verdict is still Felipe (the negative-dogfood lesson: a vision model gives confident false PASSES).

### 3.3 The studio specs and the state machine (`.ai_bridge/interior_studio/`)
Five closed specs (A–E) plus role docs and a 2026-06-21 handoff. The load-bearing one is **SPEC-E: verdict-as-JSON sidecar** — state used to be derived by *substring-matching markdown* (fragile to wording/case). Now a blessed gate writes `artifacts/review/furniture/<asset>/<gate>/gpt_verdict.json` `{asset, gate, verdict, environment}`, and `project_state.py` reads `**/gpt_verdict.json` (markdown is fallback). *Don't reintroduce substring state.*

> **Reality check:** the studio agents run on **local Ollama**; the "GPT judge" for the *class freezes* is the real ChatGPT GPT-5 (via the pushed-image URL trick). The OpenAI-API path inside the studio is a **safe stub** — local-only today. Full cycle automation and the Chrome path are **not** wired; the loop is still human-stepped (Felipe approves proposals).

---

## 4. The V-Ray photoreal pipeline (LAYER 3) — PROVEN

Proven 2026-06-22: a photorealistic living-room render of planta_74 in ~68 s, first try after the recipe froze (`vray_pipeline_proof.png` at repo root; `artifacts/planta_74/furnished/…vray_sala*.png`).

**End-to-end** (`tools/render_scene_vray.py`, the orchestrator):
1. `scene.skp` (furnished, open dollhouse) + camera from `scene.json` (m→inches).
2. **Close the geometry** — assemble 4 walls + **ceiling** + furniture into `scene_closed.skp`. *An open dollhouse lets sky light flood the interior and wash the colors.*
3. **Export to `.vrscene`** via `SketchUp.exe … -RubyStartup tools/vray_export.rb` (the `vfs`/`VRay::Context` plugin path on SU 2026): applies procedural textures keyed by material name (`ph_*` furniture / `kc_*` kitchen / `fz_*` scene), optional room isolation, render floor/walls.
4. **Tweak the `.vrscene`** (`tools/tweak_vrscene.py`): exposure (ISO/f-number/shutter/sky), a BRDF material lookup table (wood satin, fabric matte, sofa fabric-sheen, metal, inox, stone, concrete…), **theme skin-swap** (`apply_scene_theme_black_wood_gold` — diffuse-color overrides via regex on BRDF blocks; *no geometry rebuild*), `add_fill_light` (warm interior fills), Reinhard `burn` tone-map.
5. **Headless render** `vray.exe -display=0 -autoClose=1` → PNG.
6. **`_flatten_alpha`** RGBA→RGB at output.

**Flags:** `--iso --fnum --shutter --sky --sun --sun-size --burn --fill "x,y,z,intensity[,radius_m];…" --scene-theme --width --height`.

**Frozen recipe (interior):** `iso 100 / f7 / shutter 160 / sky 0.3` (tuned on suite01). The earlier light loop's frozen daylight recipe is in `.ai_bridge/HANDOFF.md`.

**Hard-won lessons (frozen):**
- **The "dead window" that blocked 3 light cycles was `alpha=0` on the background, not lighting.** The sky RGB was always there; the browser showed transparent-as-white. `_flatten_alpha` fixed it. *When iteration stalls and no recipe helps, suspect the OBSERVATION path, not the thing you're tuning.*
- **The ceiling is mandatory** and **the model must be closed** before V-Ray (else sky-wash).
- **Always pass absolute paths to SketchUp** — it resolves `model.save`/`write_image` against *its own* cwd (`Path(...).resolve()`).
- **Themes are skin-swaps**: material diffuse + optional texture relink, geometry frozen. Any appearance change re-enters the GPT judge loop.

> V-Ray remains **gated on a clean composition PASS** before rendering (the LAYER-2→3 gate); don't render a composition the judge hasn't blessed.

---

## 5. RAG project-memory + Ollama as free compute

- **`tools/project_memory_db.py`** — a local **RAG** over the project's own writing (handoffs, verdicts, lessons, cycles, consults, research). SQLite store (`.ai_bridge/project_memory.db`); embeddings via **Ollama `nomic-embed-text`**; cosine search in NumPy (no external vector DB). Markdown/JSON/JSONL chunked per type; idempotent re-index keyed on content hash.
- **`:8765` `GET /api/memory/search?q=…&k=6`** (in `tools/claude_bridge/server.py`, route registered at the `/api/memory/search` handler) — lets any agent ask *"what did we already decide/learn about X?"* over HTTP. Read-only; **fails loud** (500) if Ollama is down or the index is empty — never fabricates.
- **`tools/ollama_bridge.py` / `claude_bridge/ollama_client.py`** — the local-LLM bridge ("Ollama = compute grátis"): `probe()` health + `generate()` text (llama3.1:8b default). Raises `OllamaUnavailable` so the caller decides the fallback. This is the **"brain/muscle"** split — cheap local models do triage/draft/format/audit; the expensive judge is reserved for the final visual call.

---

## 6. The MCP server (slice 1) — the repo is (partly) an MCP server again

`tools/mcp_server/` is a **real FastMCP server** (`pip install -e .[mcp]`, run `python -m tools.mcp_server.server`, stdio transport). Slice 1 exposes **9 pure, SketchUp-free tools**: `list_capabilities`, `run_deterministic_gates`, `furniture_class_derive` (routes sofa/bed/armchair/dining/rack/coffee), `reference_to_grammar`, `validate_grammar_spec`, `room_gates`, `kitchen_ergonomics_audit`, `promote_canonical`, `skp_inventory`. Transport is proven by `smoke.py` (in-process) and `stdio_check.py` (real MCP handshake). **Slice 2** (the SketchUp-heavy verbs: build_shell, furnish, render_scene_vray, consult_oracle) is **deferred** (needs SU + background-process handling).

> **README is stale here:** `README.md` still says *"despite the `-mcp` suffix, this repo is currently … not a Model-Context-Protocol server."* That is now false for slice-1 tools. Also `README.md` says "41 test suites" while `tests/` now holds ~67 files. Minor — flag for a docs refresh.

---

## 7. The web "vitrine" (`:8783`) — explain the system to a layperson

`tools/vitrine/` — a dark-pastel, animated web explainer of the whole system, born after Felipe explored (and rejected) an Obsidian second-brain. **Landed today** (`b511f82` reorganized it under `tools/vitrine/`; it was untracked when `VITRINE_HANDOFF.md` was written on 2026-06-22).
- **Pages:** `home / grafo / fluxo / agents / explica` served by `grafo_server.py` (stdlib, `:8783`, routes `/ /grafo /fluxo /agents /explica /api/kgraph`). Also surfaced inside the studio dashboard (`:8782`).
- **Knowledge graph:** `build_kgraph.py` builds `kgraph.json` (**61 nodes / ~385 edges**) from a markdown vault; **snapshot** — rebuild if the notes change.
- **Durable hosting:** `Dockerfile.grafo` + `subir-vitrine.cmd` (container `sketchup-grafo`, `--restart unless-stopped`).
- **Grounded, not invented:** the diagrams were built from a real code map (auditor caught and fixed a "vector-first extraction" step that describes the *dead* pipeline, and an "an LLM generates the .skp" claim — the `.skp` build is **0% AI, pure code**). North-star style = ByteByteGo / Alex Xu.

---

## 8. Packaging & structure (`pyproject.toml` v0.2.0)

- Packages now formally declared: `include = ["tools*", "core*", "interior*"]`. Core deps `shapely / pypdfium2 / Pillow / numpy / matplotlib`; extras `[dev]` (pytest, ruff) and `[mcp]` (`mcp>=1.2`). `requires-python >=3.11`.
- **`core/`** — `scale.py` (the single source of truth for `PT_TO_M`/unit conversion; the scale-centralization lesson from the prior handoff).
- **`interior/`** — `planners/` (living_room, placement_brain) · `composer/` (scene_composer) · `validators/` (placement & spatial gates) · `renderers/` (sketchup_basic / vray_final / enscape_preview providers + abstract `render_provider`) · `semantics/` (room_graph, wall_affordance) · `class_specs/ schemas/ specs/ style_packs/`.
- **`tools/`** — the shell builders, the fidelity gates, the visual oracle, the furnish layer, the furniture classes, `claude_bridge/` (`:8765`), `interior_studio/` (`:8782`), `vitrine/` (`:8783`), `mcp_server/`, `pdf_knowledge/`, `prompts/`, `quadrado/`.
- **`CLAUDE_COGNITIVE_ARCHITECTURE.md`** (repo root) — a meta-doc mapping how `.claude/CLAUDE.md`'s `@import` chain + skill auto-discovery + on-demand specs actually load context per session. Read it to understand the agent's information flow.

---

## 9. Current state, services, and coordination risks

**Branch:** `develop` @ `b511f82` (2026-06-24), clean, `main`-via-`develop` only. **No open PRs.** Tests are Python-only (~67 files); **still no `.github/workflows/` (no CI)** — the no-CI lesson from the prior handoff is still open.

**Ports / long-running services now in play:**

| Port | Service | Backed by |
|---|---|---|
| `:8765` | Decision oracle + cockpit **+ `/api/memory/search`** | `tools/claude_bridge/server.py` (headless `claude -p`, Opus, mode B) |
| `:8782` | Interior **studio** dashboard | `tools/studio_dashboard.py` |
| `:8783` | **Vitrine** web explainer | `tools/vitrine/grafo_server.py` (docker `sketchup-grafo`) |
| `11434` | Local LLMs (deepseek-r1 / qwen2.5-coder / qwen2.5-vl / nomic-embed / llama3.1) | Ollama |

**Coordination risks (real, documented):**
- **Multi-agent worktree collisions (DIFF-004) are real and unsolved at the root.** The repo has a *permanent rule*: multiple agents → **isolated git worktrees**, never the same working dir; pre/post-commit checks; STOP on any unexpected branch/HEAD/tree change. `VITRINE_HANDOFF.md` records a session that **swallowed another session's uncommitted work** on the same branch (undone with `git reset`). Run `git worktree list` before any branch op.
- **Some narrative state is stale** — `.ai_bridge/HANDOFF.md`'s last dated entry is 2026-06-12 and `.claude/memory/current_state.md` is 2026-06-06, both behind develop HEAD (2026-06-24). The freshest narrative is the **git log + the studio specs**, not those files. Refresh `current_state.md` when you next touch it.

---

## 10. For a successor: how to pick up the new layers

### 10.1 What's unchanged (inherit it wholesale)
All seven Hard Rules and all numbered lessons from the **2026-06-14 doc**. The studio is *governed by* that discipline, not exempt from it: agents propose, deterministic gates are truth, Felipe owns the visual verdict.

### 10.2 What's NEW to internalize
1. **A class is a cycle, not an edit.** Take it `WARN → PASS → FREEZE` with a judge; every complaint climbs into spec/constraint/generator/gate; prove by **generalization** (the matrix re-derives the worst cell with zero manual tweaks). After PASS, a shape change is a **new formal cycle**.
2. **Satellite-by-derivation.** Principal class derives the ruler; satellites adapt via gates (`nightstand_satellite_gate`, `tv_satellite_gate`, the sofa-distance/tilt gate). Draw the satellite (e.g. TV proxy + sight line) **visibly in the matrix**.
3. **Agents propose; they never mutate.** The Architect drops proposals into `.ai_bridge/proposals/pending/`; deterministic gates (`normalize_program`, the 6 auditor lenses) wrap the LLM; Felipe approves. State is **JSON-first** (`gpt_verdict.json`), never substring-derived.
4. **Local Ollama is the cheap engine; the GPT judge is reserved.** Brain/muscle split. The local **render judges are advisory** — the final visual verdict is human (negative-dogfood).
5. **V-Ray recipe is frozen; themes are skin-swaps.** Close the model, keep the ceiling, absolute paths, flatten alpha. Render only a composition the judge has PASSed. Any appearance change re-enters the judge loop.

### 10.3 First moves on a cold start
1. **Read the 2026-06-14 handoff, then this one, then `.ai_bridge/HANDOFF.md`** (and remember the last two narrative files are stale vs the git log).
2. **Bring up what you need, verify it's live** (code ≠ process): `:8765` oracle/memory (`GET /health`, `GET /api/memory/search?q=…`), `:8782` studio dashboard, Ollama (`11434`). Restart after any change.
3. **For a furniture-class change:** open a formal cycle → derive the matrix → run the class + anatomy + satellite gates → produce the rendered grid → push it → GPT judge → freeze on PASS. Never hand-tweak one cell.
4. **For a studio/program change:** propose via the Architect, let the Auditor's 6 lenses run, route the approval to Felipe. Keep verdicts as `gpt_verdict.json`.
5. **For a render change:** close the model, apply the frozen recipe, skin-swap the theme, flatten alpha — then re-enter the judge loop because appearance changed.

### 10.4 Honest maturity caps (unchanged in spirit)
- LAYER 1 (shell): stable, deterministic-confidence ~70% / with-bridge ~85%, **never 100%**.
- LAYER 2 (classes): **5 frozen by judge PASS**; the *reference-learning* path and *full studio automation* are **WIP** (human-stepped; OpenAI-API path is a stub).
- LAYER 3 (render): the recipe is **proven** on the sala; generalizing themes/rooms is ongoing. The local render judges are **advisory, not authoritative**.

### 10.5 Known open follow-ups (logged, not faked as solved)
- Per-`session_id` worktree lock (DIFF-004 root fix) — still open; the studio added more concurrent sessions, so the risk grew.
- Minimal GitHub Actions pytest workflow (the no-CI lesson) — still absent.
- Docs refresh: `README.md` (MCP-server claim + test count) and `current_state.md` (stale snapshot).
- Reference-learning path (`reference_grammar` / `style_spec`) and full studio cycle automation — both WIP.

---

*If you remember one thing on top of the 2026-06-14 doc: the studio didn't loosen the discipline — it **scaled** it. The same "engine proposes, deterministic gates are truth, only a human eye certifies the picture" rule now governs three layers instead of one. A class is frozen by generalization, a satellite is derived not guessed, an agent proposes but never mutates, and a render is judged after — not instead of — the gates.*
