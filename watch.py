"""Poke at a boAt PRISM watch over BLE, no boAt Crest app needed.

    python watch.py battery set_time vibrate
    python watch.py "notify:Title:some text" find
    python watch.py live sleep:5

Set WATCH_MAC if yours isn't my watch.
"""

import asyncio
import datetime
import os
import struct
import sys

from bleak import BleakClient, BleakScanner

MAC = os.environ.get("WATCH_MAC", "CB:56:00:25:EA:23")

# Nordic UART. Everything goes through these two.
TX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
RX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# Stuff I never want to send by accident: reset, power off, OTA, AGPS push,
# rewriting the MAC/serial, factory test mode, renaming, unbinding.
BLOCKED = (
    {(0x06, c) for c in range(256)}
    | {(0x09, c) for c in range(256)}
    | {(0x0A, c) for c in range(256)}
    | {(0x00, c) for c in (0x80, 0x83, 0x84, 0x85, 0x91, 0xAB)}
)


def frame(cls, cmd, payload=b""):
    # [class][cmd][total length incl. this 4 byte header, LE][payload], no checksum
    if (cls, cmd) in BLOCKED:
        raise ValueError(f"not sending {cls:02x} {cmd:02x}, it's on the blocklist")
    return bytes([cls, cmd]) + struct.pack("<H", 4 + len(payload)) + payload


class Watch:
    def __init__(self, mac=MAC):
        self.mac = mac
        self.replies = asyncio.Queue()

    async def __aenter__(self):
        dev = await BleakScanner.find_device_by_address(self.mac, timeout=20)
        if not dev:
            sys.exit("can't see the watch. is it still connected to the phone?")
        self.client = BleakClient(dev, timeout=30)
        await self.client.connect()
        await self.client.start_notify(RX, self._on_data)
        return self

    async def __aexit__(self, *exc):
        await self.client.disconnect()

    def _on_data(self, _char, data):
        data = bytes(data)
        print(f"  <- {data.hex(' ')}")
        # watch pressed "find phone": it keeps asking until we answer
        if data[:2] == b"\x01\x05" and data[4:5] == b"\x01":
            print("  watch is looking for the phone")
            asyncio.ensure_future(self.raw(b"\x81\x05\x05\x00\x01", wait=False))
        self.replies.put_nowait(data)

    async def raw(self, data, wait=True, timeout=3.0):
        print(f"  -> {data.hex(' ')}")
        await self.client.write_gatt_char(TX, data, response=True)
        if not wait:
            return None
        try:
            return await asyncio.wait_for(self.replies.get(), timeout)
        except asyncio.TimeoutError:
            print("  (no reply)")

    async def send(self, cls, cmd, payload=b"", **kw):
        return await self.raw(frame(cls, cmd, payload), **kw)

    async def battery(self):
        return await self.send(0x00, 0x08)

    async def firmware(self):
        # doesn't answer on fw 0.00.24, leaving it in for other builds
        return await self.send(0x00, 0x02)

    async def set_time(self):
        now = datetime.datetime.now().astimezone()
        mins = int(now.utcoffset().total_seconds() // 60)
        sign = 0 if mins >= 0 else 1
        mins = abs(mins)
        return await self.send(0x00, 0x87, bytes([
            now.year // 100, now.year % 100, now.month, now.day,
            now.hour, now.minute, now.second,
            sign, mins // 60, mins % 60,
        ]))

    async def vibrate(self):
        # count, type, strength, duration
        return await self.send(0x04, 0x81, b"\x01\x01\x50\x28")

    async def find(self, pulses=5):
        # 02 A5 is the "proper" find command but this model ignores it.
        # The app just fires a few vibrations back to back, so do the same.
        for _ in range(pulses):
            await self.vibrate()
            await asyncio.sleep(0.6)

    async def notify(self, title, text, kind=3):
        # kind is the app icon: 3 = SMS, 5 = WhatsApp, 17 = custom... 0 is invalid.
        # Without turning the alert switches on first the watch says 02 (nope).
        await self.send(0x02, 0x82, b"\xff\xff\x7f\x00")
        body = bytes([kind]) + title.encode() + b"\xff" + text.encode()
        return await self.send(0x02, 0x83, body)

    async def live(self, secs=20):
        # watch acks these but I haven't seen the 06 80 / 06 81 stream yet
        await self.send(0x01, 0x85, b"\x01")
        await self.send(0x01, 0x93, b"\x01")
        await asyncio.sleep(secs)
        await self.send(0x01, 0x85, b"\x00", wait=False)
        await self.send(0x01, 0x93, b"\x00", wait=False)


async def main(args):
    async with Watch() as w:
        for arg in args or ["battery"]:
            print(f"[{arg}]")
            if arg.startswith("notify:"):
                _, title, text = arg.split(":", 2)
                await w.notify(title, text)
            elif arg.startswith("sleep:"):
                await asyncio.sleep(float(arg.split(":", 1)[1]))
            else:
                await getattr(w, arg)()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
