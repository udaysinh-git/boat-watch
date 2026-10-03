# boat-watch

I have a boAt PRISM smartwatch and wanted to control it from my laptop instead of going through the boAt Crest app. Turns out it's not locked down at all: you connect over BLE, write bytes to a UART characteristic, and it does stuff. No pairing, no auth.

This repo is my notes plus a small Python script that talks to it.

## The watch

- sold as boAt PRISM, shows up as `PRISM_EA23`
- actually made by KaHa, model `WA37V1`, firmware `v0.00.24`
- Realtek chip (you can tell from the Realtek OTA services it exposes)

I worked out the protocol by decompiling the boAt Crest app. The decompiled code and the APK aren't in here, just what I learned from them. That's in [PROTOCOL.md](PROTOCOL.md).

## What works so far

| thing | how | works? |
|---|---|---|
| battery | `00 08` | yes |
| set time + timezone | `00 87` | yes |
| vibrate | `04 81` | yes |
| find my watch | five `04 81` in a row | yes, buzzes but no sound |
| notifications | `02 82` then `02 83` | yes |
| live heart rate / steps | `01 85` / `01 93` | watch says ok, but no data shows up yet |
| firmware version | `00 02` | no reply on this firmware |
| custom watch face | `02 94` → `02 96` → `02 8F` | working on it |

A few things that tripped me up:

- **Notifications get rejected** (status `02`) until you turn on the per-app alert switches with `02 82`. The app does this quietly on connect, so you'd never notice.
- **The notification type can't be 0.** It's the app icon, starting at 1 (3 is SMS, 5 is WhatsApp, and so on).
- **`02 A5` (find watch) does nothing on this model.** The app checks a feature flag and falls back to sending vibrations, so that's what `find` does here.
- **It won't ring.** It has a speaker for BT calls, but that's over classic Bluetooth, not this BLE link.

## Running it

```sh
pip install -r requirements.txt
```

Turn off Bluetooth on your phone first. The watch only advertises when nothing's connected to it.

```sh
python watch.py battery set_time vibrate
python watch.py "notify:hey:this came from my laptop"
python watch.py find
```

Commands run in order, and `sleep:N` waits N seconds between them. If your watch has a different MAC, set `WATCH_MAC`.

There are two helpers in `tools/`:
- `gatt_enum.py` lists every service and characteristic and reads what it can
- `listen.py` subscribes to everything and prints whatever the watch sends

## Don't brick it

`watch.py` refuses to send anything in classes `06`, `09` or `0A`, or `00 80/83/84/85/91/AB`. Those reset or power off the watch, push firmware, rewrite the MAC or serial, or put it in factory mode.

Also stay away from the Realtek OTA services (`0000d0ff-…` and `00006287-…`). A single write to `ffd1` drops the watch into update mode.
