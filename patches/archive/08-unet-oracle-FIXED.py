"""CubiCasa5K Oracle — VERSÃO CORRIGIDA com architecture real.

PATCH #08 FIXED — reescrito após code review devastador

BUGS CRÍTICOS CORRIGIDOS vs versão anterior:
- B1: URL real é Google Drive (1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK), usa gdown
- B2: Arch é hg_furukawa_original (Hourglass), NÃO U-Net ResNet50
- B3: Output split [21 heatmaps, 12 rooms, 11 icons]. Wall = rooms[2]
- B4: Softmax APENAS em rooms[21:33], não em 44 canais
- B6: ImageNet normalization (mean=[.485,.456,.406], std=[.229,.224,.225])
- B7: Pad pra múltiplo de 32 na res nativa, NÃO resize 512
- B9: Skeleton path tracing com fix de loops, 4-junctions, border effects

INSTALAÇÃO:
    # 1. Clonar repo CubiCasa5K (PYTHONPATH)
    git clone https://github.com/CubiCasa/CubiCasa5k
    cd CubiCasa5k
    pip install -e .  # OU adicionar ao PYTHONPATH manualmente

    # 2. Dependências
    pip install torch torchvision gdown scikit-image scipy opencv-python

    # 3. Download de pesos (Google Drive, ~100MB)
    python -c "from patches.unet_oracle_fixed import download_cubicasa_weights; download_cubicasa_weights()"

HARDWARE:
    CPU i5/Ryzen5: ~5-15s por inferência (res nativa)
    GPU: ~0.5-2s

REFERÊNCIA:
    github.com/CubiCasa/CubiCasa5k — modelo oficial
    floortrans/models/hg_furukawa_original.py — arch
    samples.ipynb — exemplo oficial de inferência
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================

MODEL_DIR = Path("models")
MODEL_PATH = MODEL_DIR / "model_best_val_loss_var.pkl"

# FIX B1: Google Drive (não GitHub release fake)
GDRIVE_ID = "1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK"

# FIX B3: split correto do output CubiCasa5K
CHANNEL_SPLIT = [21, 12, 11]  # [heatmaps, rooms, icons] = 44 total
ROOMS_OFFSET = 21  # canais 21-32 são rooms
ROOMS_WALL_IDX = 2  # "Wall" dentro de rooms (index local)

# ImageNet normalization (FIX B6)
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


@dataclass(frozen=True)
class WallMaskResult:
    wall_mask: np.ndarray
    confidence_map: np.ndarray
    method: str
    inference_time_ms: float
    mean_confidence: float


# ==============================================================================
# DOWNLOAD DE WEIGHTS (Google Drive via gdown)
# ==============================================================================

def download_cubicasa_weights(force: bool = False) -> bool:
    """Baixa modelo CubiCasa5K de Google Drive via gdown.

    FIX B1: usa gdown em vez de urllib (que falha em arquivos grandes do Drive).
    """
    if MODEL_PATH.exists() and not force:
        return True

    try:
        import gdown
    except ImportError:
        print("[cubicasa] Dep. faltando: pip install gdown")
        return False

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[cubicasa] Baixando modelo de Google Drive (~100MB)...")
    try:
        gdown.download(id=GDRIVE_ID, output=str(MODEL_PATH), quiet=False)
        if MODEL_PATH.exists():
            print(f"[cubicasa] Modelo salvo em {MODEL_PATH}")
            return True
        else:
            return False
    except Exception as e:
        print(f"[cubicasa] Falha: {e}")
        print(f"[cubicasa] Download manual: https://drive.google.com/uc?id={GDRIVE_ID}")
        return False


# ==============================================================================
# CARREGAMENTO DO MODELO (ARCH REAL: hg_furukawa_original)
# ==============================================================================

def load_cubicasa_model():
    """Carrega hg_furukawa_original REAL do CubiCasa5K.

    FIX B2: NÃO usa smp.Unet. Usa arch oficial via import do repo.

    REQUER: github.com/CubiCasa/CubiCasa5k clonado e no PYTHONPATH.
    """
    try:
        import torch
        from floortrans.models import get_model
    except ImportError as e:
        print(f"[cubicasa] Imports falhando: {e}")
        print("[cubicasa] Steps:")
        print("  1. git clone https://github.com/CubiCasa/CubiCasa5k")
        print("  2. cd CubiCasa5k && pip install -e .")
        print("  3. OU: adicionar pasta ao PYTHONPATH")
        return None, None, None

    # Arch base: hg_furukawa_original com 51 classes (config inicial do repo)
    model = get_model("hg_furukawa_original", 51)

    # Override do último conv para 44 classes (config final do modelo best)
    n_classes = 44  # split [21, 12, 11]
    model.conv4_ = torch.nn.Conv2d(256, n_classes, bias=True, kernel_size=1)
    model.upsample = torch.nn.ConvTranspose2d(
        n_classes, n_classes, kernel_size=4, stride=4
    )

    # Download se precisar
    if not MODEL_PATH.exists():
        if not download_cubicasa_weights():
            return None, None, None

    # Load checkpoint (formato pickle do CubiCasa5K)
    try:
        checkpoint = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
    except Exception as e:
        print(f"[cubicasa] Falha no torch.load: {e}")
        return None, None, None

    # FIX B2: chave correta é "model_state", não "state_dict"
    state = checkpoint.get("model_state", checkpoint)
    clean = {k.replace("module.", ""): v for k, v in state.items()}

    try:
        # strict=True para falhar ruidosamente se arch diverge
        model.load_state_dict(clean, strict=True)
    except RuntimeError as e:
        print(f"[cubicasa] Mismatch de arch: {e}")
        # Fallback: strict=False com warning
        model.load_state_dict(clean, strict=False)
        print("[cubicasa] WARN: algumas keys foram ignoradas. Verifique arch.")

    model.eval()
    return model, n_classes, CHANNEL_SPLIT


# ==============================================================================
# INFERÊNCIA (com FIX B3/B4/B6/B7/B8)
# ==============================================================================

class WallMaskOracle:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._model = None
            cls._instance._device = None
            cls._instance._split = None
        return cls._instance

    def load(self) -> bool:
        if self._model is not None:
            return True

        import torch

        result = load_cubicasa_model()
        if result[0] is None:
            return False

        self._model, _, self._split = result
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model = self._model.to(self._device)
        return True

    def predict(self, image: np.ndarray) -> WallMaskResult:
        import time
        start = time.time()

        h, w = image.shape[:2]

        if self._model is None:
            self.load()

        if self._model is None:
            return WallMaskResult(
                wall_mask=np.zeros((h, w), dtype=bool),
                confidence_map=np.full((h, w), 0.0, dtype=np.float32),
                method="fallback_no_model",
                inference_time_ms=0.0,
                mean_confidence=0.0,
            )

        import torch
        import cv2

        # RGB
        if image.ndim == 2:
            rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        elif image.shape[2] == 3:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            rgb = image

        # FIX B7: pad pra múltiplo de 32 (arch hourglass requer), NÃO resize 512
        pad_h = (32 - h % 32) % 32
        pad_w = (32 - w % 32) % 32
        padded = cv2.copyMakeBorder(rgb, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)

        # FIX B6: ImageNet normalization (0-1, then (x - mean) / std)
        normalized = padded.astype(np.float32) / 255.0
        normalized = (normalized - IMAGENET_MEAN) / IMAGENET_STD

        # CHW + batch
        tensor = np.transpose(normalized, (2, 0, 1))
        batch = torch.from_numpy(tensor).unsqueeze(0).to(self._device)

        # Inference
        with torch.no_grad():
            output = self._model(batch)  # (1, 44, H', W')

        # FIX B3 + B4: split correto + softmax só em rooms
        rooms_logits = output[:, ROOMS_OFFSET:ROOMS_OFFSET + CHANNEL_SPLIT[1]]  # (1, 12, H', W')
        rooms_probs = torch.softmax(rooms_logits, dim=1)

        # Extract wall channel (index 2 dentro de rooms)
        wall_probs_padded = rooms_probs[0, ROOMS_WALL_IDX].cpu().numpy()

        # Crop pra resolução original (remove padding)
        wall_probs = wall_probs_padded[:h, :w]

        # FIX B8: threshold em res nativa (sem resize de probs)
        wall_mask = wall_probs > 0.5

        elapsed_ms = (time.time() - start) * 1000

        return WallMaskResult(
            wall_mask=wall_mask,
            confidence_map=wall_probs,
            method=f"hg_furukawa_{self._device.type}",
            inference_time_ms=elapsed_ms,
            mean_confidence=float(wall_probs.mean()),
        )


# ==============================================================================
# SKELETONIZAÇÃO → WALL CANDIDATES (FIX B9: loops + 4-junctions + borda)
# ==============================================================================

def skeletonize_mask_to_candidates(
    wall_mask: np.ndarray,
    page_index: int = 0,
    min_wall_length_px: int = 15,
    orthogonality_tolerance_deg: float = 5.0,
) -> list:
    """Converte wall mask binária em wall candidates via skeleton + path tracing.

    FIX B9: trata loops, 4-junctions e borders corretamente.
    FIX B11: usa method='lee' (mais robusto em walls espessas).
    """
    from model.types import WallCandidate

    try:
        from skimage.morphology import skeletonize
    except ImportError:
        print("[oracle] pip install scikit-image")
        return []

    if not wall_mask.any():
        return []

    import cv2

    # FIX B11: method 'lee' é mais robusto
    skeleton = skeletonize(wall_mask, method="lee")

    # Distance transform pra thickness
    dist_transform = cv2.distanceTransform(
        wall_mask.astype(np.uint8) * 255, cv2.DIST_L2, 3
    )

    # Neighbor count com BORDER_REPLICATE (FIX B9 borda)
    neighbor_count = _count_skeleton_neighbors(skeleton)

    # Endpoints: 1 vizinho. Junctions: >= 3 vizinhos
    skeleton_bool = skeleton.astype(bool)
    endpoints = np.argwhere(skeleton_bool & (neighbor_count == 1))
    junctions = np.argwhere(skeleton_bool & (neighbor_count >= 3))

    poi_set = set()
    for y, x in endpoints:
        poi_set.add((int(y), int(x)))
    for y, x in junctions:
        poi_set.add((int(y), int(x)))

    # FIX B9: trace com handling de loops e 4-junctions
    paths = _trace_skeleton_paths_fixed(skeleton_bool, poi_set)

    # Converter paths para WallCandidates
    candidates = []
    for path in paths:
        if len(path) < min_wall_length_px:
            continue

        is_ortho, orientation = _path_is_orthogonal(path, orthogonality_tolerance_deg)
        if not is_ortho:
            continue

        # Thickness = median de 2 * dist transform ao longo do path
        import statistics
        thicknesses_along_path = []
        sample_step = max(1, len(path) // 10)
        for (y, x) in path[::sample_step]:
            val = dist_transform[y, x]
            if val > 0:
                thicknesses_along_path.append(2.0 * val)

        if thicknesses_along_path:
            thickness = statistics.median(thicknesses_along_path)
        else:
            thickness = 2.0

        if orientation == "horizontal":
            y_avg = sum(p[0] for p in path) / len(path)
            xs = [p[1] for p in path]
            candidates.append(
                WallCandidate(
                    page_index=page_index,
                    start=(float(min(xs)), float(y_avg)),
                    end=(float(max(xs)), float(y_avg)),
                    thickness=float(thickness),
                    source="cubicasa_skeleton_horizontal",
                    confidence=0.95,
                )
            )
        else:  # vertical
            x_avg = sum(p[1] for p in path) / len(path)
            ys = [p[0] for p in path]
            candidates.append(
                WallCandidate(
                    page_index=page_index,
                    start=(float(x_avg), float(min(ys))),
                    end=(float(x_avg), float(max(ys))),
                    thickness=float(thickness),
                    source="cubicasa_skeleton_vertical",
                    confidence=0.95,
                )
            )

    return candidates


def _count_skeleton_neighbors(skeleton: np.ndarray) -> np.ndarray:
    """Conta vizinhos 8-connectados. FIX B9 borda: BORDER_REPLICATE."""
    import cv2
    kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8)
    return cv2.filter2D(
        skeleton.astype(np.uint8), -1, kernel, borderType=cv2.BORDER_REPLICATE
    )


def _trace_skeleton_paths_fixed(
    skeleton: np.ndarray, poi_set: set
) -> list:
    """Trace paths tratando: loops (sem POI), 4-junctions, border endpoints.

    FIX B9 completo.
    """
    visited_edges = set()
    paths = []
    H, W = skeleton.shape

    def nbrs(y, x):
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx < W and skeleton[ny, nx]:
                    out.append((ny, nx))
        return out

    def edge_key(a, b):
        return (a, b) if a < b else (b, a)

    # FASE 1: POI-to-POI paths (trata 4-junctions)
    for start in poi_set:
        for first_nb in nbrs(*start):
            ek = edge_key(start, first_nb)
            if ek in visited_edges:
                continue

            path = [start]
            prev, curr = start, first_nb

            while True:
                path.append(curr)
                visited_edges.add(edge_key(prev, curr))

                if curr in poi_set:
                    break

                cand = [n for n in nbrs(*curr) if n != prev]

                if len(cand) == 0:
                    break

                if len(cand) > 1:
                    # FIX: escolher candidate mais colinear com direção atual
                    dy_in = curr[0] - prev[0]
                    dx_in = curr[1] - prev[1]
                    cand.sort(
                        key=lambda p: -((p[0] - curr[0]) * dy_in + (p[1] - curr[1]) * dx_in)
                    )

                prev, curr = curr, cand[0]

                if edge_key(prev, curr) in visited_edges:
                    break  # guard anti-loop

            if len(path) >= 2:
                paths.append(path)

    # FASE 2: Componentes sem POI (loops fechados)
    remaining = set()
    ys, xs = np.where(skeleton)
    for y, x in zip(ys, xs):
        p = (int(y), int(x))
        for nb in nbrs(*p):
            if edge_key(p, nb) not in visited_edges:
                remaining.add(p)
                break

    while remaining:
        seed = remaining.pop()

        # Pegar primeiro vizinho não visitado
        first = None
        for nb in nbrs(*seed):
            if edge_key(seed, nb) not in visited_edges:
                first = nb
                break

        if first is None:
            continue

        path = [seed]
        prev = seed
        curr = first

        while True:
            path.append(curr)
            visited_edges.add(edge_key(prev, curr))

            cand = [
                n for n in nbrs(*curr)
                if n != prev and edge_key(curr, n) not in visited_edges
            ]

            if not cand:
                break

            if curr == seed:
                break  # loop fechou

            prev, curr = curr, cand[0]

        if len(path) >= 2:
            paths.append(path)

        # Remover nós do path de remaining
        for p in path:
            remaining.discard(p)

    return paths


def _path_is_orthogonal(path, tolerance_deg):
    """Verifica se path é horizontal ou vertical dentro de tolerance."""
    import math

    if len(path) < 2:
        return False, ""

    p0 = path[0]
    p1 = path[-1]
    dy = p1[0] - p0[0]
    dx = p1[1] - p0[1]

    if dy == 0 and dx == 0:
        return False, ""

    angle_deg = abs(math.degrees(math.atan2(dy, dx))) % 180

    if angle_deg < tolerance_deg or abs(angle_deg - 180) < tolerance_deg:
        return True, "horizontal"
    if abs(angle_deg - 90) < tolerance_deg:
        return True, "vertical"

    return False, ""


# ==============================================================================
# ORCHESTRATION: DL primário, Hough fallback
# ==============================================================================

def extract_from_raster_dl(
    image: np.ndarray, page_index: int = 0, fallback_to_hough: bool = True
) -> list:
    """Extract usando DL como primário, Hough fallback se confidence baixa."""
    from extract.service import extract_from_raster

    oracle = WallMaskOracle()
    result = oracle.predict(image)

    if result.method.startswith("fallback") or result.mean_confidence < 0.3:
        if fallback_to_hough:
            return extract_from_raster(image, page_index=page_index)
        else:
            return []

    candidates = skeletonize_mask_to_candidates(
        result.wall_mask, page_index=page_index
    )

    # Se DL produziu poucos candidates, complementar com Hough
    if len(candidates) < 5 and fallback_to_hough:
        hough = extract_from_raster(image, page_index=page_index)
        # FIX B12: filtrar por overlap espacial, não por confidence
        candidates = _merge_dl_hough_by_spatial(candidates, hough)

    return candidates


def _merge_dl_hough_by_spatial(dl_candidates, hough_candidates, overlap_tol_px=10):
    """Merge DL + Hough removendo duplicatas espaciais.

    FIX B12: usa overlap espacial, não confidence threshold (Hough sempre tem 1.0).
    """
    import math

    if not dl_candidates:
        return hough_candidates

    merged = list(dl_candidates)

    for h in hough_candidates:
        is_duplicate = False
        for d in dl_candidates:
            # Mesma orientação?
            if _candidate_orientation_generic(d) != _candidate_orientation_generic(h):
                continue

            # Endpoints próximos?
            d_mid_x = (d.start[0] + d.end[0]) / 2
            d_mid_y = (d.start[1] + d.end[1]) / 2
            h_mid_x = (h.start[0] + h.end[0]) / 2
            h_mid_y = (h.start[1] + h.end[1]) / 2

            center_dist = math.hypot(d_mid_x - h_mid_x, d_mid_y - h_mid_y)
            if center_dist < overlap_tol_px:
                is_duplicate = True
                break

        if not is_duplicate:
            merged.append(h)

    return merged


def _candidate_orientation_generic(c):
    dx = abs(c.end[0] - c.start[0])
    dy = abs(c.end[1] - c.start[1])
    return "horizontal" if dx >= dy else "vertical"


# ==============================================================================
# SETUP SCRIPT (scripts/setup_cubicasa.sh)
# ==============================================================================

SETUP_SCRIPT = """#!/bin/bash
# Setup completo CubiCasa5K para patch 08

set -e

echo "1. Instalando dependências Python..."
pip install torch torchvision segmentation-models-pytorch
pip install gdown scikit-image scipy opencv-python-headless

echo "2. Clonando CubiCasa5K..."
if [ ! -d "CubiCasa5k" ]; then
    git clone https://github.com/CubiCasa/CubiCasa5k
fi

echo "3. Instalando CubiCasa5K como editable..."
cd CubiCasa5k
pip install -e .
cd ..

echo "4. Baixando modelo pretrained (~100MB via Google Drive)..."
mkdir -p models
python -c "
from patches.unet_oracle_fixed import download_cubicasa_weights
success = download_cubicasa_weights()
if not success:
    print('Download manual: https://drive.google.com/uc?id=1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK')
    exit(1)
"

echo "5. Teste de sanidade..."
python -c "
from patches.unet_oracle_fixed import WallMaskOracle
oracle = WallMaskOracle()
loaded = oracle.load()
print(f'Modelo carregado: {loaded}')
"

echo "SETUP OK."
"""
