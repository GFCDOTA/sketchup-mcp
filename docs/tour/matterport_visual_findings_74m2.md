# Matterport Visual Validation — Living Grand Wish Jardim 74m²

> Visual ground-truth pass against the residual visual defects (V1, V2,
> V4, V5) listed in the SKP fidelity side-by-side
> (`runs/skp_current_20260504T215920Z/sidebyside_pdf_vs_skp.png`).
>
> **Source:** public Matterport Pro2 capture at
> https://discover.matterport.com/space/rLoqyVDHfzC ("Living Grand Wish
> Jardim - 74m²", 27 scan positions, 36 photos/video, hosted by PIPERZ HOST).
>
> **Scope:** validate or contradict V1/V2/V4/V5. Not a metric source — no
> dimensions extracted, no mesh/texture/asset download, no proprietary
> data accessed. Public viewer screenshots and structural observation only.

## Method

Browser-driven inspection via Claude_in_Chrome MCP:

1. Loaded the tour URL.
2. Switched to **dollhouse** view (toolbar icon) — full 3D apartment.
3. Switched to **top-down floorplan** view (Ctrl+drag tilt) — direct
   structural comparison with the SKP consensus top render.
4. Walked **FPV** scans through:
   - Living/sofá area (initial scan, scan 16/27).
   - A.S. (área de serviço) corridor between exterior wall and kitchen.
   - Kitchen island looking toward dining/terraço.
   - Dining/terraço with formal 6-chair table and porta-balcão.
5. Cross-checked with the curated `Photos and Video` gallery (36 items,
   covering each room from designer angles).

## Per-defect verdict

### V1 — SALA DE ESTAR has a diagonal bite from TERRACO TECNICO

> **In the SKP top render, the bottom edge of SALA DE ESTAR is cut by a
> diagonal line coming from TERRACO TECNICO; the room boundary is
> non-canonical.**

**Verdict: CONTRADICTED — artifact of polygonize, not a real architectural feature.**

Matterport top-down shows SALA DE ESTAR (sofá branco em L + tapete cinza
+ mesa de centro circular) with **fully orthogonal walls**. There is no
diagonal cut between the living and the technical terraço. The angle in
the SKP comes from the `rooms_from_seeds` polygonizer creating a
non-axis-aligned segment, not from a real wall. The "bite" coincides
with where the `polygonize` algorithm picks the closest junction, which
on this consensus is offset diagonally from the rectilinear truth.

**Recommended action:** investigate `tools/rooms_from_seeds.py` for
boundary snapping at near-orthogonal seeds. Out of scope for this PR
(needs a separate Track A defect-attack PR).

### V2 — TERRACO SOCIAL is pentagonal in the SKP, looks rectangular in the PDF

> **The SKP shows TERRACO SOCIAL with an angular cut on the lower-left
> corner; the PDF dimensioned shape suggests a rectangle.**

**Verdict: LIKELY CONTRADICTED — rectangular wood-floor terraço in Matterport, but full top-down crop of the terraço alone was not captured.**

Matterport dollhouse and top-down both show a clear **wood-floor area**
(distinct from the interior porcelain) along the building's exterior
edge. From the angles I captured (dollhouse + dining-area FPV looking
toward porta-balcão + tour photo 5/36 showing 6-chair dining with full
glass curtain wall), the wood deck appears **rectangular** with the
formal dining set on it. The pentagonal cut in the SKP top likely
mirrors the same near-orthogonal seed-snap issue that produces V1.

**Caveat:** I did not capture a clean top-down crop isolating only the
TERRACO outline. The pentagonal angle is small and could match a real
column or corner of the building — confirmation would require either
the original architectural plan or one more Matterport scan position
inside the terraço at the corner. Listed under "Manual screenshots
needed" below.

**Recommended action:** same as V1 — root cause is likely shared in
`tools/rooms_from_seeds.py` boundary snapping. Defer until V1 is
attacked.

### V4 — A.S. has weird proportion / position

> **In the SKP top, A.S. is a vertical strip on the far left, but the
> proportion and the way it intrudes between cozinha and other rooms
> looks off.**

**Verdict: CONFIRMED — A.S. IS a thin vertical strip; SKP layout is correct, just the rendering exaggerates the elongation.**

Matterport FPV from the kitchen-side scan shows A.S. as exactly that:
a **narrow vertical corridor** between the building's exterior wall
(left, with plants and a window) and the kitchen counter wall (right).
Washing machine + dryer + utility sink fit lengthwise. The SKP
representation is structurally correct — what looked "wrong" was the
horizontal stretch caused by the page-aspect of the side-by-side
composition, not the underlying geometry.

**Recommended action:** none on the geometry. When generating
side-by-side images, lock aspect ratio to the consensus's
`planta_region` to avoid the apparent stretch. Could be a 5-line tweak
to `runs/skp_current_*/sidebyside_pdf_vs_skp.png` rendering — minor.

### V5 — Some openings render as thin orange strips instead of recognizable doors

> **A few of the 12 openings in the SKP show as thin orange rectangles
> on the wall instead of arc-symbol-style doorways.**

**Verdict: EXPLAINED — thin strips correspond to wide open passages without an arc symbol in the source PDF (kitchen↔living, living↔terraço); they're not doors.**

Matterport confirms that several transitions in this apartment have **no
physical door**, just an open passage:
- Living ↔ Cozinha: open — sofá's back faces the kitchen island.
- Living ↔ Sala de Jantar (the formal terraço-dining): open — same
  ambient.
- Living ↔ Terraço Social: glazed sliding door (the porta-balcão), open
  in the tour.

Rooms with **real arc-doors** (doors that swing): SUITE 01, SUITE 02,
BANHO 01, BANHO 02, LAVABO. These ARE the openings that render properly
in the SKP.

The "thin strips" in the SKP are the vector extractor detecting a wall
**gap** without finding the corresponding arc symbol that the PDF would
draw for a swinging door — because no swinging door exists. This is
**semantically correct** (there really is an opening there) but
**visually impoverished** (strips don't communicate "wide open
passage").

**Recommended action:** classify openings into `door_arc` /
`open_passage` / `glazed_balcony` in the consensus schema, then render
each class with a different SKP material/symbol. This is a 30-50 line
change in `tools/extract_openings_vector.py` (adding a `kind` field) +
a small `tools/consume_consensus.rb` branch on the `kind` to pick
material. Schema-additive, not a breaking change. Worth a separate
Track A PR after V1/V2 root cause is fixed.

## Summary table

| Defect | SKP shows | Matterport ground truth | Verdict | Type |
|---|---|---|---|---|
| V1 SALA DE ESTAR diagonal bite | non-orthogonal cut | rectangular sala | **CONTRADICTED** | polygonize artifact (`rooms_from_seeds`) |
| V2 TERRACO SOCIAL pentagonal | angular cut | rectangular wood deck | **LIKELY CONTRADICTED** | likely same as V1 |
| V4 A.S. proportion | narrow strip | narrow strip | **CONFIRMED** (display-only issue) | side-by-side aspect, not geometry |
| V5 openings thin strips | thin orange strips | open wide passages, no arc | **EXPLAINED** | semantic, not bug — strips = wide-open passages w/o arc |

## Manual screenshots needed (for stronger confirmation)

To turn V2 from "likely contradicted" into "definitively contradicted" I
would want — if you can capture them manually from the Matterport tour:

1. **Top-down floorplan zoomed only on the TERRACO** (left wood-floor
   area). The Matterport top-down view is the fastest comparable to the
   SKP consensus top render. Open the tour, switch to dollhouse, tilt
   to top, zoom into the wood-floor area.
2. **FPV from inside the TERRACO looking back at the building** — shows
   any structural column or angular wall that might justify a real
   pentagonal cut.

These two would let `tools/rooms_from_seeds.py` be patched (or not)
with confidence.

## Decision: no source code change in this PR

V1 and V2 share a likely root cause inside `tools/rooms_from_seeds.py`
(near-orthogonal seed-snap producing diagonal segments). Fixing it
requires careful attention to `door-min`/`door-max` parameters and the
seed graph — not a 5-line patch. CLAUDE.md §1.3 also makes geometry
threshold changes a "human approval" item. Out of scope for a docs-only
visual-validation PR.

V4 is a side-by-side rendering aspect issue, not geometry — fix it if
you want a more honest visual artifact, but the model is correct.

V5 is a semantic enrichment opportunity; deferred to a Track A PR that
adds an opening `kind` discriminator.

This document is the deliverable. It says, per defect, whether
Matterport confirms or contradicts the SKP, and points to the right
file for any future attack.

## Cross-links

- SKP fidelity baseline: `docs/validation/skp_fidelity_2026-05-04.md`
- Side-by-side artifact: `runs/skp_current_20260504T215920Z/sidebyside_pdf_vs_skp.png` (gitignored)
- Visual defect list: that side-by-side, plus this session's prior
  analysis (V1-V8 enumerated when the user asked for the visual review).
- Pipeline source likely involved in V1/V2 root cause:
  `tools/rooms_from_seeds.py` (seed → polygon snapping).
- Pipeline source for V5 enrichment: `tools/extract_openings_vector.py`
  (would add a `kind` field) + `tools/consume_consensus.rb` (would
  branch on `kind`).
