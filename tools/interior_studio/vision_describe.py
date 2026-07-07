"""vision_describe.py — a metade SEMÂNTICA da tradução render->texto: pergunta ao modelo de
VISÃO local (qwen2.5vl) só o que o fingerprint determinístico NÃO captura (estouro perceptual,
fake-gold, hierarquia de material, "parece caverna"). Devolve respostas ESTRUTURADAS.

Por que visão local e não GPT: o estagiário roda offline/barato; o GPT/Felipe continuam sendo
o gate FINAL. Isto é o checkpoint local que faltava (o agente de texto não vê imagem sozinho).
As perguntas vêm do SCHEMA DO TEMA (theme_registry) — cada tema pergunta o que importa pra ele.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.request
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434/api/generate"
VISION_MODEL = "qwen2.5vl:7b"


def _extract_json(txt: str) -> dict | None:
    txt = re.sub(r"```(?:json)?", "", txt)
    i, j = txt.find("{"), txt.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(txt[i:j + 1])
    except Exception:  # noqa: BLE001
        return None


def describe(png_path: str | Path, questions: list[dict], model: str = VISION_MODEL,
             timeout: int = 200) -> dict:
    """questions = [{"key","q"[,"type"]}]. Devolve {"answers":{key:val}, "ok":bool, "model","raw"}.
    type ∈ {bool,str,scale} só orienta o prompt; a validação real é do estagiário."""
    p = Path(png_path)
    if not p.exists():
        return {"ok": False, "error": f"imagem ausente: {p}", "answers": {}}
    b64 = base64.b64encode(p.read_bytes()).decode()
    # placeholder de string fora da f-string: backslash dentro da expressão é
    # SyntaxError no py3.11 (só virou legal no 3.12/PEP 701).
    _str_ph = '"..."'
    schema = ", ".join(
        f'"{x["key"]}": {"true/false" if x.get("type") == "bool" else "0-10" if x.get("type") == "scale" else _str_ph}'
        for x in questions)
    qlist = "\n".join(f'- {x["key"]}: {x["q"]}' for x in questions)
    prompt = ("Você é um AUDITOR DE RENDER de interiores. Olhe a imagem e responda com OBJETIVIDADE, "
              "sem elogiar. Responda SÓ um JSON válido, nada fora dele, no formato:\n"
              f"{{{schema}}}\n\nPerguntas:\n{qlist}")
    body = json.dumps({"model": model, "prompt": prompt, "images": [b64], "stream": False,
                       "options": {"temperature": 0.1, "num_predict": 700}}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    try:
        raw = json.loads(urllib.request.urlopen(req, timeout=timeout).read()).get("response", "")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"visão local falhou: {e}", "answers": {}, "model": model}
    parsed = _extract_json(raw)
    if parsed is None:
        return {"ok": False, "error": "JSON não parseado", "answers": {}, "raw": raw[:400], "model": model}
    return {"ok": True, "answers": parsed, "model": model, "raw": raw[:400]}


if __name__ == "__main__":
    import sys
    qs = [{"key": "blowout", "q": "Há objeto branco ESTOURADO (sem detalhe)?", "type": "bool"},
          {"key": "wall_color", "q": "Cor da parede em 1-2 palavras?", "type": "str"},
          {"key": "metals", "q": "Os metais são bronze/dourado QUENTE ou prata FRIO?", "type": "str"},
          {"key": "cave", "q": "Parece caverna (escuro demais, perde o ambiente)?", "type": "bool"},
          {"key": "score", "q": "Nota 0-10 de quão premium/bem-resolvido está.", "type": "scale"}]
    print(json.dumps(describe(sys.argv[1], qs), ensure_ascii=False, indent=2))
