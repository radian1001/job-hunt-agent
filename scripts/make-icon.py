#!/usr/bin/env python3
"""Generate assets/dashboard.ico for the desktop shortcut. Stdlib only.

Design: a magnifying glass over score bars, in the dashboard's own palette —
"search jobs, score them". Shapes are drawn from signed-distance functions and
supersampled 4x, so edges come out smooth at every icon size.

    python scripts/make-icon.py
"""
import math
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "dashboard.ico")
SIZES = (256, 128, 64, 48, 32, 16)
SS = 4  # supersampling factor per axis

BG_DARK = (0x0f, 0x11, 0x15)
BG_PANEL = (0x1b, 0x20, 0x2b)
ACCENT = (0x4f, 0x8c, 0xff)
GOOD = (0x3f, 0xb9, 0x50)
GLASS = (0xe9, 0xed, 0xf5)


def rounded_rect_sd(x, y, cx, cy, hw, hh, r):
    """Signed distance to a rounded rectangle (negative inside)."""
    dx = abs(x - cx) - (hw - r)
    dy = abs(y - cy) - (hh - r)
    ox, oy = max(dx, 0.0), max(dy, 0.0)
    return math.hypot(ox, oy) + min(max(dx, dy), 0.0) - r


def capsule_sd(x, y, ax, ay, bx, by, r):
    """Signed distance to a thick line segment with round caps."""
    pax, pay = x - ax, y - ay
    bax, bay = bx - ax, by - ay
    denom = bax * bax + bay * bay
    t = 0.0 if denom == 0 else max(0.0, min(1.0, (pax * bax + pay * bay) / denom))
    return math.hypot(pax - bax * t, pay - bay * t) - r


def over(dst, src, alpha):
    """Composite src over dst with the given coverage."""
    if alpha <= 0:
        return dst
    if alpha >= 1:
        return src
    return tuple(int(round(s * alpha + d * (1 - alpha))) for s, d in zip(src, dst))


def shade(u, v):
    """Colour at unit coordinates (0..1). Returns (r,g,b,a)."""
    # Card background.
    d = rounded_rect_sd(u, v, 0.5, 0.5, 0.5, 0.5, 0.19)
    if d > 0:
        return (0, 0, 0, 0)          # outside the rounded card: transparent
    col = BG_DARK
    # Slightly lighter inner panel so the icon reads as a UI surface.
    if rounded_rect_sd(u, v, 0.5, 0.5, 0.43, 0.43, 0.14) < 0:
        col = BG_PANEL

    # Score bars rising left to right, best match in green — the ranked list.
    base = 0.755
    bars = ((0.235, 0.585, ACCENT), (0.365, 0.470, ACCENT), (0.495, 0.330, GOOD))
    for bx, top, bcol in bars:
        if rounded_rect_sd(u, v, bx, (base + top) / 2,
                           0.050, (base - top) / 2, 0.024) < 0:
            col = bcol

    # Magnifying glass: ring plus handle, sitting over the bars.
    ring_c = (0.615, 0.415)
    ring_r, ring_w = 0.185, 0.052
    ring_d = abs(math.hypot(u - ring_c[0], v - ring_c[1]) - ring_r) - ring_w / 2
    handle_d = capsule_sd(u, v, 0.745, 0.565, 0.855, 0.675, 0.036)
    glass_d = min(ring_d, handle_d)
    if glass_d < 0:
        col = GLASS
    return (col[0], col[1], col[2], 255)


def render(size):
    rows = []
    step = 1.0 / (size * SS)
    for py in range(size):
        row = []
        for px in range(size):
            r = g = b = a = 0.0
            for sy in range(SS):
                for sx in range(SS):
                    u = (px * SS + sx + 0.5) * step
                    v = (py * SS + sy + 0.5) * step
                    cr, cg, cb, ca = shade(u, v)
                    w = ca / 255.0
                    r += cr * w
                    g += cg * w
                    b += cb * w
                    a += ca
            n = SS * SS
            a_avg = a / n
            if a_avg <= 0:
                row.append((0, 0, 0, 0))
            else:
                wsum = a / 255.0
                row.append((int(round(r / wsum)), int(round(g / wsum)),
                            int(round(b / wsum)), int(round(a_avg))))
        rows.append(row)
    return rows


def png_bytes(rows):
    h = len(rows)
    w = len(rows[0])
    raw = bytearray()
    for row in rows:
        raw.append(0)  # filter type 0
        for px in row:
            raw.extend(px)

    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def main():
    images = [png_bytes(render(s)) for s in SIZES]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in zip(SIZES, images):
        dim = 0 if size >= 256 else size          # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    with open(OUT, "wb") as f:
        f.write(header + entries + blobs)
    print(f"wrote {os.path.relpath(OUT, ROOT)} "
          f"({len(header + entries + blobs)} bytes, sizes {', '.join(map(str, SIZES))})")


if __name__ == "__main__":
    main()
