"""taste_writeback.py — commit 8: fecha o WRITE-BACK do gosto no RAG.

O veredito humano de curadoria (human_verdicts.jsonl, escrito SO pelo clique do
Felipe na tela de curadoria do :8782) e' hoje um log solto que o RAG NUNCA ve —
o "buraco central". Este modulo MATERIALIZA cada veredito CURADO num
`rag_writeback_record.v1` duravel sob `references/felipe/verdicts/<id>.json`, um
source registrado no `rag_freshness.SOURCES`. A partir dai o gosto do Felipe
entra no `corpus_version`, e' chunkado, embedado e fica RECUPERAVEL pelo
`reference_db.retrieve()`. Aprendizado = write-back recuperavel, NAO log solto.

Honestidade (regra dura): `human_verdict` / `liked` / `felipe_comment` /
`positive_patterns` / `negative_patterns` vem SO do humano. positive/negative
sao derivados APENAS das tags + comentario do Felipe, com a POLARIDADE dada pelo
sinal de gosto `liked` (thumbs) — NUNCA de `design_patterns_observed` da maquina.
A maquina so TRANSPORTA o veredito; nunca o fabrica (o vocabulario e' VALIDADO,
importado de tools.human_verdict, nao emitido — membership test nao fabrica).

So verdict CURADO materializa: o `human_verdicts.jsonl` scratch inteiro (mistura
vocabulario da maquina / linhas sem galeria / TTL) NAO entra — `drain_new_verdicts`
casa cada linha com a galeria e filtra o vocabulario humano estrito.

Idempotente por id + por CONTEUDO: re-materializar o mesmo veredito produz o mesmo
arquivo e NAO reescreve bytes iguais (nao bumpa mtime -> o freshness nao vira stale
a toa). Determinístico: sem clock/random; `created_at` vem do timestamp humano do
clique (`t` da curadoria), com fallback pro `created_at` mtime-derivado da galeria.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from tools import rag_freshness as rf
from tools.human_verdict import is_human_verdict, is_liked, normalize_tags
from tools.jsonl_io import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
VERDICTS_DIR = ROOT / "references" / "felipe" / "verdicts"
WRITEBACK_SCHEMA = "rag_writeback_record/1.0.0"

_ID_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_id(raw: str) -> str:
    """id de arquivo estavel e seguro (idempotente): colapsa tudo fora de
    [A-Za-z0-9._-] em '_'. variant_id ja e' desse alfabeto; a sanitizacao e'
    defesa contra ids exoticos."""
    return _ID_UNSAFE.sub("_", str(raw)).strip("_") or "verdict"


def _first(*vals):
    """primeiro valor 'presente' (nao None / nao string vazia)."""
    for v in vals:
        if v not in (None, ""):
            return v
    return None


# ---------------------------------------------------------------------------
# extracao defensiva dos campos da GALERIA (corpus_rec) — o registro pode ser um
# item de variante de planta inteira (variant_sweep) ou uma galeria per-comodo.
# Puxa room/room_type/style/skp/render de onde existir; ausente -> "" honesto
# (o schema exige string, nao proibe vazio — nada e' inventado).
# ---------------------------------------------------------------------------
def _room_id(rec: dict) -> str:
    params = rec.get("params") or {}
    return str(_first(rec.get("room_id"), rec.get("room"), params.get("room"),
                      rec.get("plant")) or "")


def _room_type(rec: dict) -> str:
    params = rec.get("params") or {}
    return str(_first(rec.get("room_type"), params.get("room_type")) or "")


def _style_profile(rec: dict) -> str:
    params = rec.get("params") or {}
    return str(_first(rec.get("style_profile"), params.get("style"),
                      params.get("theme")) or "")


def _image_path(rec: dict) -> str:
    render = rec.get("render_refs") or {}
    return str(_first(rec.get("image_path"), render.get("iso")) or "")


def _skp_path(rec: dict) -> str:
    render = rec.get("render_refs") or {}
    return str(_first(rec.get("skp_path"), rec.get("linked_skp"),
                      render.get("skp")) or "")


def _split_patterns(liked, tags: list[str], comment: str) -> tuple[list[str], list[str]]:
    """positive/negative_patterns SO do humano. A fonte e' o territorio humano
    (tags + comentario); a POLARIDADE vem do sinal de gosto `liked` (thumbs),
    ORTOGONAL ao veredito de regressao (o Felipe pode gostar de um SAME ou
    desgostar de um IMPROVED — polaridade de GOSTO != verdict de regressao):
      liked True  -> aprender COMO positivo (queremos mais disto)
      liked False -> aprender COMO negativo (evitar)
      liked None  -> nao sinalizado: NAO fabrica polaridade (as tags/comentario
                     seguem no campo `tags`/`felipe_comment`, recuperaveis, mas
                     sem inventar se e' bom ou ruim).
    NUNCA usa design_patterns_observed / achados da maquina."""
    human = [t for t in tags if t]
    if comment:
        human.append(comment)
    if liked is True:
        return human, []
    if liked is False:
        return [], human
    return [], []


def materialize(curadoria_verdict: dict, corpus_rec: dict, con,
                *, verdicts_dir: Path | None = None) -> Path:
    """Um veredito CURADO (`curadoria_verdict.v1`) + o registro da galeria
    correspondente -> um `rag_writeback_record.v1` durável em
    `references/felipe/verdicts/<id>.json`, carimbado com o `corpus_version`
    ATUAL (`rag_freshness.current_corpus_version(con)`) no momento do write.

    Idempotente por id (o arquivo e' `<asset_id>.json`) e por CONTEUDO (nao
    reescreve bytes iguais). Levanta ValueError se `human_verdict` estiver fora do
    vocabulario humano (IMPROVED|SAME|WORSE) — so verdict CURADO materializa; a
    maquina VALIDA a leitura, nao fabrica veredito."""
    hv = curadoria_verdict.get("human_verdict")
    if not is_human_verdict(hv):
        raise ValueError(
            f"human_verdict {hv!r} fora do vocabulario humano — so verdict CURADO "
            "materializa (o human_verdicts.jsonl scratch nao entra inteiro)")

    liked = curadoria_verdict.get("liked")
    if not is_liked(liked):
        liked = None
    tags = normalize_tags(curadoria_verdict.get("tags"))
    comment = str(curadoria_verdict.get("note") or "")
    positive, negative = _split_patterns(liked, tags, comment)

    asset_id = str(_first(curadoria_verdict.get("variant_id"),
                          corpus_rec.get("variant_id"),
                          corpus_rec.get("asset_id")) or "")
    if not asset_id:
        raise ValueError("veredito sem asset_id/variant_id — nada a materializar")

    image_path = _image_path(corpus_rec)
    skp_path = _skp_path(corpus_rec)
    record = {
        "schema": WRITEBACK_SCHEMA,
        "asset_id": asset_id,
        "run_id": str(corpus_rec.get("run_id") or ""),
        # cycle_id = o LOTE de curadoria a que o clique pertence (batch_id).
        "cycle_id": str(curadoria_verdict.get("batch_id") or ""),
        "room_id": _room_id(corpus_rec),
        "room_type": _room_type(corpus_rec),
        "style_profile": _style_profile(corpus_rec),
        "image_path": image_path,
        "skp_path": skp_path,
        "human_verdict": hv,                       # TRANSPORTADO (Felipe emitiu)
        "liked": liked,                            # thumbs do Felipe (bool|null)
        "felipe_comment": comment,                 # comentario cru do Felipe
        "tags": tags,                              # tags cruas do Felipe
        "positive_patterns": positive,             # SO do humano (polaridade=liked)
        "negative_patterns": negative,             # SO do humano (polaridade=liked)
        "evidence": [e for e in (image_path, skp_path) if e],
        "corpus_version": rf.current_corpus_version(con) or "",
        # created_at deterministico: o instante do clique humano (nao wall-clock).
        "created_at": str(_first(curadoria_verdict.get("t"),
                                 corpus_rec.get("created_at")) or ""),
    }

    vdir = Path(verdicts_dir) if verdicts_dir is not None else VERDICTS_DIR
    vdir.mkdir(parents=True, exist_ok=True)
    out = vdir / f"{_safe_id(asset_id)}.json"
    payload = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    # idempotente por conteudo: so escreve se mudou (nao bumpa mtime a toa ->
    # o freshness_guard nao marca stale sem a fonte ter de fato mudado).
    if not (out.is_file() and out.read_text(encoding="utf-8") == payload):
        out.write_text(payload, encoding="utf-8")
    return out


def drain_new_verdicts(corpus_path: Path, con, *, verdicts_dir: Path | None = None,
                       human_verdicts_path: Path | None = None) -> int:
    """Varre o `human_verdicts.jsonl` (ao lado do corpus, ou explicito), casa cada
    linha com o registro da GALERIA (`corpus.jsonl`, last-wins por variant_id) e
    MATERIALIZA os verdicts CURADOS ainda nao gravados. Filtra estrito:
      - so vocabulario humano (IMPROVED|SAME|WORSE) — linha da maquina e' pulada;
      - so com match na galeria — veredito de variante inexistente e' pulado;
    (o scratch inteiro NUNCA entra). last-wins por variant_id: o ULTIMO clique
    vence. Idempotente: verdict ja materializado com o mesmo conteudo nao reconta.
    Retorna quantos NOVOS arquivos de verdict foram criados."""
    corpus_path = Path(corpus_path)
    hv_path = (Path(human_verdicts_path) if human_verdicts_path is not None
               else corpus_path.parent / "human_verdicts.jsonl")
    vdir = Path(verdicts_dir) if verdicts_dir is not None else VERDICTS_DIR

    gallery = {r.get("variant_id"): r for r in read_jsonl(corpus_path)}  # last-wins
    latest: dict[str, dict] = {}
    for rec in read_jsonl(hv_path):
        vid = rec.get("variant_id")
        if vid and is_human_verdict(rec.get("human_verdict")):
            latest[vid] = rec  # last-wins por variant_id

    created = 0
    for vid in sorted(latest):                     # ordem estavel (determinismo)
        corpus_rec = gallery.get(vid)
        if corpus_rec is None:
            continue                               # sem galeria -> nao materializa
        out = vdir / f"{_safe_id(vid)}.json"
        existed = out.is_file()
        materialize(latest[vid], corpus_rec, con, verdicts_dir=vdir)
        if not existed:
            created += 1
    return created
