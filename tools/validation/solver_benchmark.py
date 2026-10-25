"""solver_benchmark.py — linha de base MEDIDA do solver F2 (FP-054 F3, #453). Nao altera o solver.

    PT_TO_M=0.0259 PYTHONPATH=. python -m tools.validation.solver_benchmark [--repeats 5] [--out runs/solver_benchmark.json]

Para cada comodo planejavel da planta_74 (BANHO 01 `r005`, BANHO 02 `r006`, LAVABO `r007`) e cada teto de candidatos (1, 10, 100) mede o
tempo de `intelligent_pipeline.plan_room` (especialista + problema + solver + ranking) com `repeats` repeticoes: min / p50 / p95 / max em segundos.
O pico de memoria do PROCESSO (working set de pico) e medido num subprocesso novo por caso, para nao herdar o pico de outro. Registra hardware, Python,
commit e SHA-256 do consenso. NAO impoe meta: a F3 manda fixar o budget de regressao a partir de dados observados, nunca antes.

Escopo medido: dimensao "candidatos" (1/10/100 do teto `max_candidates`; o total de candidatos do comodo vai no resultado) e, com
`--obstacles`, a dimensao "obstaculos" (0/10/100/1000 caixas SINTETICAS deterministicas acrescentadas as da planta, com `max_candidates` fixo)
em dois regimes: `far` (fora da vizinhanca do comodo: custo do filtro) e `near` (no anel de 1 m em volta da celula: entram na avaliacao).
Uma passada extra, so de contagem (nao entra nos tempos), registra quantas vezes `intersection`/`buffer`/`unary_union` (e afins) foram chamados.
Com `--adversarial`, a geometria ADVERSARIAL (pior caso para os gates de intersecao): `long` (barras finas que atravessam toda a vizinhanca e
cruzam muitos candidatos), `stacked` (caixas empilhadas no mesmo ponto, dentro do comodo: sobreposicao degenerada) e `rotated` (quadrados a 45 graus
dentro do comodo). Cenas sinteticas nunca tocam a planta nem o consenso.

    PT_TO_M=0.0259 PYTHONPATH=. python -m tools.validation.solver_benchmark --obstacles [--repeats 3] [--out runs/solver_benchmark_obstacles.json]
    PT_TO_M=0.0259 PYTHONPATH=. python -m tools.validation.solver_benchmark --adversarial [--repeats 3] [--out runs/solver_benchmark_adversarial.json]
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
OBSTACLES = (0, 10, 100, 1000)
OBSTACLE_MODES = ("far", "near")
ADVERSARIAL_MODES = ("long", "stacked", "rotated")
ADVERSARIAL_N = (10, 100, 1000)
OBSTACLE_CAP = 10                      # candidatos fixos na dimensao obstaculos: so o numero de caixas varia
OBSTACLE_SIDE_IN = 4.0                 # lado da caixa sintetica (pol.)
OBSTACLE_STEP_IN = 3.0                 # passo da grade que amostra o anel `near`
COUNTED_METHODS = ("intersection", "buffer", "union", "intersects", "distance", "difference")


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
            kernel32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE                 # HANDLE de 64 bits: sem restype o ctypes trunca
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
                return None
            return round(c.PeakWorkingSetSize / 1024 / 1024, 1)
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except Exception:  # noqa: BLE001 — medicao opcional: nunca derruba o benchmark
        return None


def obstacle_positions(cell, n: int, mode: str, zone_in: float = 39.37) -> list[tuple[float, float]]:
    """Cantos (x, y), em polegadas, de `n` caixas sinteticas. Deterministico (sem random/clock). `cell`: poligono shapely do comodo.

    `far`: grade 12 pol. de passo, 200 pol. alem do canto da vizinhanca (fora dela: o filtro `neighborhood` deve descarta-las).
    `near`: pontos da grade `OBSTACLE_STEP_IN` que caem no ANEL entre a celula e a celula + 1 m (a vizinhanca do solver), em ordem
    estavel, reciclados ciclicamente se `n` passa do numero de posicoes (sobreposicao entre sinteticas e intencional e documentada)."""
    import math

    from shapely.geometry import Point
    if n <= 0:
        return []
    if mode not in OBSTACLE_MODES:
        raise ValueError(f"modo desconhecido: {mode!r}")
    minx, miny, maxx, maxy = cell.buffer(zone_in).bounds
    if mode == "far":
        side = max(1, math.ceil(math.sqrt(n)))
        return [(maxx + 200 + (i % side) * 12.0, maxy + 200 + (i // side) * 12.0) for i in range(n)]
    ring = cell.buffer(zone_in).difference(cell)
    slots = []
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            if ring.contains(Point(x, y)):
                slots.append((x, y))
            y += OBSTACLE_STEP_IN
        x += OBSTACLE_STEP_IN
    if not slots:
        raise ValueError("anel vazio: nenhuma posicao `near` disponivel")
    return [slots[i % len(slots)] for i in range(n)]


def synthetic_obstacles(template: dict, positions: list[tuple[float, float]]) -> list[dict]:
    """Caixas sinteticas no formato de `collect_boxes` (copiam o molde e trocam geometria/identidade). Nunca entram na planta."""
    out = []
    for i, (x, y) in enumerate(positions):
        s = OBSTACLE_SIDE_IN
        b = dict(template)
        b.update(corners=[[x, y], [x + s, y], [x + s, y + s], [x, y + s]], x0=x, y0=y, x1=x + s, y1=y + s, room="SYNTH",
                 module=f"SynthObstacle{i}", kind="synth_obstacle", label="synth_obstacle", z0_in=0.0, h_in=10.0)
        out.append(b)
    return out


def adversarial_boxes(template: dict, cell, n: int, kind: str, zone_in: float = 39.37) -> list[dict]:
    """`n` caixas sinteticas ADVERSARIAS (cantos em polegadas), deterministicas, no formato de `collect_boxes`.

    `long`: barras de 1 pol. de espessura que atravessam toda a vizinhanca (celula + 1 m), alternando horizontal/vertical e espalhadas
    por TODA a extensao (qualquer n cobre o comodo, nao so a borda) — cada barra cruza a celula e a maioria dos candidatos. `stacked`: caixas 4x4 sobre o centroide da celula, com deslocamentos de 0,5 pol. em ciclo de 3x3
    (sobreposicao degenerada dentro do comodo). `rotated`: quadrados de 6 pol. girados 45 graus numa grade de 8 pol. dentro da celula."""
    import math

    from shapely.geometry import Point
    if kind not in ADVERSARIAL_MODES:
        raise ValueError(f"tipo adversarial desconhecido: {kind!r}")
    if n <= 0:
        return []
    minx, miny, maxx, maxy = cell.buffer(zone_in).bounds
    corners_list: list[list[list[float]]] = []
    if kind == "long":
        n_h, n_v = (n + 1) // 2, n // 2                      # horizontais nas posicoes pares, verticais nas impares
        for i in range(n):
            horizontal = i % 2 == 0
            k, count = (i // 2, n_h) if horizontal else (i // 2, n_v)
            lo, hi = (miny, maxy) if horizontal else (minx, maxx)
            pos = lo + (k * (hi - lo - 1.0) / (count - 1) if count > 1 else (hi - lo - 1.0) / 2.0)      # espalha por TODA a vizinhanca
            if horizontal:
                corners_list.append([[minx, pos], [maxx, pos], [maxx, pos + 1.0], [minx, pos + 1.0]])
            else:
                corners_list.append([[pos, miny], [pos + 1.0, miny], [pos + 1.0, maxy], [pos, maxy]])
    elif kind == "stacked":
        c = cell.centroid
        for i in range(n):
            x, y = c.x + (i % 3 - 1) * 0.5, c.y + ((i // 3) % 3 - 1) * 0.5
            corners_list.append([[x - 2.0, y - 2.0], [x + 2.0, y - 2.0], [x + 2.0, y + 2.0], [x - 2.0, y + 2.0]])
    else:
        cx0, cy0, cx1, cy1 = cell.bounds
        slots = []
        x = cx0
        while x < cx1:
            y = cy0
            while y < cy1:
                if cell.contains(Point(x, y)):
                    slots.append((x, y))
                y += 8.0
            x += 8.0
        if not slots:
            raise ValueError("celula sem posicoes para `rotated`")
        h = 6.0 / 2.0 * math.sqrt(2.0)                     # semi-diagonal do quadrado de 6 pol. girado 45 graus
        for i in range(n):
            x, y = slots[i % len(slots)]
            corners_list.append([[x, y - h], [x + h, y], [x, y + h], [x - h, y]])
    out = []
    for i, corners in enumerate(corners_list):
        xs, ys = [c[0] for c in corners], [c[1] for c in corners]
        b = dict(template)
        b.update(corners=corners, x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys), room="SYNTH", module=f"SynthAdversarial{i}",
                 kind="synth_adversarial", label="synth_adversarial", z0_in=0.0, h_in=10.0)
        out.append(b)
    return out


class CallCounter:
    """Conta chamadas de operacoes shapely caras enquanto ativo. Uso: `with CallCounter() as c: ...; c.counts`.

    Metodos de `BaseGeometry` (COUNTED_METHODS) sao embrulhados na classe; `unary_union` e embrulhado em `shapely.ops` e em todo modulo
    carregado que o importou por nome (`from shapely.ops import unary_union`). Tudo e restaurado ao sair, mesmo com excecao."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self._undo: list = []

    def _wrap(self, name, fn):
        def counted(*a, **k):
            self.counts[name] = self.counts.get(name, 0) + 1
            return fn(*a, **k)
        counted.__wrapped__ = fn
        return counted

    def __enter__(self) -> "CallCounter":
        import shapely.ops
        from shapely.geometry.base import BaseGeometry
        for name in COUNTED_METHODS:
            orig = getattr(BaseGeometry, name)
            setattr(BaseGeometry, name, self._wrap(name, orig))
            self._undo.append((BaseGeometry, name, orig))
        orig_uu = shapely.ops.unary_union
        wrapped = self._wrap("unary_union", orig_uu)
        for mod in list(sys.modules.values()):
            if getattr(mod, "unary_union", None) is orig_uu:
                setattr(mod, "unary_union", wrapped)
                self._undo.append((mod, "unary_union", orig_uu))
        return self

    def __exit__(self, *exc) -> None:
        for owner, name, orig in reversed(self._undo):
            setattr(owner, name, orig)
        self._undo.clear()


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


def run_case(room: str, cap: int, repeats: int, obstacles: int = 0, mode: str = "far", count_calls: bool = False) -> dict:
    """Executa UM caso no processo atual (chamado no subprocesso). `obstacles` > 0 acrescenta caixas sinteticas (`mode` far|near)."""
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
    n_real = len(boxes)
    if obstacles:
        from shapely.geometry import Polygon

        from core.scale import PT_TO_IN
        from tools.spatial_model import build_spatial_model
        cell = Polygon([(x * PT_TO_IN, y * PT_TO_IN) for x, y in build_spatial_model(con, room)["_geom"]["cell"].exterior.coords])
        template = next(b for b in boxes if b.get("room") and b.get("corners"))
        if mode in ADVERSARIAL_MODES:
            boxes = boxes + adversarial_boxes(template, cell, obstacles, mode)
        else:
            boxes = boxes + synthetic_obstacles(template, obstacle_positions(cell, obstacles, mode))
    symbol = ip._builder_symbol(brain)

    def once():
        return ip.plan_room(con, boxes, ifaces, room, r["room_type"], str(r["name"]), symbol, CapabilityLedger(), max_candidates=cap)
    times, last = [], None
    for _ in range(repeats):
        t = time.perf_counter()
        last = once()
        times.append(time.perf_counter() - t)
    p = last["proposal"]
    out = {"room": room, "name": str(r["name"]), "max_candidates": cap, "candidates_total": p.candidates_total,
           "status": last["status"], "time": summarize(times), "peak_rss_mb": peak_rss_mb()}
    if obstacles or count_calls:
        out.update(obstacles=obstacles, obstacle_mode=mode if obstacles else None, boxes_real=n_real, boxes_total=len(boxes))
    if count_calls:
        with CallCounter() as c:                    # passada extra, fora dos tempos acima (o embrulho custa)
            once()
        out["shapely_calls"] = dict(sorted(c.counts.items()))
    return out


def git(*a: str) -> str:
    return subprocess.check_output(["git", *a], cwd=ROOT, text=True).strip()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--out", default="runs/solver_benchmark.json")
    ap.add_argument("--case", nargs=2, metavar=("ROOM", "CAP"), help="interno: roda um caso e imprime JSON")
    ap.add_argument("--obstacles", action="store_true", help="mede a dimensao obstaculos (sinteticos far/near) em vez da de candidatos")
    ap.add_argument("--adversarial", action="store_true", help="mede a geometria adversarial (long/stacked/rotated) em vez das outras dimensoes")
    ap.add_argument("--obstacle-case", nargs=3, metavar=("ROOM", "N", "MODE"), help="interno: um caso da dimensao obstaculos")
    a = ap.parse_args(argv)
    if a.case:
        print(json.dumps(run_case(a.case[0], int(a.case[1]), a.repeats)))
        return 0
    if a.obstacle_case:
        print(json.dumps(run_case(a.obstacle_case[0], OBSTACLE_CAP, a.repeats, int(a.obstacle_case[1]), a.obstacle_case[2], count_calls=True)))
        return 0
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    cases = []
    obstacle_dim = a.obstacles or a.adversarial
    if a.adversarial:
        grid = [(room, n, m) for room in ROOMS for n in ADVERSARIAL_N for m in ADVERSARIAL_MODES]
    elif a.obstacles:
        grid = [(room, n, m) for room in ROOMS for n in OBSTACLES for m in (OBSTACLE_MODES if n else ("far",))]
    else:
        grid = [(room, cap, None) for room in ROOMS for cap in CAPS]
    for room, k, m in grid:
        flag = ["--obstacle-case", room, str(k), m] if obstacle_dim else ["--case", room, str(k)]
        out = subprocess.run([sys.executable, "-X", "utf8", "-m", "tools.validation.solver_benchmark", *flag, "--repeats", str(a.repeats)],
                             cwd=ROOT, capture_output=True, text=True, check=True,
                             env={**os.environ, "PYTHONPATH": str(ROOT)}).stdout.strip().splitlines()[-1]
        cases.append(json.loads(out))
        c = cases[-1]
        print(f"{room} {'obstacles=%d %s' % (k, m) if obstacle_dim else 'cap=%d' % k}: p50={c['time']['p50_s']}s p95={c['time']['p95_s']}s "
              f"rss={c['peak_rss_mb']} MB status={c['status']}" + (f" calls={c['shapely_calls']}" if obstacle_dim else ""), flush=True)
    res = {"schema_version": ("solver_benchmark_adversarial.v1" if a.adversarial else "solver_benchmark_obstacles.v1" if a.obstacles
                                                         else "solver_benchmark.v1"), "commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
           "consensus_sha256": hashlib.sha256(Path(PLANTA_74_CONSENSUS).read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
           "hardware": {"platform": platform.platform(), "machine": platform.machine(), "cpu_count": os.cpu_count(),
                        "python": platform.python_version()},
           "repeats": a.repeats, "cases": cases,
           "not_measured": (["outra maquina", "contagem em gates fora do solver (so plan_room e contado)", "obstaculos adversariais acima de 1000"]
                            if a.adversarial else
                            ["geometria adversarial - use --adversarial", "contagem em gates fora do solver (so plan_room e contado)"] if a.obstacles
                            else ["obstaculos 10/100/1000 (cenas sinteticas) - use --obstacles", "geometria adversarial",
                                  "contagem de intersection/buffer/unary_union - use --obstacles"]),
           "budget": "nenhum: so a linha de base; budget de regressao por capability sai destes dados (FP-054 F3)"}
    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
