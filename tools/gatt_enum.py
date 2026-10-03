import asyncio, sys
from bleak import BleakScanner, BleakClient
MAC="CB:56:00:25:EA:23"
async def main():
    d = await BleakScanner.find_device_by_address(MAC, timeout=20)
    if not d:
        print("NOT ADVERTISING (still connected to phone?)"); return
    print("found:", d.name)
    async with BleakClient(d, timeout=30) as c:
        for s in c.services:
            print(f"[S] {s.uuid}  {s.description}")
            for ch in s.characteristics:
                val=""
                if "read" in ch.properties:
                    try:
                        v=await c.read_gatt_char(ch); val=f" = {v.hex()} {v!r}"
                    except Exception as e: val=f" (read err {e})"
                print(f"   [C] {ch.uuid} h={ch.handle} {ch.properties}{val}")
                for de in ch.descriptors: print(f"      [D] {de.uuid}")
asyncio.run(main())
