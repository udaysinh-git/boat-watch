"""Push your own picture to the watch as a watch face background.

    python face.py picture.png [face_id] [image_id]

The picture gets scaled/cropped to 410x502. Uploading is ~2800 BLE writes,
give it a minute or two.
"""

import asyncio
import struct
import sys

from PIL import Image, ImageOps

from watch import Watch

W, H = 410, 502


def crc16(data):
    # CRC-16/XMODEM, written the same odd way the app does it
    c = 0
    for b in data:
        c = ((c << 8) | (c >> 8)) & 0xFFFF
        c ^= b
        c ^= (c & 0xFF) >> 4
        c ^= (c << 12) & 0xFFFF
        c ^= ((c & 0xFF) << 5) & 0xFFFF
    return c


def to_rgb565(path):
    img = Image.open(path).convert("RGBA")
    img = ImageOps.fit(img, (W, H), Image.LANCZOS)
    # the app flattens onto white; I'd rather flatten onto black
    bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
    img = Image.alpha_composite(bg, img).convert("RGB")

    out = bytearray(W * H * 2)
    for i, (r, g, b) in enumerate(img.getdata()):
        px = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out[2 * i] = px >> 8          # big endian on Realtek
        out[2 * i + 1] = px & 0xFF
    return bytes(out)


def java_int(x):
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x & 0x80000000 else x


def frames(cls, cmd, data, extra):
    """Same framing as the app's MultiPacketRequestGenerator.generateRequest
    (withSize=True, extraFirst=False). Quirks kept on purpose: the length
    ignores the 4 size bytes, and the 'checksum' is cls + cmd*len*datalen
    with Java int overflow and a signed cmd byte."""
    total = len(data) + len(extra) + 12
    signed_cmd = cmd - 256 if cmd > 127 else cmd
    ck = java_int(cls + signed_cmd * total * len(data))
    ck_lo, ck_hi = ck & 0xFF, (ck >> 8) & 0xFF
    count = -(-total // 146)

    head = bytes([0x7F, ck_lo, 0, 0]) + struct.pack("<H", count & 0xFFFF)
    head += bytes([ck_lo, ck_hi, cls, cmd]) + struct.pack("<H", total & 0xFFFF)
    head += struct.pack("<I", len(data)) + bytes(extra)
    first = 150 - len(head)
    yield head + data[:first]

    pos = first
    for seq in range(1, count):
        chunk = data[pos:pos + 146]
        pos += len(chunk)
        yield bytes([0x7F, ck_lo]) + struct.pack("<H", seq & 0xFFFF) + chunk


async def wait_for(w, prefix, timeout=10):
    while True:
        r = await asyncio.wait_for(w.replies.get(), timeout)
        if r.startswith(prefix):
            return r


async def push_image(w, image_id, pixels):
    extra = struct.pack("<HBBHH", image_id, 0, 0, H, W) + bytes([crc16(pixels) & 0xFF])
    sent = 0
    packets = list(frames(0x02, 0x94, pixels, extra))
    print(f"sending {len(pixels)} bytes in {len(packets)} packets")

    for n, pkt in enumerate(packets):
        await w.client.write_gatt_char("6e400002-b5a3-f393-e0a9-e50e24dcca9e", pkt, response=True)
        before = sent
        sent += len(pkt) - (12 if n == 0 else 4)
        # every 2 KB the watch wants to say "ok, keep going"
        if before // 2048 != sent // 2048 or n == len(packets) - 1:
            r = await wait_for(w, b"\x82\x94", timeout=15)
            if r[-1] != 1:
                raise RuntimeError(f"watch said {r.hex(' ')} at {sent} bytes")
        if n % 200 == 0:
            print(f"  {100 * n // len(packets)}%")
    print("  done")


async def main(path, face_id, image_id):
    pixels = to_rgb565(path)
    w = Watch()
    async with w:
        await w.send(0x02, 0x95, struct.pack("<H", image_id))          # free the slot
        await asyncio.sleep(0.5)
        await push_image(w, image_id, pixels)
        await w.send(0x02, 0x96, struct.pack("<HH", face_id, image_id))  # use it as bg
        await w.send(0x02, 0x8F, struct.pack("<H", face_id))             # switch to that face


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    asyncio.run(main(a[0], int(a[1]) if len(a) > 1 else 0, int(a[2]) if len(a) > 2 else 0))
