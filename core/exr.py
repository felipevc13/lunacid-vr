#!/usr/bin/env python3
"""
OpenEXR scanline images in plain Python (zlib only), for the lightmap pass: nothing to install.

Reads NONE, RLE, ZIPS and ZIP compression with HALF, FLOAT or UINT channels; writes the same (ZIP and FLOAT by
default, what `ffmpeg -c:v exr -format 2 -compression 3` wrote before). Planes come and go in the order
ffmpeg's gbrapf32le used: [G, B, R, A], each a flat list of width*height floats, top row first.
Tiled, deep and multi-part files, and PIZ/PXR24/B44/DWA compression, are refused with a clear message.
"""

import itertools
import operator
import struct
import zlib

NONE, RLE, ZIPS, ZIP = 0, 1, 2, 3
UINT, HALF, FLOAT = 0, 1, 2
NAMES = {0: "NONE", 1: "RLE", 2: "ZIPS", 3: "ZIP", 4: "PIZ", 5: "PXR24", 6: "B44", 7: "B44A", 8: "DWAA", 9: "DWAB"}
LINES = {NONE: 1, RLE: 1, ZIPS: 1, ZIP: 16}
SIZE = {UINT: 4, HALF: 2, FLOAT: 4}
CODE = {UINT: "I", HALF: "e", FLOAT: "f"}
MAGIC = b"\x76\x2f\x31\x01"
HALF_MAX = 65504.0


# ---------- the byte transforms ZIP and RLE share

_MINUS_128 = bytes((b - 128) & 255 for b in range(256))


def _unpredict(data):
    """t[i] = t[i-1] + d[i] - 128 (mod 256), done by C-level loops: a lightmap is 30-70 million bytes."""
    if not data:
        return bytearray()
    d = bytearray(bytes(data).translate(_MINUS_128))
    d[0] = data[0]
    return bytearray(map((255).__and__, itertools.accumulate(d)))


def _predict(data):
    if not data:
        return bytearray()
    data = bytes(data)
    out = bytearray(len(data))
    out[0] = data[0]
    diffs = map(operator.sub, memoryview(data)[1:], memoryview(data)[:-1])
    out[1:] = bytes(map((255).__and__, map((128).__add__, diffs)))
    return out


def _deinterleave(t):
    """The interleaved halves back to byte order: out[0::2] = first half, out[1::2] = second half."""
    out = bytearray(len(t))
    half = (len(t) + 1) // 2
    out[0::2] = t[:half]
    out[1::2] = t[half:]
    return out


def _interleave(raw):
    return bytearray(raw[0::2]) + bytearray(raw[1::2])


def _rle_decode(data):
    out = bytearray()
    i = 0
    while i < len(data):
        count = struct.unpack("b", data[i:i + 1])[0]
        i += 1
        if count < 0:
            out += data[i:i - count]
            i -= count
        else:
            out += bytes([data[i]]) * (count + 1)
            i += 1
    return out


def _rle_encode(data):
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        run = 1
        while i + run < n and data[i + run] == data[i] and run < 128:
            run += 1
        if run >= 3:
            out += struct.pack("b", run - 1) + bytes([data[i]])
            i += run
            continue
        start = i
        while i < n and i - start < 127:
            if i + 2 < n and data[i] == data[i + 1] == data[i + 2]:
                break
            i += 1
        out += struct.pack("b", -(i - start)) + data[start:i]
    return out


def _decompress(compression, data, expected):
    if len(data) == expected and compression != NONE:
        return bytearray(data)               # stored as is when compressing would not have helped
    if compression == NONE:
        return bytearray(data)
    if compression in (ZIP, ZIPS):
        t = zlib.decompress(data)
    elif compression == RLE:
        t = _rle_decode(data)
    else:
        raise ValueError("EXR compression %s is not supported" % NAMES.get(compression, compression))
    return _deinterleave(_unpredict(t))


def _compress(compression, raw):
    if compression == NONE:
        return bytes(raw)
    t = _predict(_interleave(raw))
    packed = zlib.compress(bytes(t), 6) if compression in (ZIP, ZIPS) else bytes(_rle_encode(t))
    return packed if len(packed) < len(raw) else bytes(raw)


# ---------- reading

def _header(data):
    if data[:4] != MAGIC:
        raise ValueError("not an OpenEXR file")
    flags = struct.unpack("<I", data[4:8])[0]
    if flags & 0x200:
        raise ValueError("tiled EXR files are not supported")
    if flags & 0x1800:
        raise ValueError("deep or multi-part EXR files are not supported")
    i, attrs = 8, {}
    while data[i] != 0:
        n = data.index(b"\0", i)
        name = data[i:n].decode()
        m = data.index(b"\0", n + 1)
        kind = data[n + 1:m].decode()
        size = struct.unpack("<i", data[m + 1:m + 5])[0]
        attrs[name] = (kind, data[m + 5:m + 5 + size])
        i = m + 5 + size
    return attrs, i + 1


def _channels(blob):
    chans, j = [], 0
    while blob[j] != 0:
        n = blob.index(b"\0", j)
        name = blob[j:n].decode()
        pixel, = struct.unpack("<i", blob[n + 1:n + 5])
        xs, ys = struct.unpack("<ii", blob[n + 9:n + 17])
        if xs != 1 or ys != 1:
            raise ValueError("subsampled EXR channels are not supported")
        chans.append((name, pixel))
        j = n + 17
    return chans


def read(path):
    """(width, height, {channel name: flat list of floats})."""
    with open(path, "rb") as fh:
        data = fh.read()
    attrs, pos = _header(data)
    compression = attrs["compression"][1][0]
    if compression not in LINES:
        raise ValueError("EXR compression %s is not supported (%s)" % (NAMES.get(compression, compression), path))
    chans = _channels(attrs["channels"][1])
    x0, y0, x1, y1 = struct.unpack("<4i", attrs["dataWindow"][1])
    w, h = x1 - x0 + 1, y1 - y0 + 1
    per_line = sum(SIZE[p] * w for _, p in chans)
    lines = LINES[compression]
    blocks = (h + lines - 1) // lines
    offsets = struct.unpack("<%dQ" % blocks, data[pos:pos + 8 * blocks])
    planes = {name: [0.0] * (w * h) for name, _ in chans}
    for off in offsets:
        y, size = struct.unpack("<ii", data[off:off + 8])
        first = y - y0
        count = min(lines, h - first)
        raw = _decompress(compression, data[off + 8:off + 8 + size], per_line * count)
        k = 0
        for row in range(first, first + count):
            for name, pixel in chans:
                n = SIZE[pixel] * w
                vals = struct.unpack("<%d%s" % (w, CODE[pixel]), raw[k:k + n])
                planes[name][row * w:(row + 1) * w] = [float(v) for v in vals] if pixel == UINT else vals
                k += n
    return w, h, planes


def read_gbra(path):
    """(width, height, [G, B, R, A]); a missing alpha reads as 1."""
    w, h, planes = read(path)
    one = [1.0] * (w * h)
    return w, h, [planes.get(c, one if c == "A" else [0.0] * (w * h)) for c in ("G", "B", "R", "A")]


# ---------- writing

def _attr(name, kind, value):
    return name.encode() + b"\0" + kind.encode() + b"\0" + struct.pack("<i", len(value)) + value


def write_gbra(path, w, h, planes, compression=ZIP, pixel=FLOAT):
    """Write [G, B, R, A] planes as an RGBA scanline EXR."""
    order = ["A", "B", "G", "R"]                       # EXR keeps channels sorted by name
    by_name = dict(zip(("G", "B", "R", "A"), planes))
    chlist = b"".join(c.encode() + b"\0" + struct.pack("<iB3xii", pixel, 0, 1, 1) for c in order) + b"\0"
    header = (MAGIC + struct.pack("<I", 2)
              + _attr("channels", "chlist", chlist)
              + _attr("compression", "compression", bytes([compression]))
              + _attr("dataWindow", "box2i", struct.pack("<4i", 0, 0, w - 1, h - 1))
              + _attr("displayWindow", "box2i", struct.pack("<4i", 0, 0, w - 1, h - 1))
              + _attr("lineOrder", "lineOrder", b"\0")
              + _attr("pixelAspectRatio", "float", struct.pack("<f", 1.0))
              + _attr("screenWindowCenter", "v2f", struct.pack("<ff", 0.0, 0.0))
              + _attr("screenWindowWidth", "float", struct.pack("<f", 1.0))
              + b"\0")
    lines = LINES[compression]
    blocks = (h + lines - 1) // lines
    chunks = []
    for b in range(blocks):
        first = b * lines
        raw = bytearray()
        for row in range(first, min(first + lines, h)):
            for c in order:
                vals = by_name[c][row * w:(row + 1) * w]
                if pixel == HALF:
                    vals = [max(-HALF_MAX, min(HALF_MAX, v)) for v in vals]
                raw += struct.pack("<%d%s" % (w, CODE[pixel]), *vals)
        packed = _compress(compression, raw)
        chunks.append(struct.pack("<ii", first, len(packed)) + packed)
    offsets, at = [], len(header) + 8 * blocks
    for c in chunks:
        offsets.append(at)
        at += len(c)
    with open(path, "wb") as fh:
        fh.write(header + struct.pack("<%dQ" % blocks, *offsets) + b"".join(chunks))
