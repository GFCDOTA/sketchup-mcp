# Dashboard — Plantas tab

HTML/CSS/JS dashboard for browsing pipeline runs and oracle output. Standalone, served via Python's built-in HTTP server.

## Run

```bash
# From the repo root (microservices/plan-extract-v2/)
python -m http.server 8765 --directory tools
```

Then open <http://localhost:8765/dashboard/#plantas>.

The `tools/runs/` folder is the place where `_oracle_manifest.json` lives. The dashboard fetches `../runs/_oracle_manifest.json` (relative to `tools/dashboard/`), so symlink or copy your project runs there if you want them visible in the manifest.

## Tabs

- **Geral / Decisões / Aprendizados / Analítico** — populated from `runs/_index.json` and `runs/_learnings.json` (not in this repo; they're emitted by the workspace-level `observability/` instrumentation when it's set up).
- **Plantas** — gallery of:
  - Render limpo (output esperado pós Fase 6) — `assets/plantas/02_render_top.png`, `03_render_frontal.png`, `04_render_axon.png`
  - Pipeline atual (output bruto) — original PDF, overlay, audited, F1 validation
  - Evolução & comparações — raster vs SVG, v1→v2→v3, v3→v5
  - Workspace overview infographic
  - **Oráculo / Diagnóstico** — populated from `_oracle_manifest.json` when oracle scripts (`scripts/oracle/llm_architect.py`, `scripts/oracle/cubicasa.py`) have written diagnosis files for any run.

## Empty state

If `_oracle_manifest.json` has `runs: []` (the default after first install), the Plantas > Oráculo section shows the placeholder "Nenhum run com oracle output ainda. Rode `scripts/oracle/llm_architect.py --run <run>` para popular." That's expected on a fresh checkout.

## Populating the manifest

After running an oracle script on a run, append it to `tools/runs/_oracle_manifest.json`:

```json
{
  "schema_version": "1.0.0",
  "runs": [
    {"name": "openings_refine_final", "has_llm": true, "has_cubicasa": true}
  ]
}
```

The dashboard then fetches `runs/openings_refine_final/oracle_diagnosis_llm.json` and `runs/cubicasa_openings_refine_final/cubicasa_observed.json` automatically.
