"""Remplace l'icone d'un fichier .exe (ou .dll) par celle d'un .ico.

Utilise les API Windows UpdateResource : aucune dependance externe,
pas besoin de recompiler ni de PyInstaller.

POINT CRITIQUE : les .exe PyInstaller "onefile" sont un programme Windows
suivi d'une ARCHIVE collee a la fin du fichier. UpdateResource reconstruit
le fichier et JETTE cette archive, ce qui casse l'application (elle ne
demarre plus). Ce script detecte le cas et remet l'archive en place :

    1. il coupe le fichier a la fin de la derniere section PE,
    2. il applique l'icone sur la partie PE seule,
    3. il recolle l'archive a la suite.

L'archive PyInstaller se repere a son marqueur MEI juste avant la fin ;
ses positions internes sont relatives, donc la recolle fonctionne.

Usage :
    python set_exe_icon.py application.exe mon-icone.ico
    python set_exe_icon.py application.exe --verify

Le fichier est modifie sur place : une copie .bak est creee a cote.
"""
from __future__ import annotations

import ctypes
import os
import struct
import sys
from ctypes import wintypes

RT_ICON = 3
RT_GROUP_ICON = 14
LOAD_LIBRARY_AS_DATAFILE = 0x00000002
GROUP_ID = 1

MEI_MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

k32.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
k32.BeginUpdateResourceW.restype = wintypes.HANDLE

k32.UpdateResourceW.argtypes = [
    wintypes.HANDLE, wintypes.LPVOID, wintypes.LPVOID,
    wintypes.WORD, wintypes.LPVOID, wintypes.DWORD,
]
k32.UpdateResourceW.restype = wintypes.BOOL

k32.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
k32.EndUpdateResourceW.restype = wintypes.BOOL

k32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
k32.LoadLibraryExW.restype = wintypes.HMODULE

k32.FindResourceW.argtypes = [wintypes.HMODULE, wintypes.LPVOID, wintypes.LPVOID]
k32.FindResourceW.restype = wintypes.HANDLE

k32.FreeLibrary.argtypes = [wintypes.HMODULE]
k32.FreeLibrary.restype = wintypes.BOOL


def _res(ident: int) -> ctypes.c_void_p:
    return ctypes.cast(ctypes.c_void_p(ident), wintypes.LPVOID)


# ---------------------------------------------------------------- PE / archive

def pe_image_end(data: bytes) -> int:
    """Retourne la fin de la derniere section PE (= debut de l'archive collee)."""
    if data[:2] != b"MZ":
        raise ValueError("ce fichier n'est pas un .exe Windows (pas de signature MZ)")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("en-tete PE introuvable")
    num_sec = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    sec_off = pe + 24 + opt_size

    end = 0
    for i in range(num_sec):
        base = sec_off + i * 40
        raw_size = struct.unpack_from("<I", data, base + 16)[0]
        raw_ptr = struct.unpack_from("<I", data, base + 20)[0]
        if raw_size:
            end = max(end, raw_ptr + raw_size)
    return end


def split_overlay(data: bytes):
    """Separe (partie PE, archive collee). archive = b'' si aucun overlay."""
    end = pe_image_end(data)
    if end > len(data):
        raise ValueError(f"en-tete PE incoherent (fin calculee {end} > taille {len(data)})")
    return data[:end], data[end:]


def has_archive(overlay: bytes) -> bool:
    return MEI_MAGIC in overlay[-1024:]


# ---------------------------------------------------------------- .ico

def parse_ico(path: str):
    """Retourne la liste des images d'un .ico (metadonnees + donnees)."""
    with open(path, "rb") as fh:
        raw = fh.read()

    if len(raw) < 6:
        raise ValueError("fichier .ico trop court")

    reserved, icon_type, count = struct.unpack("<HHH", raw[:6])
    if reserved != 0 or icon_type != 1:
        raise ValueError("ce n'est pas un fichier .ico valide")
    if count == 0:
        raise ValueError("le .ico ne contient aucune image")

    images = []
    for i in range(count):
        off = 6 + i * 16
        if off + 16 > len(raw):
            raise ValueError("en-tete .ico tronque")
        w, h, colors, rsv, planes, bits, size, offset = struct.unpack("<BBBBHHII", raw[off:off + 16])
        if offset + size > len(raw):
            raise ValueError("donnees .ico tronquees")
        images.append({
            "w": 0 if w == 256 else w,
            "h": 0 if h == 256 else h,
            "colors": colors,
            "planes": planes or 1,
            "bits": bits or 32,
            "size": size,
            "data": raw[offset:offset + size],
        })
    return images


def _patch_pe_file(path: str, images) -> None:
    """Applique les images d'icone sur un fichier PE autonome (sans archive)."""
    handle = k32.BeginUpdateResourceW(path, False)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        for idx, im in enumerate(images, start=1):
            buf = ctypes.create_string_buffer(im["data"], len(im["data"]))
            ok = k32.UpdateResourceW(handle, _res(RT_ICON), _res(idx), 0, buf, len(im["data"]))
            if not ok:
                raise ctypes.WinError(ctypes.get_last_error())

        group = struct.pack("<HHH", 0, 1, len(images))
        for idx, im in enumerate(images, start=1):
            group += struct.pack(
                "<BBBBHHIH",
                im["w"], im["h"], im["colors"], 0,
                im["planes"], im["bits"], im["size"], idx,
            )
        gbuf = ctypes.create_string_buffer(group, len(group))
        if not k32.UpdateResourceW(handle, _res(RT_GROUP_ICON), _res(GROUP_ID), 0, gbuf, len(group)):
            raise ctypes.WinError(ctypes.get_last_error())

        if not k32.EndUpdateResourceW(handle, False):
            raise ctypes.WinError(ctypes.get_last_error())
    except Exception:
        k32.EndUpdateResourceW(handle, True)  # annulation
        raise


def apply_icon(exe: str, ico: str) -> int:
    images = parse_ico(ico)
    print(f"icone : {len(images)} image(s) -> "
          + ", ".join(str(im["w"] or 256) + "px" for im in images))

    with open(exe, "rb") as fh:
        original = fh.read()

    pe_part, overlay = split_overlay(original)
    archive = has_archive(overlay)
    print(f"fichier      : {len(original)} octets")
    print(f"partie PE    : {len(pe_part)} octets")
    print(f"archive      : {len(overlay)} octets" + ("  (archive PyInstaller detectee)" if archive else ""))

    if overlay and not archive:
        print("ATTENTION : donnees trouvees apres le PE sans marqueur PyInstaller.")
        print("            Elles seront conservees telles quelles.")

    # sauvegarde
    bak = exe + ".bak"
    if not os.path.isfile(bak):
        with open(bak, "wb") as fh:
            fh.write(original)
        print(f"sauvegarde   : {bak}")
    else:
        print(f"sauvegarde   : {bak} (deja presente, conservee)")

    # on travaille sur une copie de la seule partie PE
    tmp = exe + ".pe-tmp"
    try:
        with open(tmp, "wb") as fh:
            fh.write(pe_part)

        _patch_pe_file(tmp, images)

        with open(tmp, "rb") as fh:
            patched_pe = fh.read()
    finally:
        if os.path.isfile(tmp):
            os.remove(tmp)

    print(f"PE patche    : {len(patched_pe)} octets "
          f"({'%+d' % (len(patched_pe) - len(pe_part))} par rapport a l'original)")

    final = patched_pe + overlay
    with open(exe, "wb") as fh:
        fh.write(final)

    print(f"resultat     : {len(final)} octets")
    if archive:
        ok = MEI_MAGIC in final[-1024:]
        print("archive recollee : " + ("OK" if ok else "ECHEC"))
        if not ok:
            raise RuntimeError("l'archive PyInstaller n'est plus a la fin du fichier")

    return len(images)


# ---------------------------------------------------------------- verification

def verify(exe: str) -> bool:
    mod = k32.LoadLibraryExW(exe, None, LOAD_LIBRARY_AS_DATAFILE)
    if not mod:
        print(f"impossible d'ouvrir {exe} : {ctypes.WinError(ctypes.get_last_error())}")
        return False
    try:
        grp = k32.FindResourceW(mod, _res(GROUP_ID), _res(RT_GROUP_ICON))
        ico = k32.FindResourceW(mod, _res(1), _res(RT_ICON))
        print(f"RT_GROUP_ICON id={GROUP_ID} : {'present' if grp else 'ABSENT'}")
        print(f"RT_ICON id=1            : {'present' if ico else 'ABSENT'}")

        with open(exe, "rb") as fh:
            data = fh.read()
        pe_part, overlay = split_overlay(data)
        print(f"partie PE    : {len(pe_part)} octets")
        print(f"archive      : {len(overlay)} octets "
              + ("(PyInstaller OK)" if has_archive(overlay) else "(aucune)"))
        return bool(grp and ico)
    finally:
        k32.FreeLibrary(mod)


def main() -> int:
    args = sys.argv[1:]
    if len(args) < 1:
        print(__doc__)
        return 2

    exe = args[0]
    if not os.path.isfile(exe):
        print(f"ERREUR : introuvable -> {exe}")
        return 1

    if "--verify" in args:
        return 0 if verify(exe) else 1

    ico = args[1] if len(args) > 1 else None
    if not ico or not os.path.isfile(ico):
        print("ERREUR : .ico introuvable")
        return 1

    apply_icon(exe, ico)
    ok = verify(exe)
    print("verification : " + ("OK" if ok else "ECHEC"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
