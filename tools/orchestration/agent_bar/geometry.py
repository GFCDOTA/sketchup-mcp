"""geometry.py — posicionamento/limites de janela, puro (sem Qt), testavel com varios monitores e escalas DPI.

Todas as coordenadas sao LOGICAS (as que o Qt usa: ja divididas pela escala DPI do monitor). `Rect` e a area util (availableGeometry:
exclui a barra de tarefas) de um monitor; pode ter origem negativa (monitor a esquerda/acima do principal)."""
from __future__ import annotations

from dataclasses import dataclass

MARGIN = 8


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def overlap(self, x: int, y: int, w: int, h: int) -> int:
        ox = max(0, min(self.right, x + w) - max(self.left, x))
        oy = max(0, min(self.bottom, y + h) - max(self.top, y))
        return ox * oy

    def distance2(self, x: int, y: int) -> int:
        dx = max(self.left - x, 0, x - self.right)
        dy = max(self.top - y, 0, y - self.bottom)
        return dx * dx + dy * dy


def pick_screen(screens: list[Rect], x: int, y: int, w: int, h: int) -> Rect:
    """Monitor com maior area de sobreposicao com a janela; sem sobreposicao => o mais proximo. Lista vazia => ValueError (nao inventa)."""
    if not screens:
        raise ValueError("nenhum monitor disponivel")
    best = max(screens, key=lambda s: s.overlap(x, y, w, h))
    if best.overlap(x, y, w, h) > 0:
        return best
    return min(screens, key=lambda s: s.distance2(x + w // 2, y + h // 2))


def clamp_window(x: int, y: int, w: int, h: int, area: Rect, margin: int = MARGIN) -> tuple[int, int]:
    """Posicao que mantem a janela inteira dentro da area util. Se for maior que a area, ancora no canto superior esquerdo
    (a barra de titulo, no topo, continua acessivel)."""
    max_x = area.right - w - margin
    max_y = area.bottom - h - margin
    nx = area.left + margin if max_x < area.left + margin else min(max(x, area.left + margin), max_x)
    ny = area.top + margin if max_y < area.top + margin else min(max(y, area.top + margin), max_y)
    return nx, ny


def fit_height(desired: int, area: Rect, margin: int = MARGIN, minimum: int = 60) -> int:
    """Altura final: o conteudo, limitado a area util (o excedente rola por dentro)."""
    return max(minimum, min(desired, area.height - 2 * margin))


def place_below(anchor_x: int, anchor_y: int, anchor_h: int, w: int, h: int, screens: list[Rect], gap: int = 6) -> tuple[int, int]:
    """Painel abaixo da barra; se nao couber embaixo, acima; sempre dentro do monitor onde a barra esta."""
    area = pick_screen(screens, anchor_x, anchor_y, 1, anchor_h)
    below = anchor_y + anchor_h + gap
    y = below if below + h + MARGIN <= area.bottom else anchor_y - h - gap
    return clamp_window(anchor_x, y, w, h, area)
