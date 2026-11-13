#!/usr/bin/env python3
"""
Pass: Baked Lightmap Import Type
--------------------------------
AssetRipper exports a scene's baked lightmaps (Assets/Scenes/<scene>/Lightmap-N_comp_*.exr) as
plain Default textures. On Android Unity then compresses the HDR colour map as RGBM (ETC2_RGBA8),
while the shaders decode lightmaps as double-LDR: HUB_01 came out about 5x too bright (white).
Marking the files with their lightmap texture types makes Unity encode them for the platform.

The directional maps (_comp_dir) come out of AssetRipper converted from sRGB to linear, as if they
were colours: the neutral direction 0.5 reads 0.21, which darkened walls and lit floors wrongly.
Their RGB is re-encoded to sRGB (alpha untouched) once (core/exr.py, no ffmpeg); a marker in the .meta
userData records it. The colour maps are darkened the same way, so when the profile names a
"lightmap_dump_dir" (EXRs the original game decoded on the GPU, tools/lightmap_dump) its
<scene>/Lightmap-N_comp_*.exr files replace AssetRipper's and no re-encoding is needed.

Without a dump (the public release: no PC game, no BepInEx) AssetRipper's maps are converted by formula,
measured against the game's dumps (docs/RELEASE_PLAN.md, tests/test_lightmap_formula.py): colour maps
linear_to_srgb(x) on RGB; direction maps linear_to_srgb(x) / alpha on RGB, alpha untouched; shadowmasks
as they are. A marker in the .meta userData records it, once.

Imported as DirectionalLightmap on Android, the direction map made the decode factor 2-4x too
big (HUB_01's floor brighter than its own lightmap). It is an 8-bit map on PC (BC7), so it is
converted to a plain PNG (same .meta and guid, Default type, no sRGB) and sampled as stored.
"""

import glob
import os
import re
import shutil
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import exr as exr_io  # noqa: E402

# Lightmap-N_comp_<kind>.exr -> TextureImporter textureType
TYPES = {"light": 6, "dir": 0, "shadowmask": 11}

def _metas(export_dir):
    pattern = os.path.join(export_dir, "Assets", "Scenes", "*", "Lightmap-*_comp_*.*.meta")
    for meta in sorted(glob.glob(pattern)):
        m = re.search(r"_comp_(\w+)\.(exr|png)\.meta$", meta)
        if m and m.group(1) in TYPES and (m.group(2) == "exr" or m.group(1) == "dir"):
            yield meta, TYPES[m.group(1)]

def _dir_exr(meta):
    return meta.endswith("_comp_dir.exr.meta")

def _dir_to_png(meta, converted=None):
    """Replace a direction EXR by an 8-bit PNG with the same .meta (and so the same guid).
    The PNG is written here: ffmpeg would apply a transfer curve to the float data. `converted` is
    (w, h, planes) already worked out (the formula), so they never go through ffmpeg's EXR encoder."""
    exr = meta[:-5]
    png = exr[:-4] + ".png"
    w, h, planes = converted if converted is not None else _read_exr(exr)
    g, b, r, a = planes
    rows = []
    for y in range(h):
        row = bytearray([0])  # filter: none
        for x in range(y * w, (y + 1) * w):
            row += bytes(min(255, max(0, int(v * 255 + 0.5))) for v in (r[x], g[x], b[x], a[x]))
        rows.append(bytes(row))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    with open(png, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))
    os.replace(meta, png + ".meta")
    os.remove(exr)
    return png + ".meta"

def _read_exr(exr):
    """(width, height, [g, b, r, a] float planes) of an EXR (core/exr.py: plain Python, nothing to install)."""
    return exr_io.read_gbra(exr)

def _wrong(meta, wanted):
    with open(meta, encoding="utf-8", errors="ignore") as f:
        m = re.search(r"^  textureType: (-?\d+)$", f.read(), re.M)
    return m is not None and int(m.group(1)) != wanted

GAMMA_MARK = "lunaport-dir-srgb"

def _dir_needs_gamma(meta):
    if not _dir_exr(meta):
        return False
    with open(meta, encoding="utf-8", errors="ignore") as f:
        return GAMMA_MARK not in f.read()

def _to_srgb(x):
    if x <= 0.0031308:
        return max(x, 0.0) * 12.92
    return 1.055 * x ** (1 / 2.4) - 0.055

def _restore_dir_gamma(exr):
    """Re-encode the RGB planes of a float EXR from linear to sRGB; alpha stays."""
    w, h, planes = exr_io.read_gbra(exr)
    planes = [[_to_srgb(v) for v in p] for p in planes[:3]] + [planes[3]]
    exr_io.write_gbra(exr, w, h, planes)

FORMULA_MARK = "lunaport-lightmap-formula"

def convert_by_formula(exr, kind):
    """AssetRipper's float EXR to what the game decodes: colour linear_to_srgb(RGB); direction
    linear_to_srgb(RGB) / alpha, alpha kept; shadowmask unchanged."""
    if kind not in ("light", "dir"):
        return
    w, h, planes = exr_io.read_gbra(exr)
    n = w * h
    alpha = planes[3]
    out = []
    for p in range(3):  # planes g, b, r, then a
        plane = [_to_srgb(v) for v in planes[p]]
        if kind == "dir":
            plane = [v / a if a > 1e-4 else v for v, a in zip(plane, alpha)]
        out.append(plane)
    planes = (w, h, out + [list(alpha)])
    if kind == "dir":
        # The direction map becomes a PNG from these planes (written as EXR, RGB would be premultiplied by alpha
        # by some encoders: ffmpeg's measured 0.6353 written, 0.5283 = 0.6353 x 0.8315 read back).
        return planes
    exr_io.write_gbra(exr, w, h, planes[2])
    assert n == len(out[0])
    return planes

def _kind(meta):
    m = re.search(r"_comp_(\w+)\.exr\.meta$", meta)
    return m.group(1) if m else None

def _needs_formula(meta, profile):
    """An AssetRipper EXR with no game dump, not converted yet."""
    if _dump(meta, profile) or not meta.endswith(".exr.meta") or _kind(meta) not in ("light", "dir"):
        return False
    with open(meta, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    return FORMULA_MARK not in text and GAMMA_MARK not in text

def _mark_formula(meta):
    with open(meta, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    text = re.sub(r"^  userData: ?(.*)$", lambda m: f"  userData: {FORMULA_MARK}", text, count=1, flags=re.M)
    with open(meta, "w", encoding="utf-8") as f:
        f.write(text)

def _mark(meta):
    with open(meta, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    text = re.sub(r"^  userData: ?(.*)$", lambda m: f"  userData: {GAMMA_MARK}", text, count=1, flags=re.M)
    with open(meta, "w", encoding="utf-8") as f:
        f.write(text)

def _dump(meta, profile):
    """The original game's decoded copy of this lightmap, if the profile has a dump of it."""
    root = (profile or {}).get("lightmap_dump_dir")
    if not root:
        return None
    exr = meta[:-5]
    if not exr.endswith(".exr"):
        return None
    path = os.path.join(root, os.path.basename(os.path.dirname(exr)), os.path.basename(exr))
    return path if os.path.exists(path) else None

def _differs(a, b):
    with open(a, "rb") as f1, open(b, "rb") as f2:
        return f1.read() != f2.read()

def detect(export_dir, profile=None):
    findings = []
    for meta, t in _metas(export_dir):
        rel = os.path.relpath(meta, export_dir)
        dump = _dump(meta, profile)
        if dump and _differs(dump, meta[:-5]):
            findings.append(f"{rel[:-5]} differs from the original game's dump")
            continue
        if _needs_formula(meta, profile):
            findings.append(f"{rel[:-5]} is AssetRipper's, not converted by formula")
        if _wrong(meta, t):
            findings.append(f"{rel} is not imported as textureType {t}")
        if _dir_needs_gamma(meta) and not _needs_formula(meta, profile):
            findings.append(f"{rel[:-5]} still holds linearised directions")
        if _dir_exr(meta):
            findings.append(f"{rel[:-5]} is not a plain PNG")
    return findings

def apply(export_dir, profile=None, dry_run=False):
    details = []
    for meta, t in _metas(export_dir):
        dump = _dump(meta, profile)
        if dump and _differs(dump, meta[:-5]):
            details.append(f"Replace {os.path.relpath(meta, export_dir)[:-5]} with the original game's dump")
            if not dry_run:
                shutil.copyfile(dump, meta[:-5])
                if meta.endswith("_comp_dir.exr.meta"):
                    _mark(meta)
        elif _needs_formula(meta, profile):
            details.append(f"Convert {os.path.relpath(meta, export_dir)[:-5]} by formula ({_kind(meta)})")
            if not dry_run:
                converted = convert_by_formula(meta[:-5], _kind(meta))
                _mark_formula(meta)
                if _kind(meta) == "dir":
                    meta = _dir_to_png(meta, converted)
        elif _dir_needs_gamma(meta):
            details.append(f"Restore sRGB directions in {os.path.relpath(meta, export_dir)[:-5]}")
            if not dry_run:
                _restore_dir_gamma(meta[:-5])
                _mark(meta)
        if _dir_exr(meta):
            details.append(f"Convert {os.path.relpath(meta, export_dir)[:-5]} to PNG")
            if not dry_run:
                meta = _dir_to_png(meta)
        if not _wrong(meta, t):
            continue
        details.append(f"Import {os.path.relpath(meta, export_dir)[:-5]} as textureType {t}")
        if not dry_run:
            with open(meta, encoding="utf-8", errors="ignore") as f:
                text = f.read()
            with open(meta, "w", encoding="utf-8") as f:
                f.write(re.sub(r"^  textureType: -?\d+$", f"  textureType: {t}", text, count=1, flags=re.M))
    return {"changes_applied": len(details), "details": details}

def verify(export_dir, profile=None):
    findings = detect(export_dir, profile)
    return {
        "passed": len(findings) == 0,
        "remaining_issues": len(findings),
        "details": findings
    }
