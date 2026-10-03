"""Build a KaHa "DIY" face file from a picture and install it on the watch.

    python diyface.py picture.png [--digits r,g,b] [--dry]

This is what the app's "Customise" screen does on the PRISM: take the bundled
ca3_diy_01.bin template, paint the picture over its 368x448 background and
240x280 preview, and send the whole file with 02 8E as face 996. The template
is KaHa's (res/raw in the APK), so it isn't in this repo.
"""

import argparse
import asyncio
import struct
from pathlib import Path

from PIL import Image, ImageOps

import face
from watch import Watch

TEMPLATE = Path(__file__).parent / "apk/studio_assets/kaha_templates/ca3_diy_01.bin"
FACE_ID = 996  # hard-coded in the app for this family


def entry(t, i):
    # image table: u32 offset, u16 w, u16 h, u32 size (bit 31 = has alpha)
    off, w, h, size = struct.unpack_from("<IHHI", t, 12 + 12 * i)
    return off, w, h, bool(size & 0x80000000)


def rgb565(r, g, b):
    v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return v >> 8, v & 0xFF


def paint(t, i, img):
    off, w, h, alpha = entry(t, i)
    assert not alpha
    # has to be exactly w x h or the rows come out sheared
    img = ImageOps.fit(img.convert("RGB"), (w, h), Image.LANCZOS)
    px = bytearray()
    for p in img.getdata():
        px += bytes(rgb565(*p))
    t[off:off + len(px)] = px


def tint(t, first, last, color):
    # digits/month names are [alpha, hi, lo] per pixel; keep alpha, swap the colour
    hi, lo = rgb565(*color)
    for i in range(first, last + 1):
        off, w, h, alpha = entry(t, i)
        assert alpha
        for p in range(off, off + w * h * 3, 3):
            t[p + 1], t[p + 2] = hi, lo


def shift_widgets(t, dx, dy):
    # widget records: 02 kind x:u16 y:u16 id n [n image indexes], after a 15 byte header
    table_len = struct.unpack_from("<H", t, 0x0A)[0]
    p, end = 0x0C + table_len + 15, entry(t, 0)[0]
    while p < end and t[p] == 0x02:
        x, y = struct.unpack_from("<HH", t, p + 2)
        struct.pack_into("<HH", t, p + 2, x + dx, y + dy)
        p += 8 + t[p + 7]


def grow_background(t, w, h):
    """Resize the background slot to w x h and shift everything after it.
    The watch rejects this (face 996 vanishes after upload). Moving the
    widgets alone gets rejected too, so the layout seems to be checked
    against the template. Kept to document the attempt."""
    off, ow, oh, _ = entry(t, 1)
    delta = (w * h - ow * oh) * 2
    table_len = struct.unpack_from("<H", t, 0x0A)[0]
    for i in range(table_len // 12):
        pos = 12 + 12 * i
        o, ew, eh, size = struct.unpack_from("<IHHI", t, pos)
        if i == 1:
            struct.pack_into("<IHHI", t, pos, o, w, h, w * h * 2)
        elif o > off:
            struct.pack_into("<I", t, pos, o + delta)
    shift_widgets(t, (w - ow) // 2, (h - oh) // 2)
    t[off + ow * oh * 2:off + ow * oh * 2] = bytes(delta)
    struct.pack_into("<I", t, 2, len(t))


def build(picture, digits=None, full=False):
    t = bytearray(TEMPLATE.read_bytes())
    assert t[:2] == b"\x03\x00" and struct.unpack_from("<I", t, 2)[0] == len(t)
    if full:
        grow_background(t, 410, 502)
    img = Image.open(picture)
    paint(t, 1, img)   # background
    paint(t, 0, img)   # preview the app shows in its list
    if digits:
        tint(t, 2, 33, digits)
    return bytes(t)


async def install(data):
    async with Watch() as w:
        await face.push(w, 0x8E, data, struct.pack("<H", FACE_ID), extra_first=True, ack_offset=6)
        await asyncio.sleep(1)
        await w.send(0x02, 0x0D)
        await w.send(0x02, 0x0F)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("picture")
    ap.add_argument("--digits", help="recolour the clock, e.g. 230,214,196")
    ap.add_argument("--full", action="store_true", help="try a 410x502 background (the watch rejects it)")
    ap.add_argument("--dry", action="store_true", help="just write diy_out.bin")
    a = ap.parse_args()

    digits = tuple(int(x) for x in a.digits.split(",")) if a.digits else None
    data = build(a.picture, digits, a.full)
    Path("diy_out.bin").write_bytes(data)
    print(f"built {len(data)} bytes")
    if not a.dry:
        asyncio.run(install(data))
