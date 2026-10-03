# Subscribe to every notify characteristic and print whatever the watch says.
# Press buttons on the watch while this runs.

import asyncio
import os
import sys
import time

from bleak import BleakClient, BleakScanner

MAC = os.environ.get("WATCH_MAC", "CB:56:00:25:EA:23")

CHANNELS = {
    "uart": "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
    "uart2": "6e40000c-b5a3-f393-e0a9-e50e24dcca9e",  # wants a bonded link, fails otherwise
    "ba27": "0000ba27-0000-1000-8000-00805f9b34fb",
    "hr": "00002a37-0000-1000-8000-00805f9b34fb",
    "batt": "00002a19-0000-1000-8000-00805f9b34fb",
}


def printer(name):
    return lambda _ch, data: print(f"{time.strftime('%X')} <{name}> {data.hex(' ')}")


async def main(secs):
    dev = await BleakScanner.find_device_by_address(MAC, timeout=20)
    if not dev:
        print("not advertising, probably still connected to the phone")
        return

    async with BleakClient(dev, timeout=30) as c:
        print("connected, mtu", c.mtu_size)
        for name, uuid in CHANNELS.items():
            try:
                await c.start_notify(uuid, printer(name))
            except Exception as e:
                print(f"couldn't subscribe to {name}: {e}")
        await asyncio.sleep(secs)


asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else 30))
