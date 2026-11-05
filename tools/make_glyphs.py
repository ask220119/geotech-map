#!/usr/bin/env python3
"""Build MapLibre SDF glyph files (fonts/<name>/<start>-<end>.pbf) from a .ttf, so the map
needs no external font server (anvaka hosts his own glyphs too).

  python tools/make_glyphs.py /path/DejaVuSansCondensed.ttf "DejaVu Sans Condensed"

Covers Latin-1, Latin Extended-A (œ, Œ…) and general punctuation (…, –, ’), enough for EN/FR.
Requires: pip install freetype-py numpy scipy
"""
import sys
from pathlib import Path

import freetype
import numpy as np
from scipy.ndimage import distance_transform_edt

SIZE, BUFFER, RADIUS, CUTOFF = 24, 3, 8, 0.25
RANGES = [(0, 255), (256, 511), (8192, 8447)]
OVERSAMPLE = 4


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def zigzag(n):
    return (n << 1) ^ (n >> 31)


def field(num, wtype, payload):
    key = varint((num << 3) | wtype)
    if wtype == 0:
        return key + varint(payload)
    return key + varint(len(payload)) + payload


def sdf_glyph(face, code):
    if face.get_char_index(code) == 0:
        return None
    face.set_pixel_sizes(0, SIZE * OVERSAMPLE)
    face.load_char(chr(code), freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_NORMAL)
    g = face.glyph
    bm = g.bitmap
    adv = round(g.advance.x / 64 / OVERSAMPLE)
    left, top = g.bitmap_left / OVERSAMPLE, g.bitmap_top / OVERSAMPLE
    if bm.width == 0 or bm.rows == 0:
        return dict(id=code, w=0, h=0, left=0, top=0, adv=adv, bitmap=b"")
    img = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, : bm.width] > 127
    pad = (BUFFER + RADIUS) * OVERSAMPLE
    img = np.pad(img, pad)
    outside = distance_transform_edt(~img)
    inside = distance_transform_edt(img)
    dist = (outside - inside) / OVERSAMPLE  # px at target size, >0 outside
    w = int(np.ceil(bm.width / OVERSAMPLE))
    h = int(np.ceil(bm.rows / OVERSAMPLE))
    # sample the high-res distance field on the low-res grid (with buffer)
    ys = (np.arange(h + 2 * BUFFER) - BUFFER + 0.5) * OVERSAMPLE + pad - 0.5
    xs = (np.arange(w + 2 * BUFFER) - BUFFER + 0.5) * OVERSAMPLE + pad - 0.5
    sample = dist[np.clip(ys.round().astype(int), 0, dist.shape[0] - 1)][:, np.clip(xs.round().astype(int), 0, dist.shape[1] - 1)]
    val = np.clip(255 - 255 * (sample / RADIUS + CUTOFF), 0, 255).astype(np.uint8)
    return dict(id=code, w=w, h=h, left=round(left), top=round(top), adv=adv, bitmap=val.tobytes())


def encode(fontname, start, end, glyphs):
    body = field(1, 2, fontname.encode()) + field(2, 2, f"{start}-{end}".encode())
    for gl in glyphs:
        gb = field(1, 0, gl["id"])
        if gl["bitmap"]:
            gb += field(2, 2, gl["bitmap"])
        gb += field(3, 0, gl["w"]) + field(4, 0, gl["h"])
        gb += field(5, 0, zigzag(gl["left"])) + field(6, 0, zigzag(gl["top"] - SIZE + 4))
        gb += field(7, 0, gl["adv"])
        body += field(3, 2, gb)
    return field(1, 2, body)


def main(ttf, name, out_root="web/fonts"):
    face = freetype.Face(ttf)
    out = Path(out_root) / name
    out.mkdir(parents=True, exist_ok=True)
    for start, end in RANGES:
        glyphs = [g for g in (sdf_glyph(face, c) for c in range(start, end + 1)) if g]
        (out / f"{start}-{end}.pbf").write_bytes(encode(name, start, end, glyphs))
        print(f"{name} {start}-{end}: {len(glyphs)} glyphs")


if __name__ == "__main__":
    main(*sys.argv[1:])
