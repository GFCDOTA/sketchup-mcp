#!/usr/bin/env python3
"""Difficulties + Learning-Loop backlogs for the cockpit knowledge pages.

Extracted from server.py (SRP): the operational-memory domain (living
difficulties backlog + failure-pattern learning loop), each read from
.ai_bridge/*.jsonl with a built-in seed fallback + normalization. server.py
re-exports difficulties / learnings for its route table.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_jsonl(path: Path) -> list:
    """Tolerant JSONL read: skips blank/corrupt lines, never raises."""
    out = []
    try:
        for ln in path.read_text("utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except ValueError:
                pass
    except OSError:
        pass
    return out


# Seed of the living difficulties backlog. The .ai_bridge/creator_difficulties.jsonl
# (if present) overrides this; otherwise this built-in seed is served. Every entry
# MUST carry why_not_fixed_yet — the field that turns "known problem" into "actionable".
_DEFAULT_DIFFICULTIES = [
    {"id": "DIFF-001", "titulo": "Consensus é autoria humana (sem extrator PDF→consensus)",
     "sintoma": "não há pipeline que extraia walls/openings de um PDF novo; raster+Hough fabricava parede falsa",
     "severidade": "HIGH", "status": "DEFERRED", "review_by": "2026-07-15",
     "why_not_fixed_yet": "extrator vetorial confiável é grande e arriscado; decidiu-se provar o loop manual em >=2 plantas antes de investir",
     "attempts": ["raster+Hough (abandonado: fabricava falsos)", "build_vector_consensus (abandonado)"],
     "gate_helped": "parcial", "next_hypothesis": "walls = filled paths do PDF, validado contra a planta_74 já anotada",
     "acceptance_criteria": "uma 2a planta gera consensus sem anotação manual e passa os gates determinísticos"},
    {"id": "DIFF-002", "titulo": "Escala precisa de âncora física",
     "sintoma": "PDF→metros sem uma dimensão real conhecida vira chute",
     "severidade": "HIGH", "status": "MITIGATED",
     "why_not_fixed_yet": "depende de input humano por planta (uma cota/espessura real) — é requisito de dado, não bug",
     "attempts": ["PT_TO_M = wall_thickness_pts/0.19 (planta_74)"],
     "gate_helped": "nao", "next_hypothesis": "plant.json carrega wall_thickness_m por planta; sem âncora = BLOCKED",
     "acceptance_criteria": "toda planta nova declara a âncora; nunca usar default 0.0254/72"},
    {"id": "DIFF-003", "titulo": "Fidelidade de abertura de janela (peitoril/verga)",
     "sintoma": "janela carved full-height ou vidro órfão/fora do lugar (ex.: banho 2)",
     "severidade": "MED", "status": "FIXED",
     "why_not_fixed_yet": "corrigido recentemente (528e302 usa espessura da wall hospedeira) — manter sob watch p/ regressão",
     "attempts": ["3D aperture path preservando peitoril+verga", "host-wall thickness fix (banho 2)"],
     "gate_helped": "sim", "next_hypothesis": "-",
     "acceptance_criteria": "window_apertures_3d == count(kind=window), sem vidro órfão"},
    {"id": "DIFF-004", "titulo": "Colisão de worktree multi-agent",
     "sintoma": "sessões dividindo 1 worktree movem o branch sob a outra; quase clobber",
     "severidade": "MED", "status": "OPEN",
     "why_not_fixed_yet": "o orquestrador só DETECTA (heartbeat/PARALYZED); o fix-raiz (lock/isolamento de worktree) é follow-up aberto, não implementado",
     "attempts": ["orquestrador de liveness (detecção)", "worktrees isolados (wt-dash/wt-gh)"],
     "gate_helped": "sim", "next_hypothesis": "/lock keyed por session_id + ownership de branch",
     "acceptance_criteria": "duas sessões rodam sem clobber; lock visível no painel"},
    {"id": "DIFF-005", "titulo": "Julgamento visual não é auto-confiável",
     "sintoma": "oracle de visão deu PASS em planta com parede externa apagada (negative_dogfood)",
     "severidade": "HIGH", "status": "MITIGATED",
     "why_not_fixed_yet": "LLM visual não pode ser ground truth — é decisão de design (só humano/GPT-Chrome valida), não bug a consertar",
     "attempts": ["visual oracle rebaixado a conselheiro", "overlay_diff determinístico decide"],
     "gate_helped": "sim", "next_hypothesis": "determinístico decide; visual só aconselha + VISUAL_REVIEW humano",
     "acceptance_criteria": "nenhum PASS visual auto-promove fixture; VISUAL_REVIEW obrigatório"},
    {"id": "DIFF-006", "titulo": "Constantes do builder hardcoded p/ planta_74",
     "sintoma": "alturas (2.70/0.90/2.10/1.10) e crop/escala fixos no build_plan_shell_skp",
     "severidade": "LOW", "status": "OPEN",
     "why_not_fixed_yet": "é o arquivo mais QUENTE (fidelidade em voo) e a config não tem consumidor até existir 2a planta = seria infra-pela-infra; blueprint pronto esperando a árvore esfriar",
     "attempts": ["blueprint generalize_builder_constants.md (groundwork não-colidente)"],
     "gate_helped": "sim", "next_hypothesis": "plant.json com heights/crop, defaults não-quebra, swap-in quando quieto",
     "acceptance_criteria": "planta_74 inalterada sem plant.json; 2a planta respeita os valores dela"},
]


def difficulties() -> dict:
    """Living difficulties backlog. Reads .ai_bridge/creator_difficulties.jsonl if
    present (appendable by sessions), else the built-in seed. Normalizes so EVERY
    entry has why_not_fixed_yet."""
    items = _read_jsonl(REPO_ROOT / ".ai_bridge" / "creator_difficulties.jsonl")
    src = "jsonl" if items else "builtin-seed"
    if not items:
        items = _DEFAULT_DIFFICULTIES
    norm = []
    for d in items:
        norm.append({
            "id": d.get("id", "DIFF-???"),
            "titulo": d.get("titulo") or d.get("title") or "?",
            "sintoma": d.get("sintoma", ""),
            "severidade": d.get("severidade", "MED"),
            "status": d.get("status", "OPEN"),
            "why_not_fixed_yet": d.get("why_not_fixed_yet") or "UNKNOWN — campo ausente, investigar",
            "attempts": d.get("attempts", []),
            "gate_helped": d.get("gate_helped", "?"),
            "next_hypothesis": d.get("next_hypothesis", "-"),
            "acceptance_criteria": d.get("acceptance_criteria", "-"),
            "review_by": d.get("review_by", ""),
        })
    return {"difficulties": norm, "total": len(norm), "source": src}


# Learning Loop seed — failure patterns turned into operational memory so the
# system stops repeating the same mistake. Every entry MUST have como_prevenir_regressao.
_DEFAULT_LEARNINGS = [
    {"id": "FP-031", "falha_observada": "visual oracle deu PASS em planta com parede externa apagada",
     "causa_provavel": "LLM de visão não distingue ausência estrutural sutil + viés de concordância",
     "como_detectamos": "negative_dogfood (fixtures corrompidas de propósito + teste de discriminação)",
     "como_corrigimos": "rebaixar o oracle visual a conselheiro; overlay_diff determinístico vira o juiz",
     "como_prevenir_regressao": "detector DETERMINÍSTICO decide; visual só aconselha; VISUAL_REVIEW humano pra promover",
     "artefato": "tools/overlay_diff.py + tools/negative_dogfood.py + LL nos memory", "status": "APPLIED"},
    {"id": "LL-034", "falha_observada": "gate framework §6 (multi-oracle/redteam/confidence) landou VERDE mas DESPLUGADO do caller real",
     "causa_provavel": "módulos + testes unitários, sem teste de integração que prove o wiring no ask_gpt_gate",
     "como_detectamos": "review cético + grep (ask_gpt_gate não importava parse_verdict/oracle_router/redteam)",
     "como_corrigimos": "plugar parse_verdict no run_gate; wirar redteam nos triggers pesados; deletar o 6.1 (independência falsa)",
     "como_prevenir_regressao": "todo módulo de gate exige teste de INTEGRAÇÃO que prove o caller usando — verde unitário != live",
     "artefato": "test_run_gate_online_parses_verdict + test_run_gate_sends_redteam", "status": "APPLIED"},
    {"id": "LL-035", "falha_observada": "claude -p rodado de dentro do repo dispararia o SessionStart hook que sobe o próprio bridge = recursão",
     "causa_provavel": "claude -p carrega CLAUDE.md/hooks do cwd",
     "como_detectamos": "análise ao consolidar o bridge no repo (antes de subir)",
     "como_corrigimos": "rodar claude -p com cwd=tempfile.gettempdir() (fora do repo)",
     "como_prevenir_regressao": "qualquer claude -p headless do gate usa cwd NEUTRO fora do repo",
     "artefato": "server.py ask_claude (cwd=workdir)", "status": "APPLIED"},
    {"id": "LL-021", "falha_observada": "escala PDF→metros chutada (0.0254/72) gera SKP fora de proporção",
     "causa_provavel": "usar DPI default em vez de uma âncora física real da planta",
     "como_detectamos": "comparação visual com a planta + regra de extração honesta",
     "como_corrigimos": "PT_TO_M = wall_thickness_pts / 0.19 (dimensão real conhecida)",
     "como_prevenir_regressao": "plant.json declara wall_thickness_m; sem âncora = BLOCKED, nunca chutar default",
     "artefato": "PT_TO_M anchor + spec generalize_builder_constants", "status": "APPLIED"},
    {"id": "LL-036", "falha_observada": "sessões Claude dividindo um worktree movem o branch sob a outra (quase clobber)",
     "causa_provavel": "falta de isolamento/lock entre agentes no mesmo checkout",
     "como_detectamos": "o branch mudou ~5x sob a sessão durante o build do cockpit",
     "como_corrigimos": "trabalhar em worktrees isolados (wt-dash etc.) + rebase antes do push",
     "como_prevenir_regressao": "cada sessão no SEU worktree + lock por session_id (follow-up aberto)",
     "artefato": "orquestrador /sessions (detecção) + chip worktree-lock", "status": "LEARNED"},
]


def learnings() -> dict:
    """Learning Loop: failure patterns (falha→causa→correção→prevenção→artefato).
    Reads .ai_bridge/learning_log.jsonl if present, else the built-in seed.
    Normalizes so EVERY entry has como_prevenir_regressao."""
    items = _read_jsonl(REPO_ROOT / ".ai_bridge" / "learning_log.jsonl")
    src = "jsonl" if items else "builtin-seed"
    if not items:
        items = _DEFAULT_LEARNINGS
    norm = []
    for x in items:
        norm.append({
            "id": x.get("id", "FP-???"),
            "falha_observada": x.get("falha_observada") or x.get("failure") or "?",
            "causa_provavel": x.get("causa_provavel", ""),
            "como_detectamos": x.get("como_detectamos", ""),
            "como_corrigimos": x.get("como_corrigimos", ""),
            "como_prevenir_regressao": x.get("como_prevenir_regressao") or "UNKNOWN — preencher",
            "artefato": x.get("artefato", "-"),
            "status": x.get("status", "LEARNED"),
        })
    return {"learnings": norm, "total": len(norm), "source": src}
