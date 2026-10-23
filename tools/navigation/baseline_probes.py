"""FP-054 F0 — sondas de execucao: ambiente, suite nas duas escalas, performance e o cenario da mesa de jantar.

Somente medem: nenhuma regra muda, nada escreve em fixtures/ ou artifacts/. Cada subcomando imprime JSON (ou grava com --out).

    python -m tools.navigation.baseline_probes env [--gh] [--harness E:/Claude/apps/harness-app]
    python -m tools.navigation.baseline_probes tests                 # as 2 escalas, cada uma num processo proprio
    python -m tools.navigation.baseline_probes perf                  # 5 cenas sinteticas + planta_74 (subprocesso 0.0259)
    python -m tools.navigation.baseline_probes dining                # exige PT_TO_M=0.0259 (o `all` cuida disso)
    python -m tools.navigation.baseline_probes gate-probes           # sondas de falso PASS (escala padrao)
    python -m tools.navigation.baseline_probes all --out docs/reports/fp054/f0 [--gh]

Escala: a planta_74 so existe com PT_TO_M=0.0259, lido UMA vez no import de `core.scale`; por isso o que usa a planta roda
num subprocesso com a variavel ja definida, e o sintetico roda na escala padrao. Tempo: `time.perf_counter`, p50/p95 por
posto mais proximo (amostras pequenas: o numero de repeticoes vai junto). Memoria: pico do `tracemalloc` (alocacoes Python,
nao RSS — limitacao declarada). Sementes: toda cena sintetica nasce de `random.Random(seed)`; a busca da mesa nao sorteia.
"""
from __future__ import annotations

import argparse
import cProfile
import hashlib
import importlib.metadata as md
import io
import json
import os
import platform
import pstats
import random
import subprocess
import sys
import tempfile
import time
import tracemalloc
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from core.scale import M_TO_IN as M2IN  # fonte unica; PT_TO_M nao e usado no processo pai

ROOT = Path(__file__).resolve().parents[2]
PLANT_PT_TO_M = "0.0259"
PACKAGES = ("shapely", "numpy", "pypdfium2", "Pillow", "matplotlib", "pytest", "hypothesis", "ruff", "mcp")
PROTECTED = ("fixtures/", "projects/planta_74/source/")
SKIP_BLOCKED = ("não instalado", "not installed", "privil", "sketchup", "windows", "ruby", "docker", "ollama", "network")


def _git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace").stdout.strip()


def _pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return round(s[min(len(s) - 1, max(0, int(round(q * len(s) + 0.5)) - 1))], 4)


def _stats(samples: list[float]) -> dict:
    return {"n": len(samples), "p50_s": _pct(samples, 0.50), "p95_s": _pct(samples, 0.95),
            "min_s": round(min(samples), 4), "max_s": round(max(samples), 4)}


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=True, default=str).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------------------------------- ambiente
def hardware() -> dict:
    out = {"machine": platform.machine(), "processor": platform.processor(), "cpu_count": os.cpu_count()}
    if sys.platform == "win32":
        import ctypes

        class _Mem(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = _Mem()
        m.dwLength = ctypes.sizeof(_Mem)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            out["ram_gb"] = round(m.ullTotalPhys / 2 ** 30, 1)
    return out


def sketchup_info() -> dict:
    """Onde esta o SketchUp e qual versao (FileVersion do exe). Nao abre nada."""
    try:
        from tools.sketchup.process import SketchUp
        st = SketchUp().status()
    except Exception as e:  # noqa: BLE001 — sonda: ausencia vira BLOCKED, nao derruba o baseline
        return {"status": "BLOCKED", "reason": f"{type(e).__name__}: {e}"}
    info = {k: st.get(k) for k in ("platform_supported", "exe", "exe_found", "vray_exe_found")}
    info["running_instances"] = len(st.get("instances") or [])
    if st.get("exe_found") and sys.platform == "win32":
        r = subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-Item '{st['exe']}').VersionInfo.FileVersion"],
                           capture_output=True, text=True, timeout=30)
        info["file_version"] = r.stdout.strip() or None
    info["status"] = "AVAILABLE" if st.get("exe_found") else "BLOCKED"
    return info


def protected_hashes() -> list[dict]:
    """Arquivos protegidos: sha256 do disco e se o blob bate com o indice do git (= nao foi mexido)."""
    rows = []
    staged = {}
    for line in _git("ls-files", "-s", *PROTECTED).splitlines():
        meta, _, path = line.partition("\t")
        staged[path] = meta.split()[1]
    # .skp canonico (artifacts/<planta>/*.skp) e os mobiliados (artifacts/<planta>/furnished/*.skp) — regra de evidencia
    canon = [p for p in _git("ls-files", "artifacts/").splitlines() if p.endswith(".skp")
             and (p.count("/") == 2 or (p.count("/") == 3 and p.split("/")[2] == "furnished"))]
    for path in canon:
        meta = _git("ls-files", "-s", path).split()
        if meta:
            staged[path] = meta[1]
    for path, blob in sorted(staged.items()):
        disk = ROOT / path
        if not disk.is_file():
            rows.append({"path": path, "status": "MISSING"})
            continue
        work_blob = _git("hash-object", path)
        rows.append({"path": path, "sha256": hashlib.sha256(disk.read_bytes()).hexdigest(), "git_blob": blob,
                     "matches_index": work_blob == blob})
    return rows


def _gh(*args: str) -> list | dict | str:
    gh = os.environ.get("GH_EXE", r"C:\Program Files\GitHub CLI\gh.exe")
    env = {k: v for k, v in os.environ.items() if k != "GH_TOKEN"}
    r = subprocess.run([gh, *args], capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
    if r.returncode != 0:
        return {"error": r.stderr.strip()[:300]}
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.stdout.strip()


def environment(*, with_gh: bool = False, harness: Path | None = None) -> dict:
    out = {"schema_version": "fp054_baseline_environment.v1",
           "repo": {"head": _git("rev-parse", "HEAD"), "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
                    "origin_develop": _git("rev-parse", "origin/develop"),
                    "dirty_files": len(_git("status", "--porcelain").splitlines())},
           "python": {"version": platform.python_version(), "implementation": platform.python_implementation(),
                      "executable_is_venv": sys.prefix != sys.base_prefix},
           "os": {"system": platform.system(), "release": platform.release(), "version": platform.version()},
           "hardware": hardware(),
           "packages": {}, "sketchup": sketchup_info(), "protected_files": protected_hashes()}
    for name in PACKAGES:
        try:
            out["packages"][name] = md.version(name)
        except md.PackageNotFoundError:
            out["packages"][name] = None
    import shapely
    out["packages"]["geos"] = shapely.geos_version_string
    out["scale"] = {"PT_TO_M_env": os.environ.get("PT_TO_M"), "note": "PT_TO_M e lido no import de core.scale"}
    if harness is not None and (harness / ".git").exists():
        out["harness_app"] = {"path": str(harness), "remote": _git("remote", "get-url", "origin", cwd=harness),
                              "branch": _git("rev-parse", "--abbrev-ref", "HEAD", cwd=harness),
                              "develop": _git("rev-parse", "--short", "develop", cwd=harness),
                              "dirty_files": len(_git("status", "--porcelain", cwd=harness).splitlines())}
    if with_gh:
        out["open_prs"] = {repo: _gh("pr", "list", "--repo", repo, "--state", "open", "--json", "number,title,headRefName")
                           for repo in ("GFCDOTA/sketchup-mcp", "GFCDOTA/harness-app")}
    p = out["protected_files"]
    out["protected_summary"] = {"files": len(p), "all_match_index": all(r.get("matches_index") for r in p)}
    return out


# ------------------------------------------------------------------------------------------------------- testes
def parse_junit(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    counts: Counter = Counter()
    skip_reasons: Counter = Counter()
    failures, durations = [], []
    for tc in root.iter("testcase"):
        name = f"{tc.get('classname')}::{tc.get('name')}"
        t = float(tc.get("time") or 0)
        durations.append((t, name))
        skipped, failure, error = tc.find("skipped"), tc.find("failure"), tc.find("error")
        if failure is not None or error is not None:
            counts["failed" if failure is not None else "error"] += 1
            node = failure if failure is not None else error
            failures.append({"test": name, "message": (node.get("message") or "")[:300]})
        elif skipped is not None:
            msg = skipped.get("message") or ""
            if skipped.get("type") == "pytest.xfail":
                counts["xfailed"] += 1
                skip_reasons[f"XFAIL: {msg[:140]}"] += 1
            else:
                blocked = any(k in msg.lower() for k in SKIP_BLOCKED)
                counts["blocked_env" if blocked else "skipped"] += 1
                skip_reasons[("BLOCKED_ENV: " if blocked else "SKIP: ") + msg[:140]] += 1
        else:
            counts["passed"] += 1
    durations.sort(reverse=True)
    return {"counts": dict(sorted(counts.items())), "total": sum(counts.values()),
            "skip_reasons": dict(skip_reasons.most_common()), "failures": failures,
            "slowest": [{"test": n, "s": round(t, 3)} for t, n in durations[:15]]}


def run_suite(marker: str, *, pt_to_m: str | None) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PT_TO_M"}
    if pt_to_m:
        env["PT_TO_M"] = pt_to_m
    with tempfile.TemporaryDirectory() as td:
        junit = Path(td) / "junit.xml"
        cmd = [sys.executable, "-m", "pytest", "tests", "-q", "-m", marker, "-p", "no:cacheprovider", f"--junitxml={junit}"]
        t0 = time.perf_counter()
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        wall = time.perf_counter() - t0
        res = parse_junit(junit.read_text(encoding="utf-8")) if junit.is_file() else {"error": r.stdout[-2000:]}
    res.update(command=" ".join(["PT_TO_M=" + pt_to_m] if pt_to_m else []) + f" pytest tests -q -m \"{marker}\"",
               exit_code=r.returncode, wall_s=round(wall, 1), tail=r.stdout.strip().splitlines()[-1:])
    return res


def tests() -> dict:
    return {"schema_version": "fp054_baseline_tests.v1", "head": _git("rev-parse", "HEAD"),
            "python": platform.python_version(),
            "profiles": {"default_scale": run_suite("not planta74_scale", pt_to_m=None),
                         "planta74_scale": run_suite("planta74_scale", pt_to_m=PLANT_PT_TO_M)},
            "not_covered": ["L2 SketchUp real (fora do pytest; BLOCKED_L2 no CI Linux)", "L3 visual (Felipe)"]}


# --------------------------------------------------------------------------------------------- cenas sinteticas
SCENES = (  # (id, lado_m, n moveis, semente, faixa de tamanho do movel em m) — 1x = 4 m, 3x = 12 m
    ("S1_4m_n10", 4.0, 10, 1, (0.30, 0.80)),
    ("S2_4m_n100", 4.0, 100, 2, (0.10, 0.30)),
    ("S3_12m_n10", 12.0, 10, 3, (0.30, 0.80)),
    ("S4_12m_n100", 12.0, 100, 4, (0.30, 0.80)),
    ("S5_12m_n1000", 12.0, 1000, 5, (0.05, 0.20)),
)


def synthetic_room(side_m: float, *, doors: tuple[str, ...] = ("w_left", "w_right"), door_w_m: float = 0.80) -> dict:
    """Consensus minimo de um comodo quadrado (sem `source`: sem trava de planta), portas no meio das paredes pedidas."""
    from core.scale import PT_TO_M
    wt = 5.4
    s = side_m / PT_TO_M
    x0, y0, x1, y1 = 100.0, 100.0, 100.0 + s, 100.0 + s
    walls = [{"id": "w_bottom", "start": [x0, y0], "end": [x1, y0], "thickness": wt, "orientation": "h"},
             {"id": "w_top", "start": [x0, y1], "end": [x1, y1], "thickness": wt, "orientation": "h"},
             {"id": "w_left", "start": [x0, y0], "end": [x0, y1], "thickness": wt, "orientation": "v"},
             {"id": "w_right", "start": [x1, y0], "end": [x1, y1], "thickness": wt, "orientation": "v"}]
    mid = {"w_bottom": [(x0 + x1) / 2, y0], "w_top": [(x0 + x1) / 2, y1], "w_left": [x0, (y0 + y1) / 2],
           "w_right": [x1, (y0 + y1) / 2]}
    h = wt / 2
    return {"schema_version": "1.0.0", "wall_thickness_pts": wt, "plan_id": f"synthetic_{side_m:g}m",
            "walls": walls, "soft_barriers": [],
            "rooms": [{"id": "r_syn", "name": "SINTETICO", "polygon_pts": [[x0 + h, y0 + h], [x1 - h, y0 + h],
                                                                             [x1 - h, y1 - h], [x0 + h, y1 - h]],
                       "seed_pt": [(x0 + x1) / 2, (y0 + y1) / 2]}],
            "openings": [{"id": f"d_{w}", "wall_id": w, "kind_v5": "interior_door", "kind": "door", "center": mid[w],
                          "opening_width_pts": door_w_m / PT_TO_M} for w in doors]}


def synthetic_boxes(con: dict, n: int, seed: int, size_m: tuple[float, float]) -> list[dict]:
    """n moveis-caixa (0,75 m de altura) sorteados dentro do comodo, em polegadas (o quadro dos boxes do pipeline)."""
    from core.scale import PT_TO_IN
    rng = random.Random(seed)
    (ax, ay), (bx, by) = con["rooms"][0]["polygon_pts"][0], con["rooms"][0]["polygon_pts"][2]
    x0, y0, x1, y1 = ax * PT_TO_IN, ay * PT_TO_IN, bx * PT_TO_IN, by * PT_TO_IN
    out = []
    for i in range(n):
        w, d = (rng.uniform(*size_m) * M2IN for _ in range(2))
        cx, cy = rng.uniform(x0 + w / 2, x1 - w / 2), rng.uniform(y0 + d / 2, y1 - d / 2)
        corners = [[cx - w / 2, cy - d / 2], [cx + w / 2, cy - d / 2], [cx + w / 2, cy + d / 2], [cx - w / 2, cy + d / 2]]
        out.append({"module": f"syn_{i:04d}", "kind": "body", "corners": corners, "x0": cx - w / 2, "y0": cy - d / 2,
                    "x1": cx + w / 2, "y1": cy + d / 2, "z0_in": 0.0, "h_in": 0.75 * M2IN})
    return out


def _timed(fn, repeats: int, *, before=None) -> tuple[list[float], object]:
    samples, out = [], None
    for _ in range(repeats):
        if before:
            before()
        t0 = time.perf_counter()
        out = fn()
        samples.append(time.perf_counter() - t0)
    return samples, out


def _peak_mb(fn, *, before=None) -> float:
    if before:
        before()
    tracemalloc.start()
    try:
        fn()
        return round(tracemalloc.get_traced_memory()[1] / 2 ** 20, 2)
    finally:
        tracemalloc.stop()


def _call_counts(fn, names: tuple[str, ...]) -> dict:
    pr = cProfile.Profile()
    pr.enable()
    fn()
    pr.disable()
    st = pstats.Stats(pr)
    counts: Counter = Counter()
    for (file, _line, func), (cc, nc, *_rest) in st.stats.items():
        if func in names and ("circulation_gate" in file or "shapely" in file or "furniture_overlap_gate" in file):
            counts[func] += nc
    return dict(sorted(counts.items()))


def _gate_bench(con, boxes, room_id, repeats):
    from tools.validation import circulation_gate as cg
    from tools.validation.furniture_overlap_gate import _module_geom, pairwise_overlap
    run = lambda: cg.gate(con, boxes, room_id)  # noqa: E731
    clear = cg._eroded_regions.cache_clear
    cold, res = _timed(run, repeats, before=clear)
    warm, res2 = _timed(run, repeats)
    ov_samples, ov = _timed(lambda: pairwise_overlap(_module_geom(boxes)), max(1, repeats // 2))
    corr = res["checks"]["corredor_principal"]
    clear()
    calls = _call_counts(run, ("_bottleneck_width", "_connected_at_width", "_eroded_regions", "buffer", "difference",
                               "unary_union"))
    return {"gate_result": res["result"], "deterministic": _sha(res) == _sha(res2),
            "corridor": [{k: p.get(k) for k in ("status", "w_empty_m", "w_furnished_m", "erro") if k in p} for p in corr["portais"]],
            "circulation_gate_cold": _stats(cold), "circulation_gate_warm": _stats(warm),
            "circulation_gate_peak_mb": _peak_mb(run, before=clear),
            "calls": calls,
            "overlap_gate": {**_stats(ov_samples), "modules": ov[2], "pairs": ov[2] * (ov[2] - 1) // 2,
                             "fails": len(ov[0]), "warns": len(ov[1])}}


def synthetic_perf() -> list[dict]:
    from core.scale import PT_TO_M
    out = []
    for sid, side, n, seed, size in SCENES:
        con = synthetic_room(side)
        boxes = synthetic_boxes(con, n, seed, size)
        repeats = 3 if n >= 1000 else 7
        row = {"scene": sid, "side_m": side, "n_furniture": n, "seed": seed, "size_range_m": list(size),
               "pt_to_m": PT_TO_M, "input_sha": _sha([con, boxes]), "repeats": repeats}
        row.update(_gate_bench(con, boxes, "r_syn", repeats))
        out.append(row)
    return out


# ------------------------------------------------------------------------------------------------- planta_74 real
def _plant_consensus() -> dict:
    from tools.furnish_apartment import CONSENSUS
    return json.loads(CONSENSUS.read_text("utf-8"))


def real_perf(profile_out: Path | None = None) -> dict:
    """Apartamento real (exige PT_TO_M=0.0259 no processo): furnish inteiro, cada brain, gates por comodo, perfil cProfile."""
    from shapely.geometry import Polygon

    from core.scale import PT_TO_IN
    from tools.furnish_apartment import BRAINS, collect_boxes
    from tools.room_type import classify_rooms
    from tools.rooms.dispatch import get_brain
    from tools.spatial_model import build_spatial_model
    from tools.validation import circulation_gate as cg
    from tools.validation.furniture_overlap_gate import _module_geom, pairwise_overlap
    from tools.validation.room_regression_diff import capture
    con = _plant_consensus()
    quiet = io.StringIO()
    stdout, sys.stdout = sys.stdout, quiet
    try:
        cold_t0 = time.perf_counter()
        boxes, summary = collect_boxes(con)
        cold = time.perf_counter() - cold_t0
        warm, _ = _timed(lambda: collect_boxes(con), 5)
        peak = _peak_mb(lambda: collect_boxes(con))
        rooms = []
        for r in classify_rooms(con):
            brain = get_brain(BRAINS, r["room_type"])
            row = {"room_id": r["id"], "name": r["name"], "type": r["room_type"], "brain": bool(brain)}
            if brain:
                t, (rb, rout) = _timed(lambda: brain(con, r["id"]), 5)
                row.update(brain=_stats(t), boxes=len(rb or []), result=(rout or {}).get("result"))
                ov_t, ov = _timed(lambda: pairwise_overlap(_module_geom(rb or [])), 3)
                row["overlap_gate"] = {**_stats(ov_t), "modules": ov[2], "fails": len(ov[0]), "warns": len(ov[1])}
            g_t, g = _timed(lambda: cg.gate(con, boxes, r["id"]), 3, before=cg._eroded_regions.cache_clear)
            corr = g["checks"]["corredor_principal"]["portais"]
            sm = build_spatial_model(con, r["id"])
            cell = Polygon([(x * PT_TO_IN, y * PT_TO_IN) for x, y in sm["_geom"]["cell"].exterior.coords])
            row["circulation_gate"] = {**_stats(g_t), "result": g["result"], "portals_detected": len(cg._portais(sm, cell)),
                                       "portal_error": next((p["erro"] for p in corr if "erro" in p), None),
                                       "failed_checks": sorted(k for k, v in g["checks"].items() if v["result"] != "PASS"),
                                       "corridor": [{k: p.get(k) for k in ("status", "w_empty_m", "w_furnished_m")}
                                                    for p in corr if "erro" not in p and p.get("w_empty_m") is not None]}
            rooms.append(row)
        snap_t0 = time.perf_counter()
        snap = capture()
        snap_s = time.perf_counter() - snap_t0
        if profile_out is not None:
            pr = cProfile.Profile()
            pr.enable()
            collect_boxes(con)
            pr.disable()
            buf = io.StringIO()
            pstats.Stats(pr, stream=buf).sort_stats("cumulative").print_stats(30)
            text = "\n".join(line.rstrip() for line in buf.getvalue().splitlines()
                             if line.strip() and not line.lstrip().startswith(("Ordered by", "List reduced")))
            text = text.replace(str(ROOT).replace("\\", "/"), "<repo>").replace(str(ROOT), "<repo>")
            profile_out.write_text(text + "\n", encoding="utf-8", newline="\n")
    finally:
        sys.stdout = stdout
    return {"fixture": "planta_74", "pt_to_m": PLANT_PT_TO_M, "boxes": len(boxes), "boxes_sha": _sha(boxes),
            "collect_boxes": {"cold_first_call_s": round(cold, 4), "warm": _stats(warm), "peak_mb": peak},
            "room_regression_snapshot": {"snapshot_sha256": snap.get("snapshot_sha256"), "capture_s": round(snap_s, 4)},
            "rooms": rooms, "summary": [list(s) for s in summary]}


# ------------------------------------------------------------------------------------------------ cena da mesa
def dining_trace() -> dict:
    """Reproduz a busca da mesa de jantar da sala (r002) e registra CADA posicao da grade: motivo de descarte antes do gate,
    veredito do gate com o check que reprovou, colisao com o arco da porta. O espiao so OBSERVA o `GateSession` (devolve o
    mesmo resultado); a prova e o hash da sala identico com e sem espiao (`living_sha_*`)."""
    import shapely
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union

    from core.scale import PT_TO_IN, PT_TO_M
    from tools.rooms.living import furnishing
    from tools.rooms.living.components import _dining_table_rect
    from tools.rooms.shared.furniture import _chair_parts
    from tools.rooms.shared.geometry import door_swing_polygons
    from tools.rooms.shared.parts import place_parts
    from tools.spatial_model import build_spatial_model
    from tools.validation import circulation_gate as cg
    if abs(PT_TO_M - float(PLANT_PT_TO_M)) > 1e-9:
        raise SystemExit("dining_trace exige PT_TO_M=0.0259 antes do import (use o subcomando `all`)")
    con, room_id = _plant_consensus(), "r002"
    quiet = io.StringIO()
    stdout, sys.stdout = sys.stdout, quiet
    try:
        plain, plain_out = furnishing.living_room_boxes(con, room_id)
        calls: list[dict] = []
        sessions: list[list] = []
        Real = cg.GateSession

        class Spy(Real):
            def __init__(self, c, base, rid):
                super().__init__(c, base, rid)
                self._sid = len(sessions)
                sessions.append(list(base))       # copia: o furnishing estende a MESMA lista depois da busca

            def check(self, extra, *, decide_only=False):
                res = super().check(extra, decide_only=decide_only)
                # so a BUSCA da mesa: decide_only + mesa no candidato (o gate final e o da mesa de centro nao entram)
                if decide_only and any(str(b.get("module", "")).startswith("Mesa de jantar") for b in extra):
                    full = res if res["result"] == "PASS" else super().check(extra)
                    top = unary_union([Polygon(b["corners"]) for b in extra
                                       if b.get("module") == "Mesa de jantar" and b.get("corners")])
                    failed = {k: v["result"] for k, v in full["checks"].items() if v["result"] != "PASS"}
                    portals = [p.get("status") for p in full["checks"]["corredor_principal"]["portais"] if "erro" not in p]
                    calls.append({"session": self._sid, "table_center_in": [round(top.centroid.x, 3), round(top.centroid.y, 3)],
                                  "result": res["result"], "decided_by": res.get("decided_by"), "failed_checks": failed,
                                  "portal_status": portals, "corridor_slack_m": cg.corridor_slack_m(full)})
                return res

        cg.GateSession = Spy
        try:
            spied, spied_out = furnishing.living_room_boxes(con, room_id)
        finally:
            cg.GateSession = Real
    finally:
        sys.stdout = stdout
    if not calls:
        raise SystemExit("a busca da mesa nao chamou o gate (layout mudou?) — nada a rastrear")
    base = sessions[calls[0]["session"]]

    # censo independente da grade (mesmas regras do furnishing; casado 1:1 com o espiao abaixo)
    sm = build_spatial_model(con, room_id)
    cell = Polygon([(x * PT_TO_IN, y * PT_TO_IN) for x, y in sm["_geom"]["cell"].exterior.coords])
    occ = [Polygon([(c[0], c[1]) for c in b["corners"]]) for b in base if b.get("corners")]
    occ_u = unary_union(occ) if occ else None
    if occ_u is not None:
        shapely.prepare(occ_u)
    swings = door_swing_polygons(con)
    room_swings = [Polygon([(x * PT_TO_IN, y * PT_TO_IN) for x, y in swings[o["id"]].exterior.coords])
                   for o in con.get("openings", []) if o["id"] in swings and o["wall_id"] in sm["_geom"]["room_walls"]]
    mw, mdp, gap = 1.00, 0.65, 0.30
    spots = [(sx, mdp / 2 + gap, (0.0, -1.0)) for sx in (-0.25, 0.25)] + [(sx, -(mdp / 2 + gap), (0.0, 1.0)) for sx in (-0.25, 0.25)]
    dtp, chair = _dining_table_rect(w=mw, d=mdp, top_rgb=(108, 80, 58), leg_rgb=(30, 30, 33)), _chair_parts()
    seats_per_chair = sum(p.get("kind") == "seat" for p in chair)

    def inside(x, y, margin):
        p = Point(x, y)
        return cell.contains(p) and cell.exterior.distance(p) >= margin

    def classify(cx, cy):
        if not inside(cx, cy, 20):
            return "REJECT_MARGIN_20IN", None
        fits = [(dx, dy, f) for dx, dy, f in spots if inside(cx + dx * M2IN, cy + dy * M2IN, 4)]
        if len(fits) * seats_per_chair != 2:
            return "REJECT_CHAIRS_NOT_2", None
        parts = list(place_parts(dtp, (cx, cy), (0.0, 1.0)))
        for dx, dy, f in fits:
            parts += place_parts(chair, (cx + dx * M2IN, cy + dy * M2IN), f)
        polys = [Polygon([(v[0], v[1]) for v in b["corners"]]) for b in parts if b.get("corners")]
        if occ_u is not None and unary_union(polys).intersection(occ_u).area > 50:
            return "REJECT_OVERLAP_GT_50IN2", None
        top = unary_union([Polygon(b["corners"]) for b in place_parts(dtp, (cx, cy), (0.0, 1.0)) if b.get("corners")])
        hit = any(top.intersection(sw).area > 1e-8 for sw in room_swings)
        return "GATE", hit

    bx0, by0, bx1, by1 = cell.bounds
    grid, gate_i = [], 0
    gate_calls = calls
    selected = False
    for cx in range(int(bx0) + 8, int(bx1) - 8, 6):
        if selected:
            break
        for cy in range(int(by0) + 8, int(by1) - 8, 6):
            reason, hit = classify(cx, cy)
            row = {"phase": "grid", "cx_in": cx, "cy_in": cy, "reason": reason}
            if reason == "GATE":
                g = gate_calls[gate_i]
                gate_i += 1
                row.update(gate=g["result"], decided_by=g["decided_by"], failed_checks=g["failed_checks"],
                           portal_status=g["portal_status"], swing_hit=hit, corridor_slack_m=g["corridor_slack_m"],
                           spy_center_in=g["table_center_in"])
                row["reason"] = ("PASS_BUT_DOOR_SWING" if g["result"] == "PASS" and hit else
                                 "SELECTED" if g["result"] == "PASS" else f"GATE_FAIL_{(g['decided_by'] or 'x').upper()}")
            grid.append(row)
            if row["reason"] == "SELECTED":          # a busca real para aqui (mesma regra do furnishing)
                selected = True
                break
    n_grid_gate = gate_i
    refine = [{"phase": "refine", "table_center_in": g["table_center_in"], "gate": g["result"],
               "decided_by": g["decided_by"], "failed_checks": g["failed_checks"], "corridor_slack_m": g["corridor_slack_m"]}
              for g in gate_calls[n_grid_gate:]]
    mapped = [r for r in grid if "spy_center_in" in r]
    aligned = all(abs(r["spy_center_in"][0] - r["cx_in"]) < 0.51 and abs(r["spy_center_in"][1] - r["cy_in"]) < 0.51
                  for r in mapped)
    decision = next((d for d in (plain_out.get("placement_decisions") or []) if d.get("candidate_id") == "mesa_de_jantar"), None)
    chosen = next((r for r in refine if r["gate"] == "PASS"), None) or next((r for r in grid if r["reason"] == "SELECTED"), None)
    return {"schema_version": "fp054_dining_trace.v1", "fixture": "planta_74", "room_id": room_id, "pt_to_m": PT_TO_M,
            "seed": None, "rng": "nenhum — grade deterministica de 6 in + refino em passos de 0,5 in ordenado por folga",
            "inputs": {"consensus_sha": _sha(con), "table_m": [mw, mdp], "chair_gap_m": gap, "grid_step_in": 6,
                       "refine_step_in": 0.5, "refine_radius_in": 6.0, "base_boxes": len(base),
                       "door_swings_in_room": len(room_swings)},
            "proof_spy_is_passive": {"living_sha_plain": _sha(plain), "living_sha_spied": _sha(spied),
                                     "identical": _sha(plain) == _sha(spied) and plain_out == spied_out},
            "census_aligned_with_spy": aligned and len(mapped) == n_grid_gate,
            "counts": {"grid_points": len(grid), "grid_by_reason": dict(sorted(Counter(r["reason"] for r in grid).items())),
                       "gate_calls_grid": n_grid_gate, "gate_calls_refine": len(refine),
                       "gate_calls_total": len(gate_calls)},
            "placement_decision": decision, "chosen": chosen, "grid": grid, "refine": refine}


# ------------------------------------------------------------------------------------------ sondas de falso PASS
def gate_probes() -> dict:
    """Cenas minimas que testam se o gate de circulacao APROVA o que deveria bloquear. So relatam: a F1 vira cada uma em
    teste vermelho -> verde. `expected` e o que a FP-054 BLOCO 3 exige; `observed` e o que o gate devolve hoje."""
    from tools.validation import circulation_gate as cg
    out = []

    def wall_of_boxes(con, axis_x: bool):
        (ax, ay), (bx, by) = con["rooms"][0]["polygon_pts"][0], con["rooms"][0]["polygon_pts"][2]
        from core.scale import PT_TO_IN
        x0, y0, x1, y1 = ax * PT_TO_IN, ay * PT_TO_IN, bx * PT_TO_IN, by * PT_TO_IN
        cx = (x0 + x1) / 2
        c = [[cx - 10, y0 - 5], [cx + 10, y0 - 5], [cx + 10, y1 + 5], [cx - 10, y1 + 5]]   # faixa de parede a parede
        return [{"module": "Estante", "kind": "body", "corners": c, "z0_in": 0.0, "h_in": 80.0}]

    one_door = synthetic_room(4.0, doors=("w_left",))
    res = cg.gate(one_door, wall_of_boxes(one_door, True), "r_syn")
    out.append({"id": "P1_one_portal_room_split_by_furniture", "expected": "BLOCKED_MISSING_INPUT (ou NOT_APPLICABLE explicito)",
                "observed": res["result"], "corridor_detail": res["checks"]["corredor_principal"]["portais"],
                "false_pass": res["result"] == "PASS"})
    zero = synthetic_room(4.0, doors=())
    res = cg.gate(zero, wall_of_boxes(zero, True), "r_syn")
    out.append({"id": "P2_zero_portals", "expected": "BLOCKED_MISSING_INPUT", "observed": res["result"],
                "corridor_detail": res["checks"]["corredor_principal"]["portais"], "false_pass": res["result"] == "PASS"})
    two = synthetic_room(4.0)
    res = cg.gate(two, wall_of_boxes(two, True), "r_syn")
    out.append({"id": "P3_two_portals_split_control", "expected": "FAIL", "observed": res["result"],
                "false_pass": res["result"] == "PASS"})
    # cadeira rotulada fora do vocabulario do gate ('Chair'/'Dining table'): mesa encostada na parede, cadeira sem folga
    from core.scale import PT_TO_IN
    (ax, ay) = two["rooms"][0]["polygon_pts"][0]
    x0, y0 = ax * PT_TO_IN, ay * PT_TO_IN

    def rect(module, kind, x, y, w, d):
        return {"module": module, "kind": kind, "corners": [[x, y], [x + w, y], [x + w, y + d], [x, y + d]],
                "z0_in": 0.0, "h_in": 30.0}
    for label, table_mod, chair_mod in (("P4_chair_named_pt", "Mesa de jantar", "Cadeira jantar"),
                                        ("P5_chair_named_en", "Dining table", "Chair")):
        boxes = [rect(table_mod, "top", x0 + 60, y0 + 18, 40, 26),           # mesa a 18 in da parede sul
                 rect(chair_mod, "seat", x0 + 70, y0 + 1, 17, 17)]          # cadeira colada na parede: 0 m atras
        res = cg.gate(two, boxes, "r_syn")
        chairs = res["checks"]["atras_das_cadeiras"]["cadeiras"]
        out.append({"id": label, "expected": "FAIL (cadeira sem 0,70 m atras e sem recuo)", "observed": res["result"],
                    "chairs_measured": len(chairs), "behind": res["checks"]["atras_das_cadeiras"]["result"],
                    "false_pass": res["checks"]["atras_das_cadeiras"]["result"] == "PASS"})
    return {"schema_version": "fp054_gate_probes.v1", "probes": out,
            "false_pass_ids": [p["id"] for p in out if p["false_pass"]]}


# ---------------------------------------------------------------------------------------------------------- CLI
def _plant_subprocess(sub: str, *extra: str) -> dict:
    env = {**os.environ, "PT_TO_M": PLANT_PT_TO_M}
    r = subprocess.run([sys.executable, "-m", "tools.navigation.baseline_probes", sub, *extra], cwd=ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"{sub} falhou:\n{r.stderr[-3000:]}")
    return json.loads(r.stdout)


def perf(profile_out: Path | None = None) -> dict:
    extra = ("--profile", str(profile_out)) if profile_out else ()
    return {"schema_version": "fp054_baseline_performance.v1", "head": _git("rev-parse", "HEAD"), "hardware": hardware(),
            "python": platform.python_version(), "timer": "time.perf_counter", "memory": "tracemalloc peak (Python, nao RSS)",
            "percentile": "posto mais proximo", "synthetic": synthetic_perf(), "planta_74": _plant_subprocess("perf-real", *extra)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("env", "tests", "perf", "perf-real", "dining", "gate-probes", "all"))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--gh", action="store_true")
    ap.add_argument("--harness", type=Path)
    ap.add_argument("--profile", type=Path)
    args = ap.parse_args(argv)

    def emit(name: str, obj: dict):
        text = json.dumps(obj, indent=1, ensure_ascii=False) + "\n"
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / name).write_text(text, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(text)

    if args.cmd == "env":
        emit("baseline_environment.json", environment(with_gh=args.gh, harness=args.harness))
    elif args.cmd == "tests":
        emit("baseline_tests.json", tests())
    elif args.cmd == "perf":
        emit("baseline_performance.json", perf(args.profile))
    elif args.cmd == "perf-real":
        sys.stdout.write(json.dumps(real_perf(args.profile), ensure_ascii=True))
    elif args.cmd == "dining":
        sys.stdout.write(json.dumps(dining_trace(), ensure_ascii=True))
    elif args.cmd == "gate-probes":
        emit("gate_probes.json", gate_probes())
    else:
        if not args.out:
            raise SystemExit("`all` exige --out")
        emit("baseline_environment.json", environment(with_gh=args.gh, harness=args.harness))
        emit("gate_probes.json", gate_probes())
        emit("dining_scenario_trace.json", _plant_subprocess("dining"))
        emit("baseline_performance.json", perf(args.out / "profile_collect_boxes.txt"))
        emit("baseline_tests.json", tests())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
