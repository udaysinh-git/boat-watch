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


def build(picture, digits=None):
    t = bytearray(TEMPLATE.read_bytes())
    assert t[:2] == b"\x03\x00" and struct.unpack_from("<I", t, 2)[0] == len(t)
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
    ap.add_argument("--dry", action="store_true", help="just write diy_out.bin")
    a = ap.parse_args()

    digits = tuple(int(x) for x in a.digits.split(",")) if a.digits else None
    data = build(a.picture, digits)
    Path("diy_out.bin").write_bytes(data)
    print(f"built {len(data)} bytes")
    if not a.dry:
        asyncio.run(install(data))
