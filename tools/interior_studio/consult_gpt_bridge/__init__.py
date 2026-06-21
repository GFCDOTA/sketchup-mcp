"""consult_gpt_bridge — ponte pergunta/resposta estruturada Arquiteto <-> Consult GPT.

API pública usada pelo studio_dashboard.py (endpoints /api/consult/*):
    from tools.interior_studio.consult_gpt_bridge import (
        contracts, store, prompt_builder, answer_parser, ingest, openai_client)
"""
from __future__ import annotations

from tools.interior_studio.consult_gpt_bridge import (  # noqa: F401
    answer_parser, contracts, ingest, openai_client, prompt_builder, store)

__all__ = ["contracts", "store", "prompt_builder", "answer_parser", "ingest", "openai_client"]
