"""solver_benchmark.py — linha de base MEDIDA do solver F2 (FP-054 F3, #453). Nao altera o solver.

    PT_TO_M=0.0259 PYTHONPATH=. python -m tools.validation.solver_benchmark [--repeats 5] [--out runs/solver_benchmark.json]

Para cada comodo planejavel da planta_74 (BANHO 01 `r005`, BANHO 02 `r006`, LAVABO `r007`) e cada teto de candidatos (1, 10, 100) mede o
tempo de `intelligent_pipeline.plan_room` (especialista + problema + solver + ranking) com `repeats` repeticoes: min / p50 / p95 / max em segundos.
O pico de memoria do PROCESSO (working set de pico) e medido num subprocesso novo por caso, para nao herdar o pico de outro. Registra hardware, Python,
commit e SHA-256 do consenso. NAO impoe meta: a F3 manda fixar o budget de regressao a partir de dados observados, nunca antes.

Escopo medido: dimensao "candidatos" (1/10/100 do teto `max_candidates`; o total de candidatos do comodo vai no resultado). A dimensao
"obstaculos" (10/100/1000) e a geometria adversarial NAO sao medidas aqui e ficam registradas como pendentes no resultado.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROOMS = ("r005", "r006", "r007")
CAPS = (1, 10, 100)


def peak_rss_mb() -> float | None:
    """Pico de memoria do processo (MB). Windows: PeakWorkingSetSize via psapi; POSIX: ru_maxrss. None se indisponivel."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            c = Counters()
            c.cb = ctypes.sizeof(c)
            h = ctypes.windll.kernel32.GetCurrentProcess()
            if not ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
                return None
            return round(c.PeakWorkingSetSize / 1024 / 1024, 1)
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except Exception:  # noqa: BLE001 — medicao opcional: nunca derruba o benchmark
        return None


def percentile(values: list[float], q: float) -> float:
    """Percentil por interpolacao linear (sem numpy); q em [0, 100]."""
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * q / 100.0
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def summarize(times: list[float]) -> dict:
    return {"n": len(times), "min_s": round(min(times), 4), "p50_s": round(statistics.median(times), 4),
            "p95_s": round(percentile(times, 95), 4), "max_s": round(max(times), 4)}


def run_case(room: str, cap: int, repeats: int) -> dict:
    """Executa UM caso no processo atual (chamado no subprocesso)."""
    from core.pipeline_contracts import CapabilityLedger
    from tools.furnish_apartment import collect_boxes
    from tools.orchestration import furnish_apartment as fa
    from tools.orchestration import intelligent_pipeline as ip
    from tools.room_type import classify_rooms
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    from tools.validation.functional_clearance import collect_interfaces
    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _summary = collect_boxes(con)
        ifaces = collect_interfaces(con, boxes)
    r = {x["id"]: x for x in classify_rooms(con)}[room]
    brain = fa.BRAINS.get(r["room_type"])
    times, last = [], None
    for _ in range(repeats):
        t = time.perf_counter()
        last = ip.plan_room(con, boxes, ifaces, room, r["room_type"], str(r["name"]), ip._builder_symbol(brain), CapabilityLedger(),
                            max_candidates=cap)
        times.append(time.perf_counter() - t)
    p = last["proposal"]
    return {"room": room, "name": str(r["name"]), "max_candidates": cap, "candidates_total": p.candidates_total,
            "status": last["status"], "time": summarize(times), "peak_rss_mb": peak_rss_mb()}


def git(*a: str) -> str:
    return subprocess.check_output(["git", *a], cwd=ROOT, text=True).strip()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--out", default="runs/solver_benchmark.json")
    ap.add_argument("--case", nargs=2, metavar=("ROOM", "CAP"), help="interno: roda um caso e imprime JSON")
    a = ap.parse_args(argv)
    if a.case:
        print(json.dumps(run_case(a.case[0], int(a.case[1]), a.repeats)))
        return 0
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    cases = []
    for room in ROOMS:
        for cap in CAPS:
            out = subprocess.run([sys.executable, "-X", "utf8", "-m", "tools.validation.solver_benchmark", "--case", room, str(cap),
                                  "--repeats", str(a.repeats)], cwd=ROOT, capture_output=True, text=True, check=True,
                                 env={**os.environ, "PYTHONPATH": str(ROOT)}).stdout.strip().splitlines()[-1]
            cases.append(json.loads(out))
            print(f"{room} cap={cap}: p50={cases[-1]['time']['p50_s']}s p95={cases[-1]['time']['p95_s']}s rss={cases[-1]['peak_rss_mb']} MB", flush=True)
    res = {"schema_version": "solver_benchmark.v1", "commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
           "consensus_sha256": hashlib.sha256(Path(PLANTA_74_CONSENSUS).read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
           "hardware": {"platform": platform.platform(), "machine": platform.machine(), "cpu_count": os.cpu_count(),
                        "python": platform.python_version()},
           "repeats": a.repeats, "cases": cases,
           "not_measured": ["obstaculos 10/100/1000 (cenas sinteticas)", "geometria adversarial", "contagem de intersection/buffer/unary_union"],
           "budget": "nenhum: so a linha de base; budget de regressao por capability sai destes dados (FP-054 F3)"}
    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
