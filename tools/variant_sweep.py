"""variant_sweep.py — FP-034: PLACAR DE VARIANTES JULGADAS da planta inteira.

Eleva o padrao provado do sofa_class_matrix (derive -> gate -> render SU-free ->
grid -> report) de movel para planta: expande um produto cartesiano controlado
de eixos (tools/variant_axes), roda o furnish por celula (collect_boxes, SEM
SketchUp), passa gates deterministicos HERMETICOS ANTES do render, renderiza o
iso barato (render_parts_iso), coleta achados visuais honestos (FP-032) e grava
um registro `judged_variant/1.0.0` por linha em corpus.jsonl (append-only,
idempotente por variant_id) + contact_sheet.png (_grid_sheet reusado).

Honestidade (contratos herdados de FP-032/033):
- verdicts da MAQUINA: CANDIDATE | FAIL | PENDING_VISION. Gate deterministico
  FAIL -> verdict=FAIL SEMPRE (nunca CANDIDATE). Sem achados visuais ->
  PENDING_VISION, visual_findings=null — NUNCA fabrica.
- `human_verdict` nasce null e SO o Felipe preenche; `machine_score` e' sempre
  rotulado machine_provisional.
- achados em DOIS modos: sidecar visual_findings.json ao lado do render (FP-032
  externo) OU chamada real opt-in ao provider claude_bridge_vision (--ask-vision)
  com a regra "FAIL so se DISCRIMINATED" (degradacao do vision_queue_consumer).

Uso:
    PT_TO_M=0.0259 python -m tools.variant_sweep --n 4 --out runs/variant_sweep/s0 --dry-run
    python -m tools.variant_sweep --ask-vision --only <variant_id> --out <run>
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import itertools
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Escala ANTES de QUALQUER import de projeto: core.scale congela PT_TO_M no 1o
# import do processo; sem isso o placement cai no default 0.0352 e a mobilia
# flutua ~1.36x fora do shell 0.0259 (gotcha real da planta_74). O
# tools.furnish_apartment self-defaulta tambem, mas o setdefault aqui garante o
# valor mesmo se a cadeia de imports mudar.
os.environ.setdefault("PT_TO_M", "0.0259")
from core import scale  # noqa: E402
from tools.furnish_apartment import CONSENSUS, collect_boxes  # noqa: E402
from tools.jsonl_io import append_jsonl, read_jsonl  # noqa: E402
from tools.variant_axes import Variant, default_axes  # noqa: E402

SCHEMA_ID = "judged_variant/1.0.0"
MACHINE_LABEL = "machine_provisional"
BACKEND = "claude_bridge_vision"  # nome de provider/backend (source = claude_bridge)


def expand_axes(axes: dict | None = None, n: int | None = None,
                plant: str = "planta_74") -> list[Variant]:
    """Grid deterministico e ordenado (style, theme, layout). n = prefixo
    (n=0 => 0 celulas; None => grid inteiro). Guarda de unicidade: variant_id
    usa 'baseline'/'warm_compact' como default legivel — um token literal igual
    ao default colidiria e o sweep pularia a celula em silencio (dedup por id)."""
    ax = axes or default_axes()
    cells = [Variant(plant=plant, style=s, theme=t, layout_seed=ls)
             for s, t, ls in itertools.product(ax["style"], ax["theme"], ax["layout"])]
    counts = Counter(c.variant_id for c in cells)
    dupes = sorted(vid for vid, k in counts.items() if k > 1)
    if dupes:
        raise ValueError(
            "variant_id colidiu — token literal igual ao default do id (ex. theme "
            f"'warm_compact' vs '' ou style 'baseline' vs None): {dupes}")
    return cells[:n] if n is not None else cells


def _require_plant_scale(plant: str) -> None:
    """Guard honesto contra o gotcha de import-order: planta com escala
    verificada (core.scale.PLANT_PT_TO_M) exige o processo congelado nela."""
    expected = scale.PLANT_PT_TO_M.get(plant)
    if expected is not None and abs(scale.PT_TO_M - expected) > 1e-9:
        raise RuntimeError(
            f"PT_TO_M congelado em {scale.PT_TO_M:g} != {expected:g} (escala "
            f"verificada de {plant}); rode num processo com PT_TO_M={expected} "
            f"setado ANTES de qualquer import de core.scale (movel flutua 1.36x)")


# ── gates deterministicos HERMETICOS (sobre os boxes REAIS da variante) ─────
# overlap_gate/sanity_room RE-RODAM os brains a partir do consensus — variante
# com boxes mutados seria invisivel pra eles (validariam o baseline, prova
# falsa). Aqui: geometry_sanity.audit (box-accepting) + pairwise_overlap
# canonico do furniture_overlap_gate + outside_room via audit(rooms=) com os
# poligonos PRE-bufferizados em OUTSIDE_BUFFER_IN (o check cru tem tolerancia
# zero e reprova pe' de cama encostado na parede do proprio baseline golden).


def _audit_boxes(boxes: list[dict]) -> dict:
    """geometry_sanity.audit sem o check off_axis: rotacao livre de mobilia e'
    design APROVADO (track intent-to-scene); off_axis pega bug de builder
    axis-aligned, nao composicao rotacionada. Filtragem documentada, nao muda o
    audit pinado pelos testes dele."""
    from tools.geometry_sanity import audit
    g = audit(boxes, to_m=0.0254)
    findings = [f for f in g["findings"] if f["check"] != "off_axis"]
    n_fail = sum(1 for f in findings if f["severity"] == "FAIL")
    n_warn = sum(1 for f in findings if f["severity"] == "WARN")
    return {"overall": "FAIL" if n_fail else ("WARN" if n_warn else "PASS"),
            "n_fail": n_fail, "n_warn": n_warn, "findings": findings}


def _outside_room(boxes: list[dict], con: dict) -> dict:
    """Centro do box fora de TODOS os comodos (buffer OUTSIDE_BUFFER_IN) -> FAIL.
    Reusa o check canonico outside_room do geometry_sanity.audit (rooms= aceita
    os poligonos JA bufferizados) em vez de uma 3a implementacao ponto-em-
    poligono; o buffer vem da fonte unica (paridade sanity_room)."""
    from shapely.geometry import Polygon

    from tools.geometry_sanity import OUTSIDE_BUFFER_IN, audit
    polys = [list(Polygon([(x * scale.PT_TO_IN, y * scale.PT_TO_IN)
                           for x, y in r["polygon_pts"]])
                  .buffer(OUTSIDE_BUFFER_IN).exterior.coords)
             for r in con.get("rooms", []) if r.get("polygon_pts")]
    if not polys:
        return {"result": "PASS", "fails": []}
    g = audit(boxes, rooms=polys, to_m=0.0254)
    fails = [f"{f.get('label') or f.get('kind')}: {f['detail']}"
             for f in g["findings"] if f["check"] == "outside_room"]
    return {"result": "FAIL" if fails else "PASS", "fails": fails}


def _overlap_pairwise(boxes: list[dict]) -> dict:
    """Colisao movel-sobre-movel por comodo, direto nos boxes da variante, via
    o loop pairwise CANONICO do gate (furniture_overlap_gate.pairwise_overlap —
    o overlap_gate original re-roda brains e nao aceita boxes; o veredito de
    colisao, thresholds inclusos, tem fonte unica la')."""
    from tools.furniture_overlap_gate import _module_geom, pairwise_overlap
    per_room: dict[str, list[dict]] = {}
    for b in boxes:
        per_room.setdefault(str(b.get("room", "")), []).append(b)
    fails, warns = [], []
    n_modules = 0
    for room, rboxes in sorted(per_room.items()):
        f, w, n = pairwise_overlap(_module_geom(rboxes))
        n_modules += n
        fails += [f"{room}: {m}" for m in f]
        warns += [f"{room}: {m}" for m in w]
    result = "FAIL" if fails else ("WARN" if warns else "PASS")
    return {"result": result, "n_modules": n_modules, "fails": fails, "warns": warns}


def run_deterministic_gates(boxes: list[dict], con: dict) -> tuple[dict, dict]:
    """(verdicts {gate: PASS|WARN|FAIL}, detail) — ANTES do render, sempre."""
    g_geo = _audit_boxes(boxes)
    g_out = _outside_room(boxes, con)
    g_ov = _overlap_pairwise(boxes)
    verdicts = {"geometry_sanity": g_geo["overall"],
                "outside_room": g_out["result"],
                "furniture_overlap": g_ov["result"]}
    detail = {"geometry_sanity": {"n_fail": g_geo["n_fail"], "n_warn": g_geo["n_warn"],
                                  "findings": g_geo["findings"][:12]},
              "outside_room": g_out["fails"],
              "furniture_overlap": {"fails": g_ov["fails"], "warns": g_ov["warns"]}}
    return verdicts, detail


# ── geometria da variante ────────────────────────────────────────────────────


def _apply_layout_seed(con: dict, boxes: list[dict], seed: int) -> tuple[list[dict], str]:
    """seed 0 = brain default. seed k>=1 = substitui os boxes do living pelos
    placeholders do k-esimo template VALIDO do layout_candidates (ranking
    deterministico; modulo sobre len(valid) — seeds podem colidir se houver
    menos candidatos validos que seeds, ids continuam distintos)."""
    if seed <= 0:
        return boxes, "brain_default"
    from tools.layout_candidates import run as lc_run
    from tools.place_layout_skp import build_boxes as template_boxes
    from tools.room_type import LIVING, classify_rooms
    living = next((r for r in classify_rooms(con) if r["room_type"] == LIVING), None)
    if living is None:
        return boxes, "brain_default(no_living)"
    _, out = lc_run(con, living["id"])
    valid = [c for c in out.get("candidates", []) if c.get("valid")]
    if not valid:
        return boxes, "brain_default(no_valid_candidate)"
    template = valid[(seed - 1) % len(valid)]["template"]
    lb, _ = template_boxes(con, living["id"], template)
    if not lb:
        return boxes, "brain_default(template_failed)"
    room_name = str(living.get("name") or living["id"])
    for b in lb:
        b["room"] = room_name
        b.setdefault("module", str(b.get("kind", "movel")))
    style = os.environ.get("FURNISH_STYLE")
    if style:  # paridade com collect_boxes: a camada de estilo cobre o living trocado
        from tools.style_spec import apply_style, attach_materials
        apply_style(lb, style)
        attach_materials(lb, style)
    kept = [b for b in boxes if str(b.get("room")) != room_name]
    return kept + lb, f"template:{template}"


def _boxes_to_parts(boxes: list[dict]) -> list[dict]:
    """Box de planta (polegadas, corners com rotacao) -> part do render_parts.
    verts8 vem dos corners REAIS (AABB de corners rotacionados inflaria a
    footprint); x0..z1 ficam como extents pro enquadramento."""
    parts = []
    for b in boxes:
        z0 = float(b.get("z0_in", 0.0))
        z1 = z0 + float(b.get("h_in", 0.0))
        p = {"x0": float(b["x0"]), "y0": float(b["y0"]), "z0": z0,
             "x1": float(b["x1"]), "y1": float(b["y1"]), "z1": z1,
             "rgb": list(b.get("rgb") or [120, 120, 120])}
        cs = b.get("corners")
        if cs and len(cs) == 4:
            p["verts8"] = ([(float(x), float(y), z0) for x, y in cs]
                           + [(float(x), float(y), z1) for x, y in cs])
        parts.append(p)
    return parts


# ── achados visuais (FP-032) — DOIS modos honestos, nunca fabrica ────────────


def _collect_findings(png: Path, *, plant: str, provider=None,
                      discrimination=None) -> dict | None:
    """Modo 1: sidecar visual_findings.json ao lado do render (FP-032 externo);
    so vale se for visual_findings.v1 — sidecar ilegivel/nao-conforme conta como
    AUSENTE (logado) e NAO sombreia o provider.
    Modo 2: provider claude_bridge_vision injetado (opt-in --ask-vision), com a
    regra FAIL-so-se-DISCRIMINATED (degradacao REUSADA do vision_queue_consumer).
    Sem nenhum dos dois / bridge fora -> None (PENDING_VISION honesto)."""
    png = Path(png)
    sidecar = png.with_name("visual_findings.json")
    if sidecar.is_file():
        vf = None
        try:
            vf = json.loads(sidecar.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        if isinstance(vf, dict) and vf.get("schema_version") == "visual_findings.v1":
            vf.setdefault("fixture", plant)   # required no schema v1; o detector
            vf.setdefault("attempt", "variant")  # externo nem sempre preenche
            return vf
        print(f"[variant-sweep] sidecar ilegivel/nao-conforme IGNORADO "
              f"(cai pro provider, se houver): {sidecar}", file=sys.stderr)
    if provider is None:
        return None
    ok, _reason = provider.probe()
    if not ok:
        return None
    from tools.oracle_providers import OracleRequest
    req = OracleRequest(
        prompt=(f"Judge this furnished-variant render of {plant!r}: report what "
                "you SEE as visual_findings.v1; never invent a defect that is "
                "not visible."),
        image_paths=[png],
        context={"fixture": plant,
                 "pending": [f"variant render {png.parent.name}: julgar "
                             "geometria/mobilia visivel neste iso SU-free"]},
        expected_schema={"schema_version": "visual_findings.v1"},
    )
    resp = provider.call(req, out_dir=png.parent)
    if resp.status != "ok":
        return None  # negativo honesto; package de request ja escrito pelo provider
    vf = dict(resp.normalized_findings or {})
    if discrimination is not None:
        report = discrimination()
    else:
        from tools.run_skp_visual_review import load_latest_discrimination
        report = load_latest_discrimination(plant, BACKEND)
    discriminated = bool(report and report.get("result") == "DISCRIMINATED")
    from tools.vision_queue_consumer import _degrade_unproven
    vf = _degrade_unproven(vf, discriminated)
    vf["fixture"] = plant
    vf["attempt"] = "variant"
    vf["discriminated"] = discriminated
    return vf


# ── registro julgado ─────────────────────────────────────────────────────────


def _machine_score(gates: dict, findings: dict | None) -> float | None:
    """Score provisional SO quando ha achados visuais (senao null — so gates
    nao viram nota). top_level_verdict desconhecido/ausente = achado nao-
    conforme -> None (nunca fabrica nota de um verdict que nao existe).
    Deterministico, rotulado machine_provisional sempre."""
    if findings is None:
        return None
    score = {"PASS": 1.0, "WARN": 0.6, "FAIL": 0.0}.get(
        findings.get("top_level_verdict"))
    if score is None:
        return None
    for v in gates.values():
        if v == "WARN":
            score -= 0.1
        elif v == "FAIL":
            score -= 0.5
    return round(max(0.0, min(1.0, score)), 2)


def _mtime_iso(p: Path) -> str:
    # deterministico (mtime do artefato, nunca clock atual) — idempotente
    return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def build_record(v: Variant, *, run_id: str, gates: dict, gate_detail: dict | None = None,
                 summary: list | None = None, n_boxes: int = 0, png: Path | None = None,
                 renderer: str = "su-free", findings: dict | None = None,
                 layout_source: str = "brain_default", out_root: Path | None = None) -> dict:
    gate_fail = any(g == "FAIL" for g in gates.values())
    if gate_fail:
        verdict = "FAIL"  # gate deterministico FAIL manda SEMPRE (nunca CANDIDATE)
    elif findings is None:
        verdict = "PENDING_VISION"
    elif findings.get("top_level_verdict") == "FAIL":
        verdict = "FAIL"
    else:
        verdict = "CANDIDATE"
    if png is not None:
        png = Path(png)
        created = _mtime_iso(png)
        sha = hashlib.sha256(png.read_bytes()).hexdigest()
        iso_rel = png.as_posix()
        if out_root is not None:
            try:
                iso_rel = png.resolve().relative_to(Path(out_root).resolve()).as_posix()
            except ValueError:
                pass
    else:  # abort antes do render (ex. gate da cozinha): sem pixel, sem sha
        created, sha, iso_rel = _mtime_iso(Path(CONSENSUS)), None, None
    return {
        "schema": SCHEMA_ID,
        "run_id": run_id,
        "variant_id": v.variant_id,
        "created_at": created,
        "plant": v.plant,
        "params": {"style": v.style, "theme": v.theme, "layout_seed": v.layout_seed,
                   "layout_source": layout_source, "pt_to_m": f"{scale.PT_TO_M:g}",
                   "kitchen_theme_env_only_affects_vray": True},
        "geometry": {"n_boxes": n_boxes, "rooms": summary or [],
                     "deterministic_gates": gates, "gate_detail": gate_detail or {}},
        "render_refs": {"iso": iso_rel, "sha256": sha, "renderer": renderer},
        "visual_findings": findings,
        "machine_score": {"value": _machine_score(gates, findings),
                          "label": MACHINE_LABEL},
        "verdict": verdict,
        "human_verdict": None,  # EXCLUSIVO do Felipe — a maquina nunca preenche
    }


def emit_gallery_item(corpus: Path, v: Variant, *, png: Path | None = None,
                      gates: dict | None = None, gate_detail: dict | None = None,
                      findings: dict | None = None, renderer: str = "su-free",
                      run_id: str | None = None, log=print) -> dict:
    """APARENCIA NAO-BLOQUEIA: materializa UM item de galeria PENDENTE
    (build_record, human_verdict=None) e faz append IDEMPOTENTE por variant_id no
    corpus append-only — pra uma saida mobiliada / mudanca de aparencia virar um
    item RECUPERAVEL na galeria em vez de morrer travada numa fila-arquivo ou numa
    branch wip. NUNCA espera veredito humano (esse e' do Felipe, offline).

    Fabrica canonica REUSADA = build_record (mesmo shape do sweep). O CHAMADOR
    controla `gates`: pra nao BLOQUEAR aparencia, nunca passe um gate FAIL aqui —
    sem FAIL e sem findings o verdict nasce PENDING_VISION (findings PASS -> CANDIDATE).

    Idempotente: variant_id ja no corpus -> NAO re-appenda (retorna o registro
    existente). Deterministico, safe pra rodar 2x (o corpus nunca e' reescrito)."""
    corpus = Path(corpus)
    existing = {r.get("variant_id"): r for r in read_jsonl(corpus)}
    if v.variant_id in existing:
        log(f"[gallery] {v.variant_id}: ja no corpus (skip idempotente)")
        return existing[v.variant_id]
    rec = build_record(v, run_id=run_id or corpus.parent.name, gates=gates or {},
                       gate_detail=gate_detail, png=png, renderer=renderer,
                       findings=findings, out_root=corpus.parent)
    append_jsonl(corpus, [rec])
    log(f"[gallery] {v.variant_id}: {rec['verdict']} (human_verdict=None) -> {corpus}")
    return rec


def run_variant(v: Variant, out_dir: Path, *, con_path: Path | None = None,
                provider=None, discrimination=None, render: str = "su-free",
                find_adapter=None, run_id: str | None = None,
                out_root: Path | None = None) -> dict:
    """Uma celula: furnish (in-process, SEM SketchUp) -> gates deterministicos
    ANTES do render -> iso SU-free -> adapter de achados -> registro julgado.
    `--render vray` fica como flag DOCUMENTADA (renderer=vray_skipped_su_free),
    nao exercitada nesta fatia — o iso barato e' sempre gerado."""
    _require_plant_scale(v.plant)
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_root = Path(out_root).resolve() if out_root else out_dir.parent
    run_id = run_id or out_root.name
    con = json.loads(Path(con_path or CONSENSUS).read_text("utf-8"))
    os.environ["FURNISH_STYLE"] = v.style or ""  # lido em CALL time pelo furnish
    renderer = "su-free" if render == "su-free" else "vray_skipped_su_free"
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            boxes, summary = collect_boxes(con)
    except SystemExit as e:  # gate da pia da cozinha aborta o build — FAIL honesto
        return build_record(
            v, run_id=run_id, gates={"kitchen_validation": "FAIL"},
            gate_detail={"kitchen_validation": str(e)}, renderer=renderer,
            layout_source="brain_default", out_root=out_root)
    boxes, layout_source = _apply_layout_seed(con, boxes, v.layout_seed)
    gates, gate_detail = run_deterministic_gates(boxes, con)
    from tools.render_parts_iso import render_parts
    # ENVELOPE-FIRST (nota 2/10 unânime do painel/GPT era "furniture-only, sem
    # envelope"): paredes/portas/janelas do consensus entram ANTES da mobília,
    # em corte dollhouse. SWEEP_SHELL=0 desliga (comparação/depuração).
    parts = _boxes_to_parts(boxes)
    if os.environ.get("SWEEP_SHELL", "1") != "0":
        from tools.shell_parts import shell_parts
        parts = shell_parts(con) + parts
    # elev 24→38 pós-shell (GPT: câmera baixa escondia os ambientes atrás da
    # massa cortada; mais zenital revela o interior sem virar top-down)
    png = Path(render_parts(parts, out_dir / "iso.png",
                            elev=38, azim=-56, title=v.variant_id))
    if find_adapter is not None:
        findings = find_adapter(png)
    else:
        findings = _collect_findings(png, plant=v.plant, provider=provider,
                                     discrimination=discrimination)
    return build_record(v, run_id=run_id, gates=gates, gate_detail=gate_detail,
                        summary=[list(s) for s in (summary or [])],
                        n_boxes=len(boxes), png=png, renderer=renderer,
                        findings=findings, layout_source=layout_source,
                        out_root=out_root)


def sweep(n: int | None, out_root: Path, *, plant: str = "planta_74",
          axes: dict | None = None, render: str = "su-free", provider=None,
          discrimination=None, con_path: Path | None = None, run_one=None,
          only: str | None = None, force_rerender: bool = False,
          log=print) -> list[dict]:
    """Roda as celulas do grid em serie (NUNCA paraleliza contra o :8765).
    corpus.jsonl e' append-only e idempotente por variant_id: celula ja vista e'
    pulada; excecao unica = registro PENDING_VISION com provider disponivel
    (upgrade de visao), que APPENDA um registro superseding (last-wins por
    variant_id na leitura — o arquivo nunca e' reescrito). Upgrade que volta
    PENDING_VISION (bridge fora / probe FAIL) NAO appenda — nao supersede nada;
    rerun com --ask-vision offline fica idempotente.
    force_rerender=True re-roda celula JA vista e appenda supersede — o caso
    'o RENDERER evoluiu' (ex.: shell arquitetonico novo): a idempotencia por
    presenca esconderia o render novo do corpus. Explicito, nunca default."""
    out_root = Path(out_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    corpus = out_root / "corpus.jsonl"
    by_id: dict = {}
    for r in read_jsonl(corpus):
        by_id[r.get("variant_id")] = r  # last-wins
    cells = expand_axes(axes, n=n, plant=plant)
    if only:
        cells = [c for c in expand_axes(axes, plant=plant) if c.variant_id == only]
    runner = run_one or run_variant
    records: list[dict] = []
    for v in cells:
        prev = by_id.get(v.variant_id)
        upgrade = (prev is not None and prev.get("verdict") == "PENDING_VISION"
                   and provider is not None)
        if prev is not None and not upgrade and not force_rerender:
            records.append(prev)
            log(f"[variant-sweep] {v.variant_id}: ja no corpus (skip)")
            continue
        rec = runner(v, out_root / v.variant_id, con_path=con_path,
                     provider=provider, discrimination=discrimination,
                     render=render, run_id=out_root.name, out_root=out_root)
        if upgrade and rec.get("verdict") == "PENDING_VISION" and not force_rerender:
            # upgrade que NAO trouxe visao: o rec e' semanticamente o prev —
            # appendar duplicaria uma linha que nao supersede nada (com
            # force_rerender o render NOVO supersede mesmo sem visao)
            records.append(prev)
            log(f"[variant-sweep] {v.variant_id}: upgrade sem visao "
                "(PENDING_VISION mantido; corpus intacto)")
            continue
        append_jsonl(corpus, [rec])
        by_id[v.variant_id] = rec
        records.append(rec)
        log(f"[variant-sweep] {v.variant_id}: verdict={rec.get('verdict')}")
    cells4 = []
    for rec in records:
        iso = (rec.get("render_refs") or {}).get("iso")
        if not iso:
            continue
        p = out_root / iso
        if not p.is_file():
            continue
        gates = (rec.get("geometry") or {}).get("deterministic_gates") or {}
        worst = ("FAIL" if "FAIL" in gates.values()
                 else "WARN" if "WARN" in gates.values() else "PASS")
        name = rec["variant_id"].split("__", 1)[-1][:42]
        cells4.append((name, p, worst, rec.get("verdict")))
    if cells4:
        from tools.sofa_class_matrix import _grid_sheet
        _grid_sheet(cells4, out_root / "contact_sheet.png",
                    f"FP-034 variant sweep — {plant} ({len(cells4)} celulas, "
                    f"verdicts = maquina provisional; aparencia final = Felipe)")
    return records


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="FP-034 judged variant sweep (SU-free)")
    ap.add_argument("--n", type=int, default=None, help="prefixo do grid")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--plant", default="planta_74")
    ap.add_argument("--render", choices=("su-free", "vray"), default="su-free",
                    help="vray = flag documentada (nao executa V-Ray nesta fatia)")
    ap.add_argument("--dry-run", action="store_true",
                    help="sem visao: registros reais com PENDING_VISION honesto")
    ap.add_argument("--ask-vision", action="store_true",
                    help="opt-in: 1 chamada serial por celula ao claude_bridge_vision")
    ap.add_argument("--bridge-url", default=None)
    ap.add_argument("--tier", default=None)
    ap.add_argument("--only", default=None, help="roda so este variant_id (grid inteiro)")
    ap.add_argument("--force-rerender", action="store_true",
                    help="re-roda celulas JA no corpus e appenda supersede (renderer evoluiu)")
    a = ap.parse_args(argv)
    provider = None
    if a.ask_vision and not a.dry_run:
        from tools.oracle_providers import get_provider
        provider = get_provider(BACKEND)
        if a.bridge_url and hasattr(provider, "url"):
            provider.url = a.bridge_url
        if a.tier and hasattr(provider, "tier"):
            provider.tier = a.tier
    try:
        recs = sweep(a.n, a.out, plant=a.plant, render=a.render,
                     provider=provider, only=a.only, force_rerender=a.force_rerender)
    except Exception as e:  # noqa: BLE001 — CLI: erro vira exit 1, nao traceback cru
        print(f"[variant-sweep] ERRO: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    counts: dict[str, int] = {}
    for r in recs:
        counts[r.get("verdict", "?")] = counts.get(r.get("verdict", "?"), 0) + 1
    print(json.dumps({"n": len(recs), "verdicts": counts,
                      "out": str(a.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
