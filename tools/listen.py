import asyncio, time
from bleak import BleakClient, BleakScanner
MAC="CB:56:00:25:EA:23"
NOTIFY={"uart":"6e400003-b5a3-f393-e0a9-e50e24dcca9e","uart2":"6e40000c-b5a3-f393-e0a9-e50e24dcca9e",
        "ba27":"0000ba27-0000-1000-8000-00805f9b34fb","hr":"00002a37-0000-1000-8000-00805f9b34fb",
        "batt":"00002a19-0000-1000-8000-00805f9b34fb"}
async def main():
    d=await BleakScanner.find_device_by_address(MAC,timeout=20)
    async with BleakClient(d,timeout=30) as c:
        print("connected, mtu",c.mtu_size)
        for n,u in NOTIFY.items():
            try: await c.start_notify(u, lambda ch,data,n=n: print(f"{time.strftime('%X')} <{n}> {data.hex()}"))
            except Exception as e: print("notify fail",n,e)
        print("immediate alert HIGH"); await c.write_gatt_char("00002a06-0000-1000-8000-00805f9b34fb", b"\x02", response=False)
        await asyncio.sleep(4)
        await c.write_gatt_char("00002a06-0000-1000-8000-00805f9b34fb", b"\x00", response=False)
        await asyncio.sleep(16)
asyncio.run(main())
