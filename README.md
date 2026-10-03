# boat-watch

Talking to a boAt smartwatch straight from a PC over Bluetooth LE, no boAt Crest app involved.

**Target:** boAt PRISM (`PRISM_EA23`). Made by KaHa, model `WA37V1`, firmware `v0.00.24`, on a Realtek chip.

## What works

| | Command | Status |
|---|---|---|
| Battery | `00 08` | ✅ |
| Set time and timezone | `00 87` | ✅ |
| Vibrate | `04 81` | ✅ felt |
| Find my watch | 5× `04 81` (no `02 A5` on this model) | ✅ |
| Push notification (title + text) | `02 82` enable, then `02 83` | ✅ |
| Live heart rate / steps | `01 85` / `01 93` | ⚠️ the watch acknowledges, but no data has arrived yet |
| Firmware version | `00 02` | ⚠️ no reply |
| Custom watch face / background | `02 94/96/8F` | 🔜 |

Everything goes over the Nordic UART service (write `6e400002`, notify `6e400003`). No pairing or bonding needed.
Full protocol notes, framing details and the list of opcodes never to send: [PROTOCOL.md](PROTOCOL.md).

## Usage

```sh
pip install -r requirements.txt
# turn off the phone's Bluetooth first: the watch only advertises while disconnected
python watch.py battery set_time vibrate "notify:Title:Message body"
python watch.py find sleep:5
```

`tools/gatt_enum.py` dumps every GATT service. `tools/listen.py` sniffs all notify channels.

## Safety

`watch.py` refuses to send the opcode classes that reset, power off, flash firmware, rewrite the MAC or serial,
or enter factory mode (`06 xx`, `09 xx`, `0A xx`, `00 80/83/84/85/91/AB`).
Never write to the Realtek DFU services `0000d0ff-…` / `00006287-…`: a write to `ffd1` drops the watch into OTA mode.
