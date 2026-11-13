#!/usr/bin/env python3
"""
Unity's identifiers for scripts inside a DLL. A component of a class compiled into a DLL is saved as
{fileID: <id>, guid: <the DLL's guid>}, where <id> is the first 4 bytes (little-endian int32) of
MD4("s\\0\\0\\0" + namespace + class). Python's hashlib has no MD4 on OpenSSL 3, so it is written out here (RFC 1320).
"""

import struct


def md4(data):
    def rol(x, n):
        return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF

    length = len(data) * 8
    data = data + b"\x80" + b"\x00" * ((55 - len(data)) % 64) + struct.pack("<Q", length)
    a, b, c, d = 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476
    for i in range(0, len(data), 64):
        x = struct.unpack("<16I", data[i:i + 64])
        aa, bb, cc, dd = a, b, c, d
        for k in range(16):
            f = (b & c) | (~b & d)
            a, b, c, d = d, rol((a + f + x[k]) & 0xFFFFFFFF, (3, 7, 11, 19)[k % 4]), b, c
        for k in range(16):
            g = (b & c) | (b & d) | (c & d)
            a, b, c, d = d, rol((a + g + x[(k % 4) * 4 + k // 4] + 0x5A827999) & 0xFFFFFFFF, (3, 5, 9, 13)[k % 4]), b, c
        for k, j in enumerate((0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15)):
            h = b ^ c ^ d
            a, b, c, d = d, rol((a + h + x[j] + 0x6ED9EBA1) & 0xFFFFFFFF, (3, 9, 11, 15)[k % 4]), b, c
        a, b, c, d = [(v + w) & 0xFFFFFFFF for v, w in ((a, aa), (b, bb), (c, cc), (d, dd))]
    return struct.pack("<4I", a, b, c, d)


def script_file_id(namespace, name):
    """The fileID Unity gives class <namespace>.<name> inside a DLL."""
    return struct.unpack("<i", md4(("s\0\0\0" + namespace + name).encode("utf-8"))[:4])[0]
