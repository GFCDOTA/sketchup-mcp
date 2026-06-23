"""theme_intern.py — o ESTAGIÁRIO por tema valida um render. Fecha a ponte "agente local não
vê imagem": traduz o render (fingerprint determinístico + visão local) e deixa um estagiário
ESCOPADO AO TEMA julgar contra o schema dele.

Hierarquia honesta:
  1. fingerprint determinístico (números) + visão local (qwen2.5vl) = TRADUÇÃO do render.
  2. checks do tema avaliados sobre a tradução = VEREDITO AUTORITATIVO (gate determinístico onde dá).
  3. estagiário-LLM (deepseek, escopado ao DNA do tema) = SÍNTESE: taste 0-10 + porquê + próxima ação.
  O estagiário NÃO substitui o gate; ele explica e aponta o próximo passo. O veredito FINAL de
  aparência continua sendo do Felipe/GPT (este é o checkpoint LOCAL que faltava).

Uso: python -m tools.interior_studio.theme_intern <render.png> --theme black_wood_gold [--no-intern]
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

from tools.interior_studio import theme_registry as reg
from tools.interior_studio.render_fingerprint import fingerprint
from tools.interior_studio.vision_describe import describe

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / ".ai_bridge/interior_studio/intern_verdicts.jsonl"
OLLAMA = "http://127.0.0.1:11434/api/generate"
_ORDER = {"FAIL": 3, "WARN": 2, "PASS": 1, "UNKNOWN": 0}


def overall_status(check_results: list[dict]) -> str:
    """Pior status entre os checks (UNKNOWN não derruba). Gate: qualquer FAIL -> FAIL."""
    real = [c["status"] for c in check_results if c["status"] != "UNKNOWN"]
    return max(real, key=lambda s: _ORDER[s]) if real else "UNKNOWN"


def _ollama(model: str, prompt: str, timeout: int = 200) -> str:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.2, "num_predict": 900}}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode()).get("response", "")


def _extract_json(txt: str) -> dict | None:
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S)
    txt = re.sub(r"```(?:json)?", "", txt)
    i, j = txt.find("{"), txt.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(txt[i:j + 1])
    except Exception:  # noqa: BLE001
        return None


def _fp_summary(fp: dict) -> str:
    e = fp["exposure"]
    pal = " ".join(f"{c['hex']}({c['pct']}%)" for c in fp["palette"][:4])
    return (f"mean_lum={e['mean_lum']} p95={e['p95']} contraste={e['contrast_std']} "
            f"clipado={fp['clipped_pct']}% quase_preto={fp['near_black_pct']}% calor={fp['warmth']} "
            f"| paleta: {pal}")


def intern_synthesize(theme: dict, fp: dict, checks: list[dict], vis: dict) -> dict:
    """O estagiário (LLM local escopado ao tema) sintetiza taste+porquê+próxima ação a partir
    da TRADUÇÃO (números+visão+checks). Grounded: não 'vê' a imagem, lê os fatos traduzidos."""
    facts = "\n".join(f"- {c['label']}: {c['status']} ({c['detail']})" for c in checks)
    prompt = (
        f"Você é o ESTAGIÁRIO '{theme['intern']['id']}' — {theme['intern']['persona']} "
        f"Você SÓ cuida do tema {theme['id']}. DNA do tema: {theme['dna']}\n"
        f"ANTI-PATTERNS (reprovar se aparecerem): {'; '.join(theme['anti_patterns'])}\n\n"
        f"Um render foi TRADUZIDO pra você (você não vê imagem). Fatos objetivos:\n"
        f"FINGERPRINT: {_fp_summary(fp)}\n"
        f"VISÃO LOCAL: {json.dumps(vis, ensure_ascii=False)}\n"
        f"CHECKS DO TEMA:\n{facts}\n\n"
        "Com base SÓ nesses fatos, responda APENAS um JSON válido:\n"
        '{"verdict":"PASS|WARN|FAIL","felipe_taste_0a10":0,"why":"1-2 frases","next_action":'
        '"a UNICA acao de maior ROI pra melhorar no tema"}')
    raw = _ollama(theme["intern"]["model"], prompt)
    out = _extract_json(raw)
    if not out:  # fallback qwen formata o raciocínio do deepseek
        clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
        raw2 = _ollama("qwen2.5-coder:14b",
                       'Converta em UM JSON válido {"verdict","felipe_taste_0a10","why",'
                       f'"next_action"}}, nada fora:\n{clean[:1200]}', timeout=120)
        out = _extract_json(raw2)
    return out or {"verdict": "?", "why": "estagiário não devolveu JSON", "next_action": ""}


def validate(png_path: str | Path, theme_id: str, run_intern: bool = True,
             run_vision: bool = True) -> dict:
    """Valida UM render contra o schema de UM tema. Devolve o veredito estruturado."""
    theme = reg.load_theme(theme_id)
    fp = fingerprint(png_path)
    vis = {"ok": False, "answers": {}}
    if run_vision:
        vis = describe(png_path, reg.vision_questions(theme))
    answers = vis.get("answers", {})
    checks = [reg.eval_check(c, fp, answers) for c in theme["checks"]]
    overall = overall_status(checks)
    verdict = {
        "image": Path(png_path).name, "theme": theme["id"], "intern": theme["intern"]["id"],
        "overall": overall, "checks": checks,
        "fingerprint": {"exposure": fp["exposure"], "clipped_pct": fp["clipped_pct"],
                        "near_black_pct": fp["near_black_pct"], "warmth": fp["warmth"],
                        "palette": fp["palette"][:4]},
        "vision_ok": vis.get("ok", False),
    }
    if run_intern:
        verdict["synthesis"] = intern_synthesize(theme, fp, checks, answers)
    return verdict


def log_verdict(verdict: dict, ts: str) -> None:
    """Append no ledger por-tema (progresso render-a-render). ts vem de fora (sem clock na lógica)."""
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": ts, "image": verdict["image"], "theme": verdict["theme"],
           "overall": verdict["overall"],
           "checks": {c["id"]: c["status"] for c in verdict["checks"]},
           "taste": verdict.get("synthesis", {}).get("felipe_taste_0a10")}
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    import argparse
    import datetime
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--theme", default="black_wood_gold")
    ap.add_argument("--no-intern", action="store_true")
    ap.add_argument("--no-vision", action="store_true")
    ap.add_argument("--log", action="store_true", help="grava no ledger")
    a = ap.parse_args()
    v = validate(a.image, a.theme, run_intern=not a.no_intern, run_vision=not a.no_vision)
    print(json.dumps(v, ensure_ascii=False, indent=2))
    if a.log:
        log_verdict(v, datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))
        print(f"[ledger] -> {LEDGER}")
    sys.exit(0 if v["overall"] in ("PASS", "WARN") else 1)
