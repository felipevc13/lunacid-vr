#!/usr/bin/env python3
"""
Static Material/Shader Audit (read-only)
----------------------------------------
Finds materials whose (regenerated) shader no longer honours what the material asks for.
These bugs render fine in the editor's mind but show up on device as black quads, solid
blocks or missing detail, so catching them statically saves ~30 min per device round-trip.

Born from the Lunacid MainMenu bug: MenuPaint2 (alpha-masked quad 2.4 m in front of the
camera, _Cutoff 0.5) got an opaque stub without clip() and covered the whole scene in black.

Checks (severity):
  CUTOUT_LOST        high  material sets _Cutoff and its texture has real transparency,
                           but the shader neither clips nor blends
  TRANSPARENT_LOST   high  material is in the transparent queue (or Standard Fade/Transparent mode)
                           but the shader is opaque (no Blend, no clip)
  MISSING_SHADER     high  shader GUID not found in the project and not a Unity built-in
  TEXTURE_IGNORED    low   material assigns a texture slot the shader never declares
  BUILTIN_SHADER     info  material uses a Unity built-in shader by fileID (resolved at build time)

Texture transparency is measured by decoding a 64x64 downscale with ffmpeg when available;
without ffmpeg only the PNG colour type is used (alpha channel present = suspect).

Usage:
  python3 tools/audit_materials.py [export_dir] [--out report_basename] [--no-scenes]
Writes <out>.md and <out>.json (default: ./material_audit).
"""

import json
import os
import re
import shutil
import struct
import subprocess
import sys

GUID_RE = re.compile(r"guid:\s*([0-9a-f]{32})")
SHADER_REF_RE = re.compile(r"m_Shader:\s*\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-f]{32}))?")
BUILTIN_GUID_PREFIX = "0000000000000000"
IGNORED_SHADER_PREFIXES = ("Diag/",)
# Slots Standard-derived materials always serialize; never meaningful on their own.
GENERIC_TEX_SLOTS = {"_MainTex", "_BumpMap", "_DetailAlbedoMap", "_DetailMask", "_DetailNormalMap",
                     "_EmissionMap", "_MetallicGlossMap", "_OcclusionMap", "_ParallaxMap", "_SpecGlossMap"}


def _read(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def _meta_guid(meta_path):
    try:
        with open(meta_path, "r", encoding="utf-8", errors="ignore") as fh:
            m = GUID_RE.search(fh.read(600))
        return m.group(1) if m else None
    except OSError:
        return None


def index_assets(assets_dir, exts):
    """guid -> path for assets with the given extensions."""
    out = {}
    for root, _, files in os.walk(assets_dir):
        for f in files:
            if f.endswith(".meta") and f[:-5].lower().endswith(exts):
                g = _meta_guid(os.path.join(root, f))
                if g:
                    out[g] = os.path.join(root, f[:-5])
    return out


def parse_material(text):
    mat = {"name": None, "shader_file_id": None, "shader_guid": None, "queue": -1,
           "floats": {}, "textures": {}, "keywords": ""}
    m = re.search(r"m_Name:\s*(.*)", text)
    mat["name"] = m.group(1).strip() if m else None
    m = SHADER_REF_RE.search(text)
    if m:
        mat["shader_file_id"] = int(m.group(1))
        mat["shader_guid"] = m.group(2)
    m = re.search(r"m_CustomRenderQueue:\s*(-?\d+)", text)
    if m:
        mat["queue"] = int(m.group(1))
    m = re.search(r"m_ShaderKeywords:\s*(.*)", text)
    if m:
        mat["keywords"] = m.group(1).strip()

    tex_block = re.search(r"m_TexEnvs:\n(.*?)\n    m_(?:Ints|Floats):", text, re.S)
    if tex_block:
        for tm in re.finditer(r"- (\w+):\n\s+m_Texture:\s*\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-f]{32}))?",
                              tex_block.group(1)):
            if tm.group(3):
                mat["textures"][tm.group(1)] = tm.group(3)
        # serializedVersion 3 layout: "      _MainTex:\n        m_Texture: ..."
        for tm in re.finditer(r"\n\s{6}(\w+):\n\s+m_Texture:\s*\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-f]{32}))?",
                              "\n" + tex_block.group(1)):
            if tm.group(3):
                mat["textures"][tm.group(1)] = tm.group(3)
    float_block = re.search(r"m_Floats:\n(.*?)\n    m_Colors:", text, re.S)
    if float_block:
        for fm in re.finditer(r"(?:- )?(\w+):\s*(-?[\d.eE+-]+)\s*$", float_block.group(1), re.M):
            try:
                mat["floats"][fm.group(1)] = float(fm.group(2))
            except ValueError:
                pass
    return mat


def shader_traits(text):
    m = re.search(r'Shader\s+"([^"]+)"', text)
    props = set(re.findall(r"^\s*\[?[^\n(]*?(\w+)\s*\(\s*\"", text.split("SubShader", 1)[0], re.M))
    # Additive ForwardAdd passes (Blend One One) only add light; they do not make a shader transparent.
    passes = re.split(r"\bPass\s*\{", text)
    # passes[0] holds SubShader-level state (e.g. a shared "Blend One One"), which applies to every pass.
    base_passes = passes[:1] + [ps for ps in passes[1:] if '"ForwardAdd"' not in ps]
    blends = [b for ps in base_passes for b in re.findall(r"^\s*Blend\s+(\w+)", ps, re.M) if b.lower() != "off"]
    return {
        "name": m.group(1) if m else None,
        "clips": "clip(" in text or "discard" in text,
        "blends": bool(blends),
        "transparent_queue": bool(re.search(r'"Queue"\s*=\s*"(Transparent|AlphaTest)', text)),
        "props": props,
        "stub": "//DummyShaderTextExporter" in text,
    }


def png_has_alpha_channel(path):
    try:
        with open(path, "rb") as fh:
            head = fh.read(33)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        color_type = head[25]
        return color_type in (4, 6)
    except OSError:
        return None


def transparent_fraction(path, ffmpeg):
    """Fraction of pixels with alpha < 128 on a 64x64 downscale, or None if unknown."""
    if not ffmpeg:
        return None
    try:
        raw = subprocess.run([ffmpeg, "-v", "error", "-i", path, "-vf", "scale=64:64",
                              "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                             capture_output=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    if len(raw) != 64 * 64 * 4:
        return None
    return sum(1 for i in range(3, len(raw), 4) if raw[i] < 128) / 4096.0


def scene_usage(assets_dir, mat_guids):
    """material guid -> sorted list of scenes that reference it directly."""
    usage = {}
    for root, _, files in os.walk(assets_dir):
        for f in files:
            if f.endswith(".unity"):
                found = set(GUID_RE.findall(_read(os.path.join(root, f)))) & mat_guids
                for g in found:
                    usage.setdefault(g, []).append(f[:-6])
    return {g: sorted(v) for g, v in usage.items()}


def audit(export_dir, with_scenes=True, ffmpeg=None):
    assets = os.path.join(export_dir, "Assets")
    shaders = index_assets(assets, (".shader",))
    textures = index_assets(assets, (".png", ".tga", ".jpg", ".jpeg", ".psd", ".exr", ".tif", ".tiff"))
    materials = index_assets(assets, (".mat",))
    traits = {g: shader_traits(_read(p)) for g, p in shaders.items()}
    usage = scene_usage(assets, set(materials)) if with_scenes else {}
    alpha_cache = {}

    def tex_transparency(guid):
        if guid not in alpha_cache:
            p = textures.get(guid)
            if not p:
                alpha_cache[guid] = None
            elif p.lower().endswith(".png") and png_has_alpha_channel(p) is False:
                alpha_cache[guid] = 0.0
            else:
                frac = transparent_fraction(p, ffmpeg)
                if frac is None and p.lower().endswith(".png"):
                    frac = 1.0 if png_has_alpha_channel(p) else 0.0  # unknown amount: flag it
                alpha_cache[guid] = frac
        return alpha_cache[guid]

    findings = []
    for mguid, mpath in sorted(materials.items(), key=lambda kv: kv[1]):
        mat = parse_material(_read(mpath))
        rel = os.path.relpath(mpath, export_dir)
        base = {"material": mat["name"], "file": rel, "scenes": usage.get(mguid, [])}
        sguid = mat["shader_guid"]
        if sguid and sguid.startswith(BUILTIN_GUID_PREFIX):
            findings.append(dict(base, check="BUILTIN_SHADER", severity="info",
                                 detail="built-in shader fileID %s" % mat["shader_file_id"]))
            continue
        if not sguid or sguid not in traits:
            findings.append(dict(base, check="MISSING_SHADER", severity="high",
                                 detail="shader guid %s not in project" % sguid))
            continue
        t = traits[sguid]
        if t["name"] and t["name"].startswith(IGNORED_SHADER_PREFIXES):
            continue
        base["shader"] = t["name"]
        opaque = not t["clips"] and not t["blends"]

        cutoff = mat["floats"].get("_Cutoff", 0.0)
        main_tex = mat["textures"].get("_MainTex")
        if cutoff > 0.01 and main_tex and opaque:
            frac = tex_transparency(main_tex)
            if frac and frac > 0.02:
                findings.append(dict(base, check="CUTOUT_LOST", severity="high",
                                     detail="_Cutoff=%.2f, %.0f%% of _MainTex is transparent, shader neither clips nor blends"
                                     % (cutoff, frac * 100)))

        mode = mat["floats"].get("_Mode", 0.0)
        if opaque and (mat["queue"] >= 2450 or mode in (2.0, 3.0)):
            findings.append(dict(base, check="TRANSPARENT_LOST", severity="high",
                                 detail="queue=%d mode=%g but shader is opaque" % (mat["queue"], mode)))

        if not t["stub"]:
            for slot in sorted(set(mat["textures"]) - GENERIC_TEX_SLOTS - t["props"]):
                findings.append(dict(base, check="TEXTURE_IGNORED", severity="low",
                                     detail="texture slot %s not declared by shader" % slot))
    return findings


SEVERITY_ORDER = {"high": 0, "low": 1, "info": 2}


def write_report(findings, out_base, export_dir):
    with open(out_base + ".json", "w", encoding="utf-8") as fh:
        json.dump(findings, fh, indent=1)
    counts = {}
    for f in findings:
        counts[f["check"]] = counts.get(f["check"], 0) + 1
    lines = ["# Material audit", "", "Project: `%s`" % export_dir, "",
             "| check | count |", "|---|---|"]
    lines += ["| %s | %d |" % (k, v) for k, v in sorted(counts.items())]
    for sev in ("high", "low"):
        sel = sorted((f for f in findings if f["severity"] == sev),
                     key=lambda f: (f["check"], -len(f["scenes"]), f["file"]))
        if not sel:
            continue
        lines += ["", "## %s" % sev, "", "| check | material | shader | scenes | detail |", "|---|---|---|---|---|"]
        for f in sel:
            sc = ", ".join(f["scenes"][:6]) + (" +%d" % (len(f["scenes"]) - 6) if len(f["scenes"]) > 6 else "")
            lines.append("| %s | %s | %s | %s | %s |" % (f["check"], f["material"], f.get("shader", ""),
                                                          sc or "-", f["detail"]))
    builtin = {}
    for f in findings:
        if f["check"] == "BUILTIN_SHADER":
            builtin[f["detail"]] = builtin.get(f["detail"], 0) + 1
    if builtin:
        lines += ["", "## info: built-in shaders", "", "| shader | materials |", "|---|---|"]
        lines += ["| %s | %d |" % (k, v) for k, v in sorted(builtin.items(), key=lambda kv: -kv[1])]
    with open(out_base + ".md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return counts


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    export_dir = args[0] if args else _config_project()
    out = "material_audit"
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
        args = [a for a in args if a != out]
    findings = audit(export_dir, with_scenes="--no-scenes" not in argv, ffmpeg=shutil.which("ffmpeg"))
    counts = write_report(findings, out, export_dir)
    print(json.dumps(counts, indent=1))
    print("report: %s.md / %s.json" % (out, out))



def _config_project():
    """The project from the machine configuration (core/config.py), for running this pass by hand."""
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core import config
    return config.load()["project"]

if __name__ == "__main__":
    main(sys.argv[1:])
