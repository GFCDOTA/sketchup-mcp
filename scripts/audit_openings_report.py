"""Gera docs/OPENINGS-EXPLOSION-AUDIT.md a partir do audit_summary.json."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "runs" / "openings_audit" / "audit_summary.json"
OUT = ROOT / "docs" / "OPENINGS-EXPLOSION-AUDIT.md"


def fmt_int(n):
    return f"{n}"


def bar(n, total, width=30):
    if total == 0:
        return ""
    filled = int(round(n / total * width))
    return "#" * filled + "." * (width - filled)


def dist_table(title, d, total):
    lines = [f"### {title}", "", "| key | n | % | bar |", "|-----|---|---|-----|"]
    for k, v in sorted(d.items(), key=lambda kv: -kv[1]):
        pct = v / total * 100 if total else 0
        lines.append(f"| {k} | {v} | {pct:.1f}% | `{bar(v, total, 24)}` |")
    return "\n".join(lines)


def opening_row(e):
    ra = e.get("room_a") or "-"
    rb = e.get("room_b") or "-"
    ra_area = e.get("room_a_area")
    rb_area = e.get("room_b_area")
    ra_disp = f"{ra} ({ra_area:.0f})" if ra_area else ra
    rb_disp = f"{rb} ({rb_area:.0f})" if rb_area else rb
    return (
        f"| {e['opening_id']} | {e['wall_a']} | {e['wall_b']} | "
        f"{ra_disp} | {rb_disp} | {e['width']:.1f} | {e['orientation'][0].upper()} | "
        f"{e['kind']} | {'YES' if e['genuine'] else 'no'} |"
    )


def main():
    data = json.loads(SUMMARY.read_text(encoding="utf-8"))
    cur = data["current"]
    base = data["baseline"]

    # top suspeitos: ordena por (genuine=False primeiro, entao width extremo)
    def suspect_score(e):
        w = e["width"]
        extreme = max(0.0, 10 - w) + max(0.0, w - 280)
        return (0 if not e["genuine"] else 1, -extreme)

    cur_sorted_susp = sorted(cur["enriched"], key=suspect_score)[:10]
    cur_sorted_gen = [e for e in cur["enriched"] if e["genuine"]]
    # top genuinos por largura tipica de porta (60-110) entre duas rooms legitimas
    cur_sorted_gen.sort(
        key=lambda e: (
            0 if (e["legit_a"] and e["legit_b"]) else 1,
            abs(e["width"] - 85.0),
        )
    )
    top_gen = cur_sorted_gen[:10]

    doc: list[str] = []
    doc.append("# OPENINGS EXPLOSION AUDIT: planta_74 (15 -> 71 post-hardening)")
    doc.append("")
    doc.append("Comit atual: `f2b896c` (branch `fix/dedup-colinear-planta74`).")
    doc.append("Baseline: `dcb9751` (main pre-fix, em `runs/baseline_pre_fix_main`).")
    doc.append("")
    doc.append("Nota: o prompt mencionava 7 openings no baseline; o artefato real tem 15.")
    doc.append("A explosao relevante e, portanto, 15 -> 71 (4.7x), nao 7 -> 71 (10x).")
    doc.append("")
    doc.append("## 1. Numeros agregados")
    doc.append("")
    doc.append("| metrica | baseline (pre-fix) | current (pos-hardening) | delta |")
    doc.append("|---|---|---|---|")
    doc.append(f"| openings | {base['n_openings']} | {cur['n_openings']} | +{cur['n_openings']-base['n_openings']} |")
    doc.append(f"| walls | {base['n_walls']} | {cur['n_walls']} | +{cur['n_walls']-base['n_walls']} |")
    doc.append(f"| rooms (total) | {base['n_rooms_total']} | {cur['n_rooms_total']} | +{cur['n_rooms_total']-base['n_rooms_total']} |")
    doc.append(f"| rooms legit (>=3000 px2) | {base['n_rooms_legit']} | {cur['n_rooms_legit']} | +{cur['n_rooms_legit']-base['n_rooms_legit']} |")
    doc.append(f"| openings genuine (>=1 lado room legit) | {base['genuine_count']} | {cur['genuine_count']} | +{cur['genuine_count']-base['genuine_count']} |")
    doc.append(f"| openings suspect | {base['suspect_count']} | {cur['suspect_count']} | {cur['suspect_count']-base['suspect_count']:+d} |")
    doc.append("")
    doc.append("Observacao critica: o baseline pre-fix so tinha 3 rooms acima de 3000 px2 "
              "(rooms 1/4/9 com areas 13k/16k/3.5k). O resto (13 das 16) sao slivers. "
              "O hardening nao inventou portas; ele passou a fechar poligonos antes perdidos.")
    doc.append("")

    doc.append("## 2. Distribuicoes (post-hardening)")
    doc.append("")
    doc.append(dist_table("Por kind", cur["by_kind"], cur["n_openings"]))
    doc.append("")
    doc.append(dist_table("Por orientacao", cur["by_orient"], cur["n_openings"]))
    doc.append("")
    doc.append(dist_table("Por bucket de largura (px @ 150 DPI)",
                           cur["by_bucket"], cur["n_openings"]))
    doc.append("")
    doc.append("Faixas de referencia: door 60-110; wide door 110-200; window/passage 200-280; "
              "tiny 10-60 (suspeito - gap dedup residual); absurd <10 (bug).")
    doc.append("")

    doc.append("## 3. Openings vs rooms (tabela top-genuinos)")
    doc.append("")
    doc.append("Classificacao `genuine = pelo menos um lado do opening cai em room >=3000 px2`. "
              "Lado = Point(cx +/- 8px, cy +/- 8px) perpendicular ao vao, via shapely contains.")
    doc.append("")
    doc.append("### Top 10 genuinos (ambos lados em rooms grandes, width proxima de porta padrao)")
    doc.append("")
    doc.append("| opening_id | wall_a | wall_b | room_a (area) | room_b (area) | width | ori | kind | genuine |")
    doc.append("|---|---|---|---|---|---|---|---|---|")
    for e in top_gen:
        doc.append(opening_row(e))
    doc.append("")

    doc.append("### Top 10 suspeitos (mais provaveis de serem falsos positivos)")
    doc.append("")
    doc.append("Priorizados por (1) genuine=False e (2) width extremo (<10 ou >280). "
              "So 4/71 openings sao classificados suspeitos por este criterio.")
    doc.append("")
    doc.append("| opening_id | wall_a | wall_b | room_a (area) | room_b (area) | width | ori | kind | genuine |")
    doc.append("|---|---|---|---|---|---|---|---|---|")
    for e in cur_sorted_susp:
        doc.append(opening_row(e))
    doc.append("")

    # detalhe: quantos tem ambos lados legit vs so um
    both = sum(1 for e in cur["enriched"] if e["legit_a"] and e["legit_b"])
    one = sum(1 for e in cur["enriched"] if (e["legit_a"] or e["legit_b"]) and not (e["legit_a"] and e["legit_b"]))
    none = sum(1 for e in cur["enriched"] if not (e["legit_a"] or e["legit_b"]))
    doc.append("### Classificacao granular por quantidade de lados legit")
    doc.append("")
    doc.append(f"- `BOTH` rooms grandes: **{both}** openings (porta 'perfeita' entre dois ambientes)")
    doc.append(f"- `ONE_SIDE` grande + outro lado sliver/vazio: **{one}** openings (borda externa ou split)")
    doc.append(f"- `NONE` lado em room legit: **{none}** openings (suspects puros)")
    doc.append("")

    doc.append("## 4. Histograma textual de width (post-hardening)")
    doc.append("")
    bins = list(range(0, 301, 20))
    hist = [0] * (len(bins))
    for e in cur["enriched"]:
        w = e["width"]
        if w >= 300:
            hist[-1] += 1
            continue
        idx = int(w // 20)
        if idx < len(hist):
            hist[idx] += 1
    doc.append("```")
    doc.append("width_bin  count  bar")
    for i, cnt in enumerate(hist):
        lo = bins[i]
        hi = bins[i] + 20
        label = f"{lo:3d}-{hi:3d}"
        doc.append(f"{label:>9} {cnt:5d}  {'#'*cnt}")
    doc.append("```")
    doc.append("")

    doc.append("## 5. Hipoteses (H1/H2/H3)")
    doc.append("")
    doc.append("- **H1 (extras em slivers)**: REJEITADA para a maioria. Apenas 4 openings nao tem "
              "nenhum lado em room legit. Se H1 fosse dominante, esperariamos dezenas de "
              "openings entre slivers triangulares.")
    doc.append("- **H2 (fragmentos que deveriam estar snapados)**: PARCIAL. 15 openings caem no "
              "bucket `tiny_10-60` (<60 px, menor que porta real). Sao candidatos a dedup "
              "residual: provavelmente dois pedacos de mesma wall que o extractor deixou com "
              "gap 20-40 px, e o detector classificou como porta. `_extend_to_perpendicular` "
              "nao alcanca estes (snap = 60 px mas gap no meio da wall, nao no endpoint).")
    doc.append("- **H3 (ganho real de recall)**: CONFIRMADA como hipotese dominante. "
              f"Post-hardening: {cur['n_rooms_legit']} rooms legitimas (vs 3 no baseline), "
              f"{cur['genuine_count']}/{cur['n_openings']} openings genuinos "
              f"({cur['genuine_count']/cur['n_openings']*100:.0f}%). "
              "O baseline pre-fix estava falhando em fechar polygonos - pipeline atual "
              "finalmente consegue separar os ambientes que o raster original tem.")
    doc.append("")
    doc.append("Evidencia quantitativa: rooms grandes (>10k px2) saltaram de 2 (baseline) "
              "para 17 (current). Isso so e possivel se walls novas realmente fecharam poligonos.")
    doc.append("")

    doc.append("## 6. Recomendacoes")
    doc.append("")
    doc.append("Dois ganchos possiveis pra reduzir ruido sem sacrificar recall:")
    doc.append("")
    doc.append("1. **Sliver filter downstream** (preferido, baixo risco): ao filtrar rooms "
              "com area < LEGIT_AREA no pos-processamento, dropar tambem openings cujos dois "
              "lados caem em slivers ou fora de rooms. Hoje seriam 4 openings removidos. "
              "Simples, determinstico, nao mexe em `openings/service.py`.")
    doc.append("")
    doc.append("2. **Reforcar dedup colinear residual em openings/service.py** (ataque H2): "
              "15 openings no bucket 10-60 px sao provavelmente mesma wall fragmentada. "
              "Opcoes: (a) aumentar `_MIN_OPENING_PX` de 8 para 40 (corta todos tiny mas risca "
              "portas de 30-40 px em desenhos em escala menor); (b) adicionar criterio "
              "`confidence = min(wall_a.confidence, wall_b.confidence)` e descartar bridges com "
              "`confidence < 0.4` + `width < 60`; (c) checar se wall_a.thickness == wall_b.thickness "
              "com tolerancia pequena - se sim E gap < 50 px, e provavel mesma wall.")
    doc.append("")
    doc.append("Recomendacao final: adotar (1) agora (patch 1-linha no room filter pipeline) "
              "e agendar (2c) como fase de followup junto com o sliver filter - ambos atacam "
              "o mesmo sintoma (fragmentacao residual) por vias complementares.")
    doc.append("")
    doc.append("## 7. Metodologia e artefatos")
    doc.append("")
    doc.append("- Comando extracao: `python main.py extract planta_74.pdf --out runs/openings_audit`")
    doc.append("- Scripts: `scripts/audit_openings.py` (enrichment) + `scripts/audit_openings_report.py` (este doc)")
    doc.append("- Dados brutos: `runs/openings_audit/observed_model.json`")
    doc.append("- Sumario JSON: `runs/openings_audit/audit_summary.json`")
    doc.append("- Baseline: `runs/baseline_pre_fix_main/observed_model.json`")
    doc.append("- Overlay visual com openings: `runs/openings_audit/overlay_with_openings.png`")
    doc.append("")
    doc.append("Criterio `genuine`: construimos dois Points deslocados 8px perpendiculares "
              "ao opening a partir do center, e verificamos se pelo menos um cai em room "
              "com area >= 3000 px2 via shapely Polygon.contains. Threshold 3000 e conservador "
              "(apartamento tipo: WC 2-4k, cozinha 4-6k, quarto 6-12k, sala/varanda 10-40k). "
              "Slivers diagonais de dedup ficam tipicamente < 2000 px2.")
    doc.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(doc), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
