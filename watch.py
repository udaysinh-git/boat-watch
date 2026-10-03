"""Tiny driver for boAt PRISM (KaHa WA37V1, Realtek) over Nordic UART."""
import asyncio, struct, sys, time, datetime
from bleak import BleakClient, BleakScanner
MAC = "CB:56:00:25:EA:23"
TX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
RX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
# (class, cmd) pairs that can brick/reset/unbind -- refuse to send.
BLOCKED = {(0x06,c) for c in range(256)} | {(0x0A,c) for c in range(256)} | {(0x09,c) for c in range(256)} | \
          {(0x00,0x80),(0x00,0x83),(0x00,0x84),(0x00,0x85),(0x00,0x91),(0x00,0xAB)}

def frame(cls, cmd, payload=b""):
    if (cls, cmd) in BLOCKED: raise ValueError(f"blocked opcode {cls:02x} {cmd:02x}")
    return bytes([cls, cmd]) + struct.pack("<H", 4 + len(payload)) + payload

class Watch:
    def __init__(self): self.q = asyncio.Queue()
    def _rx(self, _ch, data):
        data = bytes(data)
        print(f"  <- {data.hex(' ')}")
        if data[:2] == b"\x01\x05" and data[4:5] == b"\x01":  # find-my-phone from watch
            print("  !! watch is looking for the phone"); asyncio.ensure_future(self.raw(b"\x81\x05\x05\x00\x01", wait=False))
        self.q.put_nowait(data)
    async def __aenter__(self):
        d = await BleakScanner.find_device_by_address(MAC, timeout=20)
        if not d: sys.exit("watch not advertising (connected to phone?)")
        self.c = BleakClient(d, timeout=30); await self.c.connect()
        await self.c.start_notify(RX, self._rx); return self
    async def __aexit__(self, *a): await self.c.disconnect()
    async def raw(self, b, wait=True, t=3.0):
        print(f"  -> {b.hex(' ')}"); await self.c.write_gatt_char(TX, b, response=True)
        if wait:
            try: return await asyncio.wait_for(self.q.get(), t)
            except asyncio.TimeoutError: print("  (no reply)")
    async def send(self, cls, cmd, payload=b"", **kw): return await self.raw(frame(cls, cmd, payload), **kw)
    # --- safe commands ---
    async def firmware(self): return await self.send(0x00, 0x02)
    async def battery(self):  return await self.send(0x00, 0x08)
    async def set_time(self):
        n = datetime.datetime.now().astimezone(); off = n.utcoffset().total_seconds() / 60
        sign = 0 if off >= 0 else 1; off = abs(int(off))
        return await self.send(0x00, 0x87, bytes([n.year//100, n.year%100, n.month, n.day, n.hour, n.minute, n.second, sign, off//60, off%60]))
    async def find(self, on=True): return await self.send(0x02, 0xA5, b"\x01\x78" if on else b"\x02\x00")
    async def vibrate(self): return await self.send(0x04, 0x81, b"\x01\x01\x50\x28")
    async def notify(self, title, msg, typ=3):
        # watch rejects (status 02) unless the app-alert categories are enabled first
        await self.send(0x02, 0x82, bytes([0xFF, 0xFF, 0x7F, 0x00]))
        return await self.send(0x02, 0x83, bytes([typ]) + title.encode() + b"\xff" + msg.encode())
    async def live(self, secs=20):
        await self.send(0x01, 0x85, b"\x01"); await self.send(0x01, 0x93, b"\x01")
        await asyncio.sleep(secs)  # 06 80 = live HR, 06 81 = live steps (watch->phone only)
        await self.send(0x01, 0x85, b"\x00", wait=False); await self.send(0x01, 0x93, b"\x00", wait=False)

async def main():
    async with Watch() as w:
        for a in sys.argv[1:] or ["firmware"]:
            print(f"[{a}]")
            if a.startswith("notify:"): _, t, m = a.split(":", 2); await w.notify(t, m)
            elif a.startswith("sleep:"): await asyncio.sleep(float(a[6:]))
            else: await getattr(w, a)()
if __name__ == "__main__": asyncio.run(main())
