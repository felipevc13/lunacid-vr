#!/usr/bin/env python3
"""
Read the ORIGINAL compiled shaders of a Unity game (Direct3D 11 / DXBC) and print them as
readable pseudo-code, so a port's replacement shader can copy the exact formulas.

Input: the YAML of a Shader asset from AssetRipper (Settings: ShaderExportMode = Yaml), e.g. via
the AssetRipper web API: GET /Assets/Yaml?Path=...

  python3 dxbc_dump.py shader.yaml                    # list passes and variants
  python3 dxbc_dump.py shader.yaml --pass FORWARD --stage frag [--keywords DIRECTIONAL,LIGHTMAP_OFF]

The variant chosen is the one whose keyword set matches --keywords best (fewest extra keywords).
Constant-buffer reads are annotated with the property name from the program's RDEF chunk
(cb0[5].xyz -> _Color.xyz), textures and samplers likewise.
"""

import argparse
import re
import struct
import sys

# ---------------------------------------------------------------- YAML (just what we need)

def _hex_list(lines, i):
    out = []
    while i < len(lines) and lines[i].lstrip().startswith("- "):
        out.append(lines[i].strip()[2:])
        i += 1
    return out, i

def parse_yaml(text):
    lines = text.split("\n")
    blob_hex = None
    offsets = comp = decomp = None
    passes = []          # [{name, stages: {vert: [...], frag: [...]}, names: {idx: kw}}]
    cur = None
    stage = None
    name_map = {}
    i = 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if s.startswith("m_NameIndices:"):
            name_map = {}
            j = i + 1
            ind = len(ln) - len(ln.lstrip())
            while j < len(lines) and (len(lines[j]) - len(lines[j].lstrip())) > ind:
                m = re.match(r"\s*(\S+): (\d+)$", lines[j])
                if m:
                    name_map[int(m.group(2))] = m.group(1)
                j += 1
            cur = {"name": None, "stages": {}, "names": name_map}
            passes.append(cur)
            i = j
            continue
        if cur is not None and s.startswith("m_Name: ") and cur["name"] is None and ln.startswith("          m_Name"):
            cur["name"] = s[len("m_Name: "):]
        m = re.match(r"\s*prog(Vertex|Fragment|Geometry|Hull|Domain|RayTracing):", ln)
        if m and cur is not None:
            stage = {"Vertex": "vert", "Fragment": "frag"}.get(m.group(1), m.group(1).lower())
            cur["stages"].setdefault(stage, [])
        if s.startswith("m_BlobIndex:") and cur is not None and stage:
            cur["stages"][stage].append({"blob": int(s.split()[1]), "kw": []})
        if s.startswith("m_GlobalKeywordIndices:") and cur is not None and stage and cur["stages"][stage]:
            h = s.split(":", 1)[1].strip()
            idx = [struct.unpack("<H", bytes.fromhex(h[k:k + 4]))[0] for k in range(0, len(h), 4)]
            cur["stages"][stage][-1]["kw"] += [name_map.get(x, str(x)) for x in idx]
        if s.startswith("m_LocalKeywordIndices:") and cur is not None and stage and cur["stages"][stage]:
            h = s.split(":", 1)[1].strip()
            idx = [struct.unpack("<H", bytes.fromhex(h[k:k + 4]))[0] for k in range(0, len(h), 4)]
            cur["stages"][stage][-1]["kw"] += [name_map.get(x, str(x)) for x in idx]
        if s.startswith("offsets:"):
            offsets, i = _hex_list(lines, i + 1); continue
        if s.startswith("compressedLengths:"):
            comp, i = _hex_list(lines, i + 1); continue
        if s.startswith("decompressedLengths:"):
            decomp, i = _hex_list(lines, i + 1); continue
        if s.startswith("compressedBlob:"):
            blob_hex = s.split(":", 1)[1].strip()
        i += 1
    u32 = lambda h: struct.unpack("<I", bytes.fromhex(h))[0]
    blob = bytes.fromhex(blob_hex)
    return passes, blob, u32(offsets[0]), u32(comp[0]), u32(decomp[0])

def lz4_block(src, out_len):
    dst = bytearray()
    i = 0
    while i < len(src):
        tok = src[i]; i += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = src[i]; i += 1; lit += b
                if b != 255: break
        dst += src[i:i + lit]; i += lit
        if i >= len(src): break
        off = src[i] | (src[i + 1] << 8); i += 2
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[i]; i += 1; ml += b
                if b != 255: break
        ml += 4
        start = len(dst) - off
        for k in range(ml):
            dst.append(dst[start + k])
    assert len(dst) == out_len, (len(dst), out_len)
    return bytes(dst)

def programs(blob):
    """Unity 2020 blob: u32 count, then (offset, length, segment) per entry; each holds one DXBC."""
    n = struct.unpack_from("<I", blob, 0)[0]
    out = []
    for k in range(n):
        off, ln = struct.unpack_from("<II", blob, 4 + 12 * k)
        entry = blob[off:off + ln]
        d = entry.find(b"DXBC")
        if d < 0:
            out.append(None); continue
        size = struct.unpack_from("<I", entry, d + 24)[0]
        out.append((entry[d:d + size], entry[d + size:]))
    return out

def bindings(tail):
    """Unity's binding table after the DXBC: length-prefixed names, each followed by u32 fields
    (for constant-buffer members: index flags, byte offset; for textures: slot). Printed raw."""
    out = []
    i = 0
    while i + 4 <= len(tail):
        n = struct.unpack_from("<I", tail, i)[0]
        if 2 <= n <= 64 and i + 4 + n <= len(tail):
            name = tail[i + 4:i + 4 + n]
            if re.fullmatch(rb"[$A-Za-z_][A-Za-z0-9_]*", name):
                j = i + 4 + n
                vals = struct.unpack_from("<5I", tail, j) if j + 20 <= len(tail) else ()
                out.append("%s %s" % (name.decode(), list(vals)))
                i = j
                continue
        i += 1
    return out

# ---------------------------------------------------------------- DXBC

OPS = ("add and break breakc call callc case continue continuec cut default deriv_rtx deriv_rty "
       "discard div dp2 dp3 dp4 else emit emitthencut endif endloop endswitch eq exp frc ftoi ftou "
       "ge iadd if ieq ige ilt imad imax imin imul ine ineg ishl ishr itof label ld ld_ms log loop "
       "lt mad min max customdata mov movc mul ne nop not or resinfo ret retc round_ne round_ni "
       "round_pi round_z rsq sample sample_c sample_c_lz sample_l sample_d sample_b sqrt switch "
       "sincos udiv ult uge umul umad umax umin ushr utof xor").split()
DCL_FIRST = 88

def chunks(dx):
    n = struct.unpack_from("<I", dx, 28)[0]
    out = {}
    for k in range(n):
        off = struct.unpack_from("<I", dx, 32 + 4 * k)[0]
        tag = dx[off:off + 4].decode("ascii", "replace")
        size = struct.unpack_from("<I", dx, off + 4)[0]
        out[tag] = dx[off + 8:off + 8 + size]
    return out

def cstr(b, off):
    e = b.index(b"\0", off)
    return b[off:e].decode("ascii", "replace")

def parse_rdef(r):
    cb_count, cb_off, bind_count, bind_off = struct.unpack_from("<IIII", r, 0)
    binds = {}
    for k in range(bind_count):
        o = bind_off + 32 * k
        name_off, typ, _, _, _, slot, _, _ = struct.unpack_from("<IIIIIIII", r, o)
        binds[(typ, slot)] = cstr(r, name_off)
    cbs = {}
    for k in range(cb_count):
        o = cb_off + 24 * k
        name_off, var_count, var_off, size, _, _ = struct.unpack_from("<IIIIII", r, o)
        vars_ = []
        for v in range(var_count):
            vo = var_off + 24 * v
            vn, start, vsize, flags, _, _ = struct.unpack_from("<IIIIII", r, vo)
            vars_.append((start, vsize, cstr(r, vn)))
        cbs[cstr(r, name_off)] = vars_
    # cbuffer slot -> name via binds (type 0 = cbuffer)
    cb_slots = {slot: name for (typ, slot), name in binds.items() if typ == 0}
    return binds, cbs, cb_slots

COMP = "xyzw"

class Dis:
    def __init__(self, shex, rdef):
        self.t = struct.unpack_from("<%dI" % (len(shex) // 4), shex)
        self.binds, self.cbs, self.cb_slots = parse_rdef(rdef) if rdef else ({}, {}, {})

    def cbname(self, slot, reg, comps):
        name = self.cb_slots.get(slot)
        if not name: return None
        for start, size, vname in self.cbs.get(name, []):
            first = reg * 16 + (COMP.index(comps[0]) * 4 if comps else 0)
            if start <= first < start + size:
                base = (first - start) // 16
                suffix = "[%d]" % base if size > 16 else ""
                return vname + suffix
        return None

    def operand(self, i):
        tok = self.t[i]; i += 1
        ncomp = tok & 3
        sel = (tok >> 2) & 3
        typ = (tok >> 12) & 0xFF
        idim = (tok >> 20) & 3
        reps = [(tok >> 22) & 7, (tok >> 25) & 7, (tok >> 28) & 7]
        mod = ""
        if tok >> 31:
            ext = self.t[i]; i += 1
            if ext & 0x3F == 1:
                mod = {1: "-", 2: "|", 3: "-|"}.get((ext >> 6) & 0xFF, "")
        comps = ""
        if ncomp == 2:
            if sel == 0:
                m = (tok >> 4) & 15
                comps = "".join(COMP[k] for k in range(4) if m >> k & 1)
            elif sel == 1:
                comps = "".join(COMP[(tok >> (4 + 2 * k)) & 3] for k in range(4))
            else:
                comps = COMP[(tok >> 4) & 3]
        if typ == 4:  # immediate32
            n = 4 if ncomp == 2 else 1
            vals = self.t[i:i + n]; i += n
            fl = [struct.unpack("<f", struct.pack("<I", v))[0] for v in vals]
            txt = "(" + ", ".join(("%g" % f) if abs(f) < 1e9 and (v & 0x7F800000) else str(v) for f, v in zip(fl, vals)) + ")" if n > 1 else \
                  (("%g" % fl[0]) if (vals[0] & 0x7F800000) or vals[0] == 0 else str(vals[0]))
            return txt, i
        idx = []
        for d in range(idim):
            r = reps[d]
            if r == 0:
                idx.append(str(self.t[i])); i += 1
            elif r == 2:
                sub, i = self.operand(i); idx.append(sub)
            elif r == 3:
                base = self.t[i]; i += 1
                sub, i = self.operand(i); idx.append("%s + %d" % (sub, base))
            else:
                idx.append("?"); i += 1
        names = {0: "r", 1: "v", 2: "o", 3: "x", 6: "s", 7: "t", 8: "cb", 9: "icb", 12: "oDepth", 13: "null"}
        base = names.get(typ, "op%d" % typ)
        if typ == 8 and len(idx) == 2:
            txt = "cb%s[%s]" % (idx[0], idx[1])
            if idx[1].isdigit():
                n = self.cbname(int(idx[0]), int(idx[1]), comps)
                if n: txt = n
        elif typ in (6, 7) and idx:
            n = self.binds.get((3 if typ == 6 else 2, int(idx[0])))
            txt = n if n else base + idx[0]
        elif typ == 3 and len(idx) == 2:
            txt = "x%s[%s]" % (idx[0], idx[1])
        elif typ == 9:
            txt = "icb[%s]" % idx[0] if idx else "icb"
        else:
            txt = base + "".join(idx[:1]) + ("[%s]" % idx[1] if len(idx) > 1 else "")
        if comps: txt += "." + comps
        if mod == "-": txt = "-" + txt
        elif mod == "|": txt = "abs(" + txt + ")"
        elif mod == "-|": txt = "-abs(" + txt + ")"
        return txt, i

    def run(self):
        out = []
        i = 2  # version, length
        depth = 0
        while i < len(self.t):
            tok = self.t[i]
            op = tok & 0x7FF
            ln = (tok >> 24) & 0x7F
            if op == 53:  # customdata: length in next dword
                ln = self.t[i + 1]
                out.append("  " * depth + "// immediate constant buffer (%d dwords)" % (ln - 2))
                i += ln; continue
            if ln == 0: break
            end = i + ln
            if op >= DCL_FIRST:
                i = end; continue
            name = OPS[op] if op < len(OPS) else "op%d" % op
            sat = "_sat" if (tok >> 13) & 1 else ""
            j = i + 1
            if tok >> 31:
                while self.t[j] >> 31: j += 1
                j += 1
            ops = []
            while j < end:
                o, j = self.operand(j)
                ops.append(o)
            if name in ("endif", "endloop", "else"): depth = max(0, depth - 1)
            if name in ("if", "breakc", "retc", "discard", "continuec"):
                nz = "nz" if (tok >> 18) & 1 else "z"
                out.append("  " * depth + "%s_%s %s" % (name, nz, ", ".join(ops)))
            elif ops:
                out.append("  " * depth + "%s = %s%s(%s)" % (ops[0], name, sat, ", ".join(ops[1:])))
            else:
                out.append("  " * depth + name)
            if name in ("if", "loop", "else"): depth += 1
            i = end
        return out

def io_sig(ch, tag):
    c = ch.get(tag)
    if not c: return []
    n = struct.unpack_from("<I", c, 0)[0]
    out = []
    for k in range(n):
        o = 8 + 24 * k
        name_off, sem_idx, _, _, reg, mask, _ = struct.unpack_from("<IIIIIBB", c, o)
        out.append("%s%d%s -> reg %d mask %s" % (cstr(c, name_off), sem_idx, "", reg, "".join(COMP[b] for b in range(4) if mask >> b & 1)))
    return out

def dump(dx, tail=b""):
    ch = chunks(dx)
    shex = ch.get("SHEX") or ch.get("SHDR")
    lines = []
    lines.append("// inputs:  " + "; ".join(io_sig(ch, "ISGN")))
    lines.append("// outputs: " + "; ".join(io_sig(ch, "OSGN")))
    d = Dis(shex, ch.get("RDEF"))
    for cbn, vs in d.cbs.items():
        lines.append("// cbuffer %s: %s" % (cbn, ", ".join("%s@%d" % (n, s) for s, _, n in vs)))
    lines.append("// textures/samplers: " + ", ".join("%s:%s" % (k, v) for k, v in sorted(d.binds.items())))
    lines += ["// unity binding: " + b for b in bindings(tail)]
    lines += d.run()
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("yaml")
    ap.add_argument("--pass", dest="pass_name")
    ap.add_argument("--stage", default="frag")
    ap.add_argument("--keywords", default="")
    ap.add_argument("--blob", type=int)
    a = ap.parse_args()
    passes, cblob, off, clen, dlen = parse_yaml(open(a.yaml, encoding="utf-8", errors="ignore").read())
    blob = lz4_block(cblob[off:off + clen], dlen)
    progs = programs(blob)
    if a.blob is not None:
        print(dump(*progs[a.blob])); return
    if not a.pass_name:
        for p in passes:
            print("pass", p["name"])
            for st, subs in p["stages"].items():
                kws = sorted({" ".join(s["kw"]) for s in subs})
                print("  %s: %d variants, e.g. %s" % (st, len(subs), kws[:4]))
        return
    want = set(k for k in a.keywords.split(",") if k)
    for p in passes:
        if p["name"] != a.pass_name: continue
        subs = p["stages"].get(a.stage, [])
        best = min(subs, key=lambda s: (len(want - set(s["kw"])), len(set(s["kw"]) - want)))
        print("// pass %s %s keywords: %s (blob %d)" % (p["name"], a.stage, " ".join(best["kw"]), best["blob"]))
        print(dump(*progs[best["blob"]]))
        return
    sys.exit("pass not found")

if __name__ == "__main__":
    main()
