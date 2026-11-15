"""Dessine l'icone de Tulip Factures (tulipe blanche sur badge bleu).

La tete de tulipe est une silhouette lissee (algorithme de Chaikin) :
bien plus propre qu'une union de disques, et nette a toutes les tailles.

Sortie : PNG carre 1024x1024.
Le .ico est produit ensuite par make_ico.py.

Usage :
    python make_tulip_icon.py sortie.png [--preview-only]
"""
from __future__ import annotations

import sys

from PIL import Image, ImageDraw

SIZE = 1024
SS = 3  # supersampling interne

TOP = (59, 130, 246)     # #3B82F6
BOTTOM = (30, 64, 175)   # #1E40AF
WHITE = (255, 255, 255, 255)
CLEAR = (0, 0, 0, 0)

# Silhouette de la tete, sens horaire, en coordonnees 1024.
# Les deux points bas (462/562 , 470) forment les encoches entre petales.
HEAD = [
    (512, 668),
    (612, 622), (672, 538), (700, 432), (678, 324), (616, 262),
    (566, 298), (562, 432),
    (548, 312), (512, 224), (476, 312),
    (462, 432),
    (458, 298), (408, 262), (346, 324), (324, 432), (352, 538), (412, 622),
]


def chaikin(points, iterations: int = 4):
    """Adoucit un polygone ferme (coupe les coins)."""
    pts = list(points)
    for _ in range(iterations):
        out = []
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            out.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            out.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        pts = out
    return pts


def vertical_gradient(w: int, h: int, top, bottom) -> Image.Image:
    strip = Image.new("RGB", (1, h))
    px = strip.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        px[0, y] = (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
        )
    return strip.resize((w, h), Image.BICUBIC)


def _ellipse(size, angle=0.0, color=WHITE) -> Image.Image:
    w, h = size
    layer = Image.new("RGBA", (w, h), CLEAR)
    ImageDraw.Draw(layer).ellipse([0, 0, w - 1, h - 1], fill=color)
    if angle:
        layer = layer.rotate(angle, expand=True, resample=Image.BICUBIC)
    return layer


def _paste(canvas, shape, center) -> None:
    canvas.alpha_composite(
        shape,
        (int(round(center[0] - shape.width / 2)), int(round(center[1] - shape.height / 2))),
    )


def build(with_bg: bool = True) -> Image.Image:
    s = SIZE * SS
    k = s / 1024.0

    canvas = Image.new("RGBA", (s, s), CLEAR)
    if with_bg:
        canvas.paste(vertical_gradient(s, s, TOP, BOTTOM), (0, 0))

    # ---------- feuilles (derriere la tige)
    leaf = (int(96 * k), int(206 * k))
    _paste(canvas, _ellipse(leaf, angle=42), (452 * k, 812 * k))
    _paste(canvas, _ellipse(leaf, angle=-42), (572 * k, 812 * k))

    # ---------- tige
    stem_w = 42 * k
    stem_h = 190 * k
    stem = Image.new("RGBA", (int(stem_w * 2), int(stem_h)), CLEAR)
    ImageDraw.Draw(stem).rounded_rectangle(
        [stem.width / 2 - stem_w / 2, 0,
         stem.width / 2 + stem_w / 2, stem.height - 1],
        radius=stem_w / 2, fill=WHITE,
    )
    _paste(canvas, stem, (512 * k, 748 * k))

    # ---------- tete de tulipe (silhouette lissee)
    smooth = [(x * k, y * k) for (x, y) in chaikin(HEAD, 4)]
    ImageDraw.Draw(canvas).polygon(smooth, fill=WHITE)

    return canvas.resize((SIZE, SIZE), Image.LANCZOS)


def build_small(with_bg: bool = True) -> Image.Image:
    """Version simplifiee pour les petites tailles (16 / 24 / 32 px).

    A 32 px, les feuilles et les encoches arrondies disparaissent : la
    tulipe devient une tache blanche. Cette variante ne garde que
    l'essentiel - une fleur seule, plus grosse, aux deux encoches
    franches - ce qui reste lisible une fois reduite.
    """
    s = SIZE * SS
    k = s / 1024.0

    canvas = Image.new("RGBA", (s, s), CLEAR)
    if with_bg:
        canvas.paste(vertical_gradient(s, s, TOP, BOTTOM), (0, 0))

    layer = Image.new("RGBA", (s, s), CLEAR)
    d = ImageDraw.Draw(layer)
    d.ellipse(
        [(512 - 232) * k, (470 - 258) * k, (512 + 232) * k, (470 + 258) * k],
        fill=WHITE,
    )

    # deux fentes en V, larges en haut et pointues en bas
    for sign in (-1, 1):
        gx = 512 + sign * 60
        d.polygon(
            [(gx - 52) * k, 218 * k,
             (gx + 52) * k, 218 * k,
             (gx + 9) * k, 486 * k,
             (gx - 9) * k, 486 * k],
            fill=CLEAR,
        )

    canvas.alpha_composite(layer)
    return canvas.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else "tulip-icon-1024.png"
    with_bg = "--bg-none" not in sys.argv

    img = build_small(with_bg=with_bg) if "--small" in sys.argv else build(with_bg=with_bg)
    img.save(out)
    print(f"ecrit : {out} ({img.size[0]}x{img.size[1]}"
          + (", version petites tailles)" if "--small" in sys.argv else ")"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
