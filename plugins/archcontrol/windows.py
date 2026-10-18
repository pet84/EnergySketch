# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Window grid geometry, matching the Ruby tool's local axes and dimensions."""
from dataclasses import dataclass
import math

WINDOW_TYPES = ("OD", "OS", "ODN", "ODZ", "OX")


def window_material(name):
    return any(name == t or name.startswith(t + "-") for t in WINDOW_TYPES)


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _unit(v):
    length = math.sqrt(sum(x*x for x in v))
    if not math.isfinite(length) or length < 1e-12:
        raise ValueError("Plocha nemá platnou normálu.")
    return tuple(x / length for x in v)


@dataclass(frozen=True)
class Grid:
    cols: int = 1
    rows: int = 1
    width: float = 1.
    height: float = 1.
    gap_h: float = 2.
    gap_v: float = 1.5
    material: str = ""

    def __post_init__(self):
        if any(type(n) is not int or not 1 <= n <= 50 for n in (self.cols, self.rows)):
            raise ValueError("Počet řad i sloupců musí být celé číslo od 1 do 50.")
        if not all(math.isfinite(v) for v in (self.width, self.height, self.gap_h, self.gap_v)):
            raise ValueError("Rozměry a mezery musí být konečná čísla.")
        if min(self.width, self.height) <= 0:
            raise ValueError("Šířka i výška okna musí být větší než nula.")

    @property
    def size(self):
        return (self.cols*self.width + (self.cols-1)*self.gap_h,
                self.rows*self.height + (self.rows-1)*self.gap_v)

    def rectangles(self, center, normal):
        if len(center) != 3 or not all(math.isfinite(x) for x in center):
            raise ValueError("Neplatný bod vložení.")
        n = _unit(normal)
        if math.hypot(n[0], n[1]) < 1e-10:
            h, v = (1., 0., 0.), (0., 1., 0.)
        else:
            h = _unit(_cross(n, (0., 0., 1.)))
            v = _unit(_cross(h, n))
            if v[2] < 0:
                v = tuple(-x for x in v)
        total_w, total_h = self.size
        result = []
        for row in range(self.rows):
            for col in range(self.cols):
                x = -total_w/2 + col*(self.width+self.gap_h)
                y = -total_h/2 + row*(self.height+self.gap_v)
                result.append(tuple(tuple(center[i] + h[i]*dx + v[i]*dy for i in range(3))
                                    for dx, dy in ((x,y),(x+self.width,y),
                                                   (x+self.width,y+self.height),(x,y+self.height))))
        return result
