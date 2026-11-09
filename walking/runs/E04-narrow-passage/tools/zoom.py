"""Crop and enlarge part of a PNG (standard library + numpy only; my own viewing tool).

    python tools/zoom.py preview/contact_sheet.png out.png x0 y0 x1 y1 [scale]"""
import struct
import sys
import zlib

import numpy as np


def read_png(path):
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w = 8, b"", None
    while pos < len(data):
        n, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if typ == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
            assert depth == 8 and ctype in (2, 6), (depth, ctype)
            ch = 3 if ctype == 2 else 4
        elif typ == b"IDAT":
            idat += body
        pos += 12 + n
    raw = np.frombuffer(zlib.decompress(idat), dtype=np.uint8).reshape(h, 1 + w * ch)
    out = np.zeros((h, w * ch), dtype=np.int32)
    prev = np.zeros(w * ch, dtype=np.int32)
    for y in range(h):
        f, line = raw[y, 0], raw[y, 1:].astype(np.int32)
        if f == 0:
            cur = line
        elif f == 2:
            cur = (line + prev) & 255
        else:
            cur = np.zeros_like(line)
            for x in range(w * ch):
                a = cur[x - ch] if x >= ch else 0
                b = prev[x]
                c = prev[x - ch] if x >= ch else 0
                if f == 1:
                    pr = a
                elif f == 3:
                    pr = (a + b) // 2
                else:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                cur[x] = (line[x] + pr) & 255
        out[y] = cur
        prev = cur
    return out.reshape(h, w, ch)[:, :, :3].astype(np.uint8)


def write_png(path, img):
    h, w, _ = img.shape
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(h))

    def chunk(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
    open(path, "wb").write(png)


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    x0, y0, x1, y1 = (int(v) for v in sys.argv[3:7])
    sc = int(sys.argv[7]) if len(sys.argv) > 7 else 2
    img = read_png(src)[y0:y1, x0:x1]
    img = np.repeat(np.repeat(img, sc, axis=0), sc, axis=1)
    write_png(dst, np.ascontiguousarray(img))
    print("wrote", dst, img.shape)
