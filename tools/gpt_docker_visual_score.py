"""gpt_docker_visual_score.py — backbone do loop visual autônomo (nota-pro-10).

Papel do Claude / gate (diretriz do Felipe, 2026-07-11):
  1. PUBLICA o render no GitHub e CONFIRMA que subiu (raw URL == 200) — sem link o
     GPT é cego, não vê a imagem;
  2. manda o link pro GPT-no-Docker (:8899), que faz a VALIDAÇÃO VISUAL e devolve
     NOTA (0-10) + se o 10 é factível + o PORQUÊ + o CAMINHO PRO 10 (ensino).
O Claude NUNCA autodeclara o veredito visual — só transporta. Quem decide a imagem
é o GPT. O determinístico (publicar, confirmar 200, parsear) é do Claude.

Idempotente: se o render já está no `origin/<branch>` com o mesmo conteúdo, só
verifica a URL; não recommita.

Uso:
    python -m tools.gpt_docker_visual_score --render <path.png> [--branch develop]
        [--bridge-url http://127.0.0.1:8899] [--timeout 200] [--json]

Saída: struct {nota:int|None, factivel_10, porque, caminho_pro_10, url, raw_answer}.
Exit code 0 se conseguiu uma nota; 2 se IMAGE_NOT_VIEWED / sem nota; 3 em erro de
publicação (não perguntou ao GPT porque a imagem não estava visível).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BRIDGE_URL = "http://127.0.0.1:8899"
RAW_HOST = "https://raw.githubusercontent.com"


# ---- git helpers -----------------------------------------------------


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True, text=True,
    )


def _remote_slug() -> str:
    """`https://github.com/GFCDOTA/sketchup-mcp.git` -> `GFCDOTA/sketchup-mcp`."""
    url = _git("remote", "get-url", "origin").stdout.strip()
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if not m:
        raise RuntimeError(f"cannot parse GitHub slug from origin url {url!r}")
    return m.group(1)


def _rel_posix(render: Path) -> str:
    return render.resolve().relative_to(REPO_ROOT).as_posix()


def _url_status(url: str, timeout: int = 10) -> int:
    """HEAD-ish GET; return HTTP status (0 on network error)."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


def ensure_published(render: Path, branch: str) -> str:
    """Guarantee the render is on `origin/<branch>` and reachable at its raw URL.

    Idempotent: if the committed blob on `origin/<branch>` already equals the local
    file, no commit happens. Otherwise: add + commit + push the render to `<branch>`.
    Returns the verified raw URL. Raises if it cannot make the URL return 200.
    """
    render = render.resolve()
    if not render.exists():
        raise FileNotFoundError(f"render not found: {render}")
    rel = _rel_posix(render)
    slug = _remote_slug()
    raw_url = f"{RAW_HOST}/{slug}/{branch}/{rel}"

    local_sha = _git("hash-object", str(render)).stdout.strip()
    remote_sha = _git("rev-parse", f"origin/{branch}:{rel}").stdout.strip()

    if local_sha and local_sha == remote_sha and _url_status(raw_url) == 200:
        return raw_url

    # Not present / stale on origin/<branch> — publish it there.
    add = _git("add", "--", str(render))
    if add.returncode != 0:
        raise RuntimeError(f"git add failed: {add.stderr.strip()}")
    # Commit only if there is something staged (avoid empty-commit failure).
    if _git("diff", "--cached", "--quiet", "--", str(render)).returncode != 0:
        commit = _git(
            "commit", "-m",
            f"chore(evidence): publish {render.name} for GPT visual score",
            "--", str(render),
        )
        if commit.returncode != 0:
            raise RuntimeError(f"git commit failed: {commit.stderr.strip()}")
    push = _git("push", "origin", f"HEAD:{branch}")
    if push.returncode != 0:
        raise RuntimeError(f"git push to {branch} failed: {push.stderr.strip()}")

    if _url_status(raw_url) != 200:
        raise RuntimeError(
            f"render pushed but raw URL not reachable (repo private? branch wrong?): "
            f"{raw_url}"
        )
    return raw_url


# ---- GPT-no-Docker visual call ---------------------------------------


_PROMPT_TEMPLATE = (
    "Você é um crítico sênior de design de interiores e arquitetura, olho duro. "
    "Abra e OLHE de verdade esta imagem de um ambiente renderizado: {url} . "
    "Se NÃO conseguir abrir/ver a imagem, responda EXATAMENTE 'IMAGE_NOT_VIEWED' e "
    "nada mais — não invente o que não viu.\n\n"
    "Depois de olhar, responda em texto NESTE formato, começando pela primeira linha:\n"
    "NOTA: <inteiro de 0 a 10>/10\n"
    "FACTIVEL_10: <sim|nao> — <qual o teto realista de nota pra este ambiente e por quê>\n"
    "PORQUE: <crítica específica: iluminação/exposição, proporção e escala dos móveis, "
    "paleta e materiais, composição e parede, circulação, styling — não aceite 'parece ok'>\n"
    "CAMINHO_PRO_10: <passos em ordem de prioridade, do que mais sobe a nota pro que é "
    "só polimento; ENSINE o como, não só o quê>\n\n"
    "Seja honesto e direto: se estiver ruim, diga que está ruim e por quê."
)


@dataclass
class VisualScore:
    url: str
    nota: int | None
    factivel_10: str
    porque: str
    caminho_pro_10: str
    image_viewed: bool
    raw_answer: str


def _post_ask(bridge_url: str, prompt: str, timeout_s: int) -> dict:
    payload = json.dumps({"prompt": prompt, "timeout_s": timeout_s}).encode("utf-8")
    req = urllib.request.Request(
        f"{bridge_url.rstrip('/')}/ask",
        data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s + 30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _section(answer: str, label: str) -> str:
    """Grab text after `LABEL:` up to the next known label or end."""
    labels = ["NOTA", "FACTIVEL_10", "PORQUE", "CAMINHO_PRO_10"]
    others = "|".join(l for l in labels if l != label)
    m = re.search(
        rf"{label}\s*:\s*(.*?)(?=\n\s*(?:{others})\s*:|\Z)",
        answer, re.IGNORECASE | re.DOTALL,
    )
    return m.group(1).strip() if m else ""


def parse_visual_answer(url: str, answer: str) -> VisualScore:
    """Pure parse of the GPT answer into a VisualScore (no I/O — testable).

    `IMAGE_NOT_VIEWED` anywhere in the answer means the GPT could not see the image:
    nota=None, image_viewed=False (never fabricate a verdict from a blind model)."""
    answer = (answer or "").strip()
    if "IMAGE_NOT_VIEWED" in answer:
        return VisualScore(url, None, "", "", "", False, answer)
    nota_m = re.search(r"NOTA\s*:?\s*(\d{1,2})\s*/\s*10", answer, re.IGNORECASE)
    nota = int(nota_m.group(1)) if nota_m else None
    return VisualScore(
        url=url,
        nota=nota,
        factivel_10=_section(answer, "FACTIVEL_10"),
        porque=_section(answer, "PORQUE"),
        caminho_pro_10=_section(answer, "CAMINHO_PRO_10"),
        image_viewed=True,
        raw_answer=answer,
    )


def score_render(
    render: Path, *, branch: str = "develop",
    bridge_url: str = DEFAULT_BRIDGE_URL, timeout_s: int = 200,
) -> VisualScore:
    """Publish → confirm → ask the Docker GPT → parse. The visual verdict is the
    GPT's; this function only transports and parses it."""
    url = ensure_published(render, branch)
    resp = _post_ask(bridge_url, _PROMPT_TEMPLATE.format(url=url), timeout_s)
    answer = resp.get("answer") or resp.get("response") or ""
    return parse_visual_answer(url, answer)


# ---- cli -------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--render", required=True, help="path to the render PNG (repo-relative or absolute)")
    ap.add_argument("--branch", default="develop", help="branch to publish/verify on (default: develop)")
    ap.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    ap.add_argument("--timeout", type=int, default=200, help="GPT answer timeout (s)")
    ap.add_argument("--json", action="store_true", help="emit JSON only")
    args = ap.parse_args(argv)

    render = Path(args.render)
    if not render.is_absolute():
        render = (REPO_ROOT / render)

    try:
        score = score_render(
            render, branch=args.branch,
            bridge_url=args.bridge_url, timeout_s=args.timeout,
        )
    except (RuntimeError, FileNotFoundError) as e:
        print(f"[publish-error] {e}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(asdict(score), ensure_ascii=False, indent=2))
    else:
        if not score.image_viewed:
            print(f"IMAGE_NOT_VIEWED — GPT não conseguiu abrir {score.url}")
        else:
            print(f"URL:   {score.url}")
            print(f"NOTA:  {score.nota}/10" if score.nota is not None else "NOTA:  (não parseada)")
            print(f"FACTÍVEL_10: {score.factivel_10}\n")
            print(f"PORQUÊ:\n{score.porque}\n")
            print(f"CAMINHO PRO 10:\n{score.caminho_pro_10}")

    return 0 if (score.image_viewed and score.nota is not None) else 2


if __name__ == "__main__":
    raise SystemExit(main())
