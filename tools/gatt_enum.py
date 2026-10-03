# Dump every service/characteristic the watch exposes, reading whatever is readable.

import asyncio
import os

from bleak import BleakClient, BleakScanner

MAC = os.environ.get("WATCH_MAC", "CB:56:00:25:EA:23")


async def main():
    dev = await BleakScanner.find_device_by_address(MAC, timeout=20)
    if not dev:
        print("not advertising, probably still connected to the phone")
        return
    print("found", dev.name)

    async with BleakClient(dev, timeout=30) as c:
        for svc in c.services:
            print(f"[S] {svc.uuid}  {svc.description}")
            for ch in svc.characteristics:
                val = ""
                if "read" in ch.properties:
                    try:
                        v = await c.read_gatt_char(ch)
                        val = f" = {v.hex()} {v!r}"
                    except Exception as e:
                        val = f" (read failed: {e})"
                print(f"   [C] {ch.uuid} h={ch.handle} {ch.properties}{val}")
                for d in ch.descriptors:
                    print(f"      [D] {d.uuid}")


asyncio.run(main())
