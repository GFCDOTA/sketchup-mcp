"""bedroom_report.py — relatorio (JSON + Markdown) do brain de quartos
(entregavel #6 da spec). Classifica os comodos por nome, roda bedroom_layout
nos BEDROOM e registra por comodo: tipo inferido + fonte, area, cama escolhida
(+ fallback), candidato vencedor (moveis + score breakdown + motivos), candidatos
rejeitados + motivos. UNKNOWN / nao-quarto: pulado com motivo (nunca chuta).
Felipe 2026-06-05.

Uso: python tools/bedroom_report.py
     -> artifacts/planta_74/furnished/bedroom_report.{json,md}
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.bedroom_layout import run   # noqa: E402
from tools.room_type import BEDROOM, classify_rooms   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONSENSUS = ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
OUT_DIR = ROOT / "artifacts/planta_74/furnished"


def build_report(con, plant="planta_74"):
    rooms = classify_rooms(con)
    report = {"plant": plant, "stage": "bedroom_layout", "rooms": []}
    for r in rooms:
        rec = {"id": r["id"], "name": r["name"], "room_type": r["room_type"],
               "room_type_source": r["room_type_source"]}
        if r["room_type"] != BEDROOM:
            rec["status"] = "SKIPPED"
            rec["reason"] = (r.get("reason")
                             or f"tipo {r['room_type']}: brain de quarto so mobilia BEDROOM")
            report["rooms"].append(rec)
            continue
        _, out = run(con, r["id"])
        rec["status"] = out["result"]
        rec["area_m2"] = out["area_m2"]
        rec["bed_size"] = out.get("bed_size")
        rec["bed_size_target"] = out.get("bed_size_target")
        if out.get("fallback"):
            rec["fallback"] = out["fallback"]
        if out["result"] == "OK":
            cw = out["chosen"]["headboard_wall"]
            ch = next(c for c in out["candidates"]
                      if c["headboard_wall"] == cw and c["valid"])
            rec["chosen"] = {"headboard_wall": ch["headboard_wall"],
                             "total_score": ch["total_score"],
                             "furniture": ch["furniture"],
                             "score_breakdown": ch["soft"],
                             "reasons": ch.get("reasons", []),
                             "metrics": ch["metrics"]}
            rec["rejected"] = [{"headboard_wall": c["headboard_wall"], "valid": c["valid"],
                                "total_score": c["total_score"],
                                "blocked_by": c.get("violations", []),
                                "penalties": c.get("penalties", [])}
                               for c in out["candidates"] if c["headboard_wall"] != cw]
        else:
            rec["reason"] = out.get("reason")
            rec["rejected"] = out.get("ranking", [])
        report["rooms"].append(rec)
    return report


def to_markdown(rep):
    L = [f"# Relatorio auto-mobiliado — quartos ({rep['plant']})", ""]
    n_bed = sum(1 for r in rep["rooms"] if r["room_type"] == BEDROOM)
    n_ok = sum(1 for r in rep["rooms"] if r.get("status") == "OK")
    L.append(f"{len(rep['rooms'])} comodos | {n_bed} quartos | {n_ok} mobiliados OK")
    L.append("")
    for r in rep["rooms"]:
        L.append(f"## `{r['id']}` — {r['name']}  ({r['room_type']}, via {r['room_type_source']})")
        if r.get("status") == "SKIPPED":
            L.append(f"- **PULADO**: {r['reason']}")
            L.append("")
            continue
        L.append(f"- area **{r.get('area_m2')} m2** | cama **{r.get('bed_size')}** "
                 f"(alvo {r.get('bed_size_target')})")
        if r.get("fallback"):
            fb = r["fallback"]
            L.append(f"- ⚠ **fallback de cama**: {fb['from']} → {fb['to']} ({fb['reason']})")
        if r["status"] == "OK":
            ch = r["chosen"]
            L.append(f"- **vencedor**: cabeceira `{ch['headboard_wall']}` — **{ch['total_score']} pts**")
            L.append(f"  - moveis: " + ", ".join(f["kind"] for f in ch["furniture"]))
            L.append(f"  - score: " + ", ".join(f"{k}={v}" for k, v in ch["score_breakdown"].items()))
            if ch.get("reasons"):
                L.append(f"  - prós: " + "; ".join(ch["reasons"]))
            for rej in r.get("rejected", []):
                why = rej.get("blocked_by") or rej.get("penalties") or ["-"]
                L.append(f"  - rejeitado `{rej.get('headboard_wall')}` "
                         f"(valid={rej.get('valid')}, {rej.get('total_score')} pts): "
                         f"{', '.join(map(str, why))[:90]}")
        else:
            L.append(f"- **{r['status']}**: {r.get('reason')}")
        L.append("")
    return "\n".join(L)


def main():
    con = json.loads(CONSENSUS.read_text("utf-8"))
    rep = build_report(con)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "bedroom_report.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "bedroom_report.md").write_text(to_markdown(rep), encoding="utf-8")
    n_bed = sum(1 for r in rep["rooms"] if r["room_type"] == BEDROOM)
    n_ok = sum(1 for r in rep["rooms"] if r.get("status") == "OK")
    print(f"[report] {len(rep['rooms'])} comodos, {n_bed} quartos, {n_ok} mobiliados OK")
    print(f"  -> {OUT_DIR}/bedroom_report.json + bedroom_report.md")


if __name__ == "__main__":
    main()
