"""Construit un fichier .ico multi-tailles a partir d'une image carree.

Usage :
    python make_ico.py source.png sortie.ico
    python make_ico.py source.png sortie.ico --radius 0.22 --no-mask
    python make_ico.py source.png sortie.ico --preview
    python make_ico.py grand.png sortie.ico --small-source petit.png

- recadre au centre en carre
- applique un masque "squircle" (coins arrondis) avec anti-aliasing
- exporte 16, 24, 32, 48, 64, 128, 256 dans le .ico
- --preview ecrit aussi des PNG de controle a cote du .ico
- --small-source utilise un dessin simplifie pour 16/24/32 px : a ces
  tailles un dessin detaille devient une tache, alors qu'un dessin
  epure reste lisible. Les deux sources sont independantes.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

from PIL import Image, ImageDraw

SIZES = [16, 24, 32, 48, 64, 128, 256]
SMALL_MAX = 32          # tailles servies par --small-source
BASE = 1024
SS = 4                  # supersampling du masque


def _center_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def _squircle_mask(size: int, radius_ratio: float) -> Image.Image:
    big = size * SS
    mask = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(mask)
    r = int(big * radius_ratio)
    d.rounded_rectangle([0, 0, big - 1, big - 1], radius=r, fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def _prepare(path: str, radius: float, apply_mask: bool) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    img = _center_square(img).resize((BASE, BASE), Image.LANCZOS)
    if apply_mask:
        img.putalpha(_squircle_mask(BASE, radius))
    return img


def _dib(img: Image.Image) -> bytes:
    """Encode une image RGBA en DIB (BITMAPINFOHEADER + pixels + masque AND).

    Format historique des .ico : c'est celui que Windows 7 attend pour les
    petites tailles. Le PNG n'est fiable que pour 128 px et au-dela.
    """
    s = img.size[0]
    px = img.load()

    xor = bytearray()
    for y in range(s - 1, -1, -1):          # lignes de bas en haut
        for x in range(s):
            r, g, b, a = px[x, y]
            xor += bytes((b, g, r, a))

    row_bytes = ((s + 31) // 32) * 4        # masque 1 bit/pixel, aligne sur 4 octets
    mask = bytearray(row_bytes * s)
    for y in range(s):
        src_y = s - 1 - y
        for x in range(s):
            if px[x, src_y][3] == 0:
                mask[y * row_bytes + (x // 8)] |= 0x80 >> (x % 8)

    header = struct.pack(
        "<IiiHHIIiiII",
        40,          # taille du BITMAPINFOHEADER
        s, s * 2,    # largeur, hauteur (x2 : pixels + masque)
        1, 32,       # plans, bits par pixel
        0,           # compression BI_RGB
        len(xor) + len(mask), 0, 0, 0, 0,
    )
    return header + bytes(xor) + bytes(mask)


def write_ico(frames, output: str) -> int:
    """Ecrit un .ico a partir d'une liste [(taille, image)].

    Les grandes tailles sont stockees en PNG (compact), les petites en DIB
    (compatibilite maximale, notamment Windows 7).
    """
    payloads = []
    for size, img in frames:
        small = img.resize((size, size), Image.LANCZOS)
        if size >= 128:
            import io as _io
            buf = _io.BytesIO()
            small.save(buf, format="PNG", optimize=True)
            payloads.append((size, buf.getvalue(), "PNG"))
        else:
            payloads.append((size, _dib(small), "DIB"))

    header = struct.pack("<HHH", 0, 1, len(payloads))
    offset = 6 + 16 * len(payloads)
    entries = b""
    body = b""
    for size, data, _kind in payloads:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        body += data
        offset += len(data)

    with open(output, "wb") as fh:
        fh.write(header + entries + body)

    print("contenu : " + ", ".join(f"{s}px {k}" for s, _d, k in payloads))
    return len(payloads)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("output")
    ap.add_argument("--radius", type=float, default=0.22,
                    help="rayon des coins, en fraction de la largeur (defaut 0.22)")
    ap.add_argument("--no-mask", action="store_true",
                    help="ne pas arrondir les coins")
    ap.add_argument("--small-source",
                    help="dessin simplifie pour les tailles <= 32 px")
    ap.add_argument("--preview", action="store_true",
                    help="ecrire des PNG de controle et une planche")
    args = ap.parse_args()

    if not os.path.isfile(args.source):
        print(f"ERREUR : source introuvable -> {args.source}")
        return 1

    img = _prepare(args.source, args.radius, not args.no_mask)
    print(f"source : {Image.open(args.source).size[0]}x{Image.open(args.source).size[1]}")
    if not args.no_mask:
        print(f"masque squircle applique (rayon {args.radius:.2f})")

    small = None
    if args.small_source:
        if not os.path.isfile(args.small_source):
            print(f"ERREUR : --small-source introuvable -> {args.small_source}")
            return 1
        small = _prepare(args.small_source, args.radius, not args.no_mask)
        print(f"petites tailles : dessin simplifie (<= {SMALL_MAX} px)")

    def source_for(size: int) -> Image.Image:
        return small if (small is not None and size <= SMALL_MAX) else img

    out_dir = os.path.dirname(os.path.abspath(args.output)) or "."
    os.makedirs(out_dir, exist_ok=True)

    count = write_ico([(s, source_for(s)) for s in SIZES], args.output)
    print(f"ecrit : {args.output}  ({os.path.getsize(args.output)} octets)")
    print(f"tailles : {', '.join(str(s) for s in SIZES)}  ({count} images)")

    if args.preview:
        stem = os.path.splitext(args.output)[0]
        for s in (16, 32, 48, 256):
            p = f"{stem}-{s}.png"
            source_for(s).resize((s, s), Image.LANCZOS).save(p)
            print(f"apercu : {p}")

        # planche de controle : toutes les tailles alignees sur damier
        pad = 16
        total_w = sum(SIZES) + pad * (len(SIZES) + 1)
        total_h = max(SIZES) + pad * 2
        sheet = Image.new("RGBA", (total_w, total_h), (255, 255, 255, 255))
        d = ImageDraw.Draw(sheet)
        for y in range(0, total_h, 8):
            for x in range(0, total_w, 8):
                if (x // 8 + y // 8) % 2 == 0:
                    d.rectangle([x, y, x + 7, y + 7], fill=(232, 232, 232, 255))
        x = pad
        for s in SIZES:
            sheet.alpha_composite(source_for(s).resize((s, s), Image.LANCZOS),
                                  (x, (total_h - s) // 2))
            x += s + pad
        p = f"{stem}-planche.png"
        sheet.save(p)
        print(f"apercu : {p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
