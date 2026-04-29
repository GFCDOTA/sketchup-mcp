"""Oracle / architect helpers — external comparators for the pipeline output.

Sub-modules:
- llm_architect.py   Vision LLM (Claude) reads debug PNGs, returns structured defect list
- cubicasa.py        CubiCasa5K (vendored DL model) runs inference, returns walls/openings

Both are dev-time tools. They are NEVER imported by `main.py`, the API, or any
service in the pipeline core (CLAUDE.md invariants §6).
"""
