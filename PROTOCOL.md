# boAt / KaHa "PRISM_EA23" (WA37V1) BLE protocol notes

Source: the boAt Crest APK (com.coveiot.android.boat), decompiled with jadx. Paths below are relative to
`E:\Projects\boat-watch\src\sources\`. Everything here comes from reading the code statically. Nothing
has been tested against the watch yet.

---------------------------------------------------------------------------------------------------

## 1. Which SDK and protocol the watch uses

**Answer: the CoveIoT/KaHa "Leonardo" SDK (`com.coveiot.sdk.ble`) on the Nordic UART service, in its
Realtek variant. The SMA (`com.szabh.smable3`), TopStep/FitCloud, JStyle, IDO and similar SDKs do not
apply to this watch.**

How the app picks the SDK:
- The device type is a string stored in the session (`SessionManager.getDeviceType()`). It comes from a
  Firebase Remote Config list, `device_models`, whose entries have `modelNumber`, `type` and `scanFilter`
  (`com/coveiot/android/devicemodels/DeviceRemoteConfig.java:24-27, 224-252`). The table that maps a BLE
  name or model to a type is served by the server and is not in the APK.
- The type string becomes the `DeviceType` enum in `DeviceUtils.getBleDeviceType()`
  (`com/coveiot/android/devicemodels/DeviceUtils.java:703`). For example, `R.string.ultima_prism`
  maps to `DeviceType.ULTIMAPRISM` at line 932.
- `BleApiManager` turns the enum into an implementation class: `ULTIMAPRISM` gives
  `UltimaPrismBleApiImpl` (`com/coveiot/android/bleabstract/api/BleApiManager.java:1093`).
  `SMA_ULTIMA_PRISM` ("ULTIMA PRISM 2024 EDITION") is a separate SMA-SDK product
  (`SmaUltimaPrismBleApiImpl`, which imports `com.szabh.smable3`).
- Inheritance chain: `UltimaPrismBleApiImpl` -> `CA6BTABleApiImpl` -> `CY1BleApiImpl` ->
  `CA3BTCallingLeonardoBleApiImpl` -> `CA3LeonardoBleApiImpl` -> `CZ1WavePrimeLeonardoBleApiImpl` ->
  `CZ0LeonardoBleApiImpl` -> `LeonardoBleApiImpl`. The transport is `LeonardoBleService` /
  `LeonardoBleCmdService`.
- `UltimaPrismBleApiImpl.getDeviceSupportedFeatures()` (`bleimpl/UltimaPrismBleApiImpl.java:476`) sets
  `setKaHaRealtekChip(true)` (line 546). Its notification and image requests use
  `DevicePlatformEnum.Realtek` (lines 242, 608, 986).
- `isOPP3Device()` (`DeviceUtils.java:5031`) covers `ultima_prism`, `ultima_chronos` and `wave_convex`.
  These are KaHa devices (see `isKaHaDeviceWithRem`, line 4928).
- The KaHa OTA helper (`com/coveiot/mki/d.java:89`) labels any device that exposes
  `0000d0ff-3c17-d293-8e48-14fe2e4da212` as `Realtek`. Your watch exposes that service.
  `com/coveiot/mki/d.java:409` lists `WA34Vx`..`WA40Vx`, including `WA37V4/V5/V6`, as the "KaHa JieLi"
  variants. So **WA37 is a KaHa platform. WA37V1 is its Realtek build, and the "PRISM" name points to
  Ultima Prism (the OPP3 family).**
- Screen size: the OPP3 assets (`assets/cricket_bg_opp3.bmp`, `football_opp3.bmp`) are **410 x 502**.
- Quick check that it is the KaHa protocol: send `00 02 04 00` (get firmware). A KaHa watch replies
  `80 02 LL 00 <ascii "v0.00.24">`. An SMA watch would not answer this way.

**The other GATT services are not used by the app.** None of `6e40000a/0b/0c`, `494d58a9-...`,
`0000ba26` or `0000ba27` appears in any of the 18 classes*.dex files (I checked the raw dex strings).
They are firmware or vendor services that the app never touches. All commands go through
`6e400002` (write) and `6e400003` (notify).

---------------------------------------------------------------------------------------------------

## 2. Framing on the command channel

The app writes to `6E400002-...` (`WRITE_TYPE_DEFAULT`, i.e. write-with-response, which is the Android
default). It enables CCCD notifications on `6E400003-...` (`services/LeonardoBleService.java:1800-1812`).
- **MTU:** the app requests 185 (`LeonardoBleService.java:182`). Frames can be up to 150 bytes, so you
  need MTU 153 or more.
- Writes are serialized: the app waits for `onCharacteristicWrite` before sending the next one. On
  failure it retries up to 8 times, 40 ms apart (`LeonardoBleCmdService.java:827-860`).

### 2a. Single-packet command (most commands)
```
[0] class    0x00 device/info, 0x01 fitness/health, 0x02 alerts/notifications/watchface,
             0x03 hands, 0x04 vibrator, 0x05 LED, 0x06 system/live streams, 0x0A AGPS
[1] cmd id   GET commands are mostly < 0x80, SET commands are >= 0x80
[2..3] total length of the WHOLE frame including these 4 header bytes, uint16 little-endian
[4..] payload
```
Example: `GET_DEVICE_NAME = 00 00 04 00`. Newer commands put a sub-flag in byte 4: `0x40` means "get"
and `0x41` means "set" (for example `GET_SOS_CONFIG = 00 B7 05 00 40`, `SET_A2DP_MODE = 06 8A 06 00 41`).
Single packets have **no CRC**. Builder: `MultiPacketRequestGenerator.generateSinglePacketRequest()`
(`com/coveiot/sdk/ble/api/MultiPacketRequestGenerator.java:217`).

### 2b. Responses and ACKs
- A reply to command `(class, cmd)` comes back as `(class | 0x80, cmd, lenLo, lenHi, payload...)`.
  For SET commands, `payload[0]` (byte 4) is the status: **0x01 = success**. Examples: `80 87 05 00 01`
  after set-time, `81 85 05 00 01` after starting HR. See the parser at
  `com/coveiot/sdk/ble/parser/ProtocolParser.java:1575` (`handleDeviceInput`). It branches on
  `bArr[0] == 0x80` at line 1589, `0x81` at 2327 and `0x7F` (multi-packet response) at 2984.
- File-transfer ACKs (`82 8E`, `82 94`): the **last byte** is 1 = OK/continue, 0 = busy, anything
  else = memory full (`ProtocolParser.java:4321-4345, 4430-4455`).
- Unsolicited watch events use a class byte without the 0x80 bit (`01 xx`, `03 xx`, `04 xx`, `06 xx`).
  See section 3.
- The app queues commands and sends the next one after a response, or after a 500 ms to 10 s timeout.

### 2c. Multi-packet frames (payloads that do not fit in one frame)
There are two generators in the code.

**(i) Legacy generator** `MultiPacketRequestGenerator.generateRequest(cls, cmd, data, extra, withSize, extraFirst)`
(`MultiPacketRequestGenerator.java:106`). Watch faces, images, files and long notifications use this one.
```
L    = len(data) + len(extra) + 12                       (uint16, truncated; it is only 16 bits)
CK   = (cls + cmd*L*len(data)) & 0xFFFF                  (Java int maths, cmd is a SIGNED byte, e.g. 0x8E = -114)
N    = ceil(L / 146)                                     packet count

first frame (seq 0):
  7F  CK_lo  00 00  N_lo N_hi  CK_lo CK_hi  cls cmd  L_lo L_hi
  then, if withSize:  extraFirst ? (extra + u32le(len(data))) : (u32le(len(data)) + extra)
  otherwise:          extra
  then data bytes until the frame reaches 150 bytes
frame seq k (k >= 1):
  7F  CK_lo  k_lo k_hi  then up to 146 data bytes
```
The "CK" field is a pseudo-checksum, not a real CRC. The app sends it this way in production, so either
copy the formula exactly or expect the watch to ignore it.

**(ii) Newer generator** `MultiPacketRequestGenerator.a()` / `generateBleFramesL()` (line 12; the OTA
helper has an identical copy at `com/coveiot/mki/w.java`). This one uses a real CRC.
```
CRC = crc16(payload)      (see below)
N   = ceil((len+8)/(mtu-4))
first: 7F CRC_lo 00 00 N_lo N_hi CRC_lo CRC_hi cls cmd (len+12)_lo (len+12)_hi [0x41 if set-flag] data...
next:  7F CRC_lo k_lo k_hi data...
```

**CRC-16** (`MultiPacketRequestGenerator.java:235`, also `SendImageReq.crc16`): the byte-swap form of
CCITT, initial value 0, no final XOR. That is **CRC-16/XMODEM** (poly 0x1021, init 0x0000, not reflected).
```python
def crc16(b):
    c = 0
    for x in b:
        c = ((c << 8) | (c >> 8)) & 0xFFFF
        c ^= x
        c ^= (c & 0xFF) >> 4
        c ^= (c << 12) & 0xFFFF
        c ^= ((c & 0xFF) << 5) & 0xFFFF
    return c
```

### 2d. Connection handshake (no auth or bind)
There is no key exchange, encryption or bind token at the GATT level. After services are discovered,
the app does the following (`LeonardoBleService.java:956-980`):
1. requests MTU 185 and enables notifications on 6e400003.
2. sends **set time** (section 3) with `k()` at line 1419.
3. sends a time-format command if supported (24h/12h, `00 82 05 00 00|01`).
4. sends **set phone type** `00 86 05 00 00` (`BleUUID.SET_PAIRING_PHONE_TYPE`, l() at line 1465).
   When `80 86 .. 01` comes back, the app treats the link as CONNECTED.

The OS-level BLE bond and the `PairingFlowCmdReq` (`00 91 14 00 <status> 00*15`) belong to the
onboarding UI. They are not required for commands.

---------------------------------------------------------------------------------------------------

## 3. Safe commands (exact bytes)
Constants are in `com/coveiot/sdk/ble/api/BleUUID.java` (lines 147-273).

| Function | TX bytes | Reply / notes |
|---|---|---|
| Find my watch, start | `02 A5 06 00 01 <count<=120>` e.g. `02 A5 06 00 01 78` | `FindMyWatchReq.java`. Used when the FW capability flag "new find-watch cmd" is set. |
| Find my watch, stop | `02 A5 06 00 02 00` | |
| Vibrate (fallback find-watch) | `04 81 LL 00 <n> {type strength duration}*n`, e.g. `04 81 08 00 01 01 50 28` | `SetVibrationReq.java`. The app's fallback loops 5x (1,80,40) (`CZ0LeonardoBleApiImpl.java:828-850`). |
| Set time | `00 87 0E 00 CC YY MM DD hh mm ss SIGN tzH tzM` | CC/YY = century and year-in-century (2026 -> `14 1A`). SIGN = `2B` '+' or `2D` '-'. Example, 2026-10-03 14:30:00 IST: `00 87 0E 00 14 1A 0A 03 0E 1E 00 2B 05 1E`. Reply `80 87 05 00 01` (`LeonardoBleService.java:1419-1462`). |
| Get time | `00 06 04 00` | `80 06 .. CC YY MM DD hh mm ss SIGN tzH tzM` |
| 24h / 12h | `00 82 05 00 00` / `00 82 05 00 01` | |
| Distance km / miles | `00 A2 05 00 00` / `00 A2 05 00 01` | |
| Temperature C / F | `00 A0 05 00 00` / `00 A0 05 00 01` | |
| Battery | GATT read 0x180F/0x2A19 (what the app uses, `ReadBatteryLevelReq`), or `00 08 04 00` | `80 08 05 00 <pct>` (`ProtocolParser.java:2293`) |
| HW / FW version | `00 01 04 00` / `00 02 04 00` | `80 01|02 LL 00 <ascii>` |
| Name / MAC / SN / mode / colour | `00 00`, `00 03`, `00 04`, `00 05`, `00 07` + `04 00` | ASCII from byte 4. Device info is also readable via GATT 0x180A. |
| FW capability | `01 AC 05 00 ..` (`GET_FIRMWARE_CAPABILITY`) | |
| User profile | `00 81 LL 00 height_cm weight_kg stride_cm gender(0=M,1=F) runStride [age]` | `SaveFitnessProfileReq.java`. LL = 9, or 10 with age. Reply `80 81 .. 01`. **There is no "user name" field in this protocol.** `00 80 08 00` is SET_DEVICE_NAME, which renames the BLE device. Avoid it. |
| Push notification | `02 83 LL 00 <appType> <title utf8> FF <message utf8>` | `CZ2MessageContentReq.java`, used through `CZ0LeonardoBleApiImpl.java:749`. LL = 5 + len(title) + 1 + len(msg). If len(title+msg)+14 > 146, use the legacy multi-packet generator with cls=02, cmd=0x83, extra=[appType], no size. Max 200 chars. appType: 1 call, 2 calendar, 3 SMS, 4 email, 5 WhatsApp, 6 WeChat, 7 Facebook, 8 Instagram, 9 Twitter, 10 Messenger, 11 QQ, 12 QZone, 13 Snapchat, 14 Skype, 15 Telegram, 16 LinkedIn, 17 custom event, 18 other apps, 19 Gmail, 20 KakaoTalk, 21 Line, 22 YouTube, 23 News. |
| Stop / dismiss notification | `02 8C 05 00 <type>` | |
| Enable app alerts | `02 82 06|08 00 <bitmask..>` (`MessageAlertSwitchesReq`) | The notification categories may need to be switched on first. |
| Camera mode on / off (phone to watch) | `02 12 06 00 02 01` / `02 12 06 00 02 02` | `SetCameraStatusReq.java` |
| Music state (phone to watch) | `02 81 05 00 01` play / `02` pause | Metadata: title `02 8B LL 00 <utf16le, max 60B>`, artist `02 8A ..`, album `02 8B ..` (as coded in `SetMediaInfoReq.java`) |
| Live HR on / off | `01 85 05 00 01` / `01 85 05 00 02` | Ack `81 85 05 00 01`. Stream `06 80 LL 00 HR DBP SBP RR STRESS` (`LiveHealthRes.java`). The standard 0x180D/0x2A37 service may also work. |
| Live steps on / off | `01 93 05 00 01` / `01 93 05 00 02` | Stream `06 81 LL 00 steps(u32le) [meters(f32le) kcal(f32le)]` (16-byte variant) (`LiveStepsRes.java`) |
| Today's steps (history) | `01 00 05 00 00` (`GET_WALK_VALUE`), `01 2F 04 00` (today's fitness) | |

**Events from the watch** (`ProtocolParser.java:3599-3700, 3853-3893`):
- `01 05 LL 00 01 <1|0>`: find-my-phone on/off. **Reply with `81 05 05 00 01`** (`BleUUID.FIND_MY_PHONE_ACK`).
- `01 05 LL 00 02 <1|else>`: camera opened/closed on the watch. `01 05 LL 00 03 ..`: **shutter pressed**.
- `01 05 LL 00 04`: call reject. `01 05 LL 00 05`: call mute.
- `01 00 LL 00 <1 play | 2 pause | 3 next | 4 previous>`: music control.
- `01 01 LL 00 <1 vol+ | 2 vol- | >2 absolute level>`: volume.
- `01 08 LL 00 ..`: personalised button event. `04 03 .. <faceId u16le at [5..6]>`: watch face changed on the watch.
- `06 80`: live health. `06 81`: live steps. `06 83`: raw ECG. `06 84`: recovery time.

---------------------------------------------------------------------------------------------------

## 4. Watch faces and images

Everything goes over the **same UART channel (6e400002)**. The app does not use the Realtek DFU services
for watch faces.

### 4a. Cloud / "DIY" watch-face file: opaque blob, cmd `02 8E`
- `WatchFaceUploadReq.java`, called from `CZ0LeonardoBleApiImpl.java:1482-1494`. The app sends the
  downloaded file **unmodified**:
  `generateRequest(cls=02, cmd=0x8E, data=file, extra=u16le(watchFaceId), withSize=true, extraFirst=true)`.
  - First frame: `7F CK 00 00 N N CK CK 02 8E L L | faceId_lo faceId_hi | size u32le | 132 data bytes`.
  - Following frames: `7F CK seq_lo seq_hi | 146 data bytes`.
- **Flow control on KaHa-Realtek** (`LeonardoBleService.java:243-268`): keep a running count of payload
  bytes (first frame length - 12, later frames length - 4). Each time `(written-6)/2048` moves to the next
  whole number, stop and wait for `82 8E .. 01`, then continue. After the last frame, `82 8E .. 01`
  means done. A last byte of 0 means busy; any other value means out of memory.
- File format: produced by KaHa's server. Nothing in the app parses or builds it, so the header layout
  is not visible here. To get samples, capture the download (`watchfaces` API below) and diff them.
- Related commands: list faces `02 0D 04 00`, get current `02 0F 04 00`,
  **set current `02 8F 06 00 <id> 00`**, delete face `02 90 06 00 <id> 00`.

### 4b. Custom background image (the simplest path to your own picture): cmd `02 94`
The sequence for this model is in `UltimaPrismBleApiImpl.java:302-310, 600-620` and
`CZ0LeonardoBleApiImpl.java:3272-3310`:
1. `02 95 06 00 <imageId u16le>`: DeleteImage (frees the slot). Wait for the reply.
2. Wait 500 ms, then send SendImage (`SendImageReq.java`):
   `generateRequest(cls=02, cmd=0x94, data=img, extra=[imgId_lo, imgId_hi, compression(0), transparent(0), height_lo, height_hi, width_lo, width_hi, crc16(img)&0xFF], withSize=true, extraFirst=false)`.
   - First frame: `7F CK 00 00 N N CK CK 02 94 L L | size u32le | 9 extra bytes | 125 data bytes`.
   - Flow control: wait for `82 94 .. 01` every 2048 payload bytes (`written/2048`, no offset).
3. `02 96 08 00 <watchFaceId u16le> <imageId u16le>`: ChangeWatchFaceBG.
4. `02 8F 06 00 <watchFaceId> 00`: SetCurrentWatchFace.

- **Pixel format** (`com/coveiot/sdk/ble/utils/ImageModel.java:157-220`): decode to ARGB8888 and
  composite onto white unless transparency is on. Each pixel becomes
  **RGB565 = (R&0xF8)<<8 | (G&0xFC)<<3 | B>>3**, stored **big-endian** (high byte first) for Realtek.
  Pixels are row-major, top-left first. With transparency on, each pixel is 3 bytes:
  `[alpha, hi, lo]`. This model's background path sends compression=0 and transparent=0, so the
  payload is raw **410 x 502 x 2 = 411,640 bytes**.
- Optional RLE (compression=1, `ImageModel.b()`): a header with one byte per row (the compressed row
  length, truncated to 8 bits), followed by the runs. Each run is either `(count+128), pixel` for a
  repeat of 3 to 127 pixels, or `count, pixel*count` for literals. Runs do not cross row boundaries.
- The watchFaceId and imageId slots come from the server's `WatchFaceLayoutInfo` for this model. Read
  them from the watch with `02 0D 04 00` (face list) and `02 13 04 00` (image id list), or capture them
  from the app.

### 4c. Where face files come from
- REST gateway base URL (from manifest meta-data `com.coveiot.coveaccess.gateway.Url`):
  **`https://gateway.cove.kahaapi.com/`**
- Endpoints (`com/coveiot/coveaccess/CoveApiService.java:1009-1021, 551, 1344, 1441`):
  - `GET watchfaces?edition=&faceType=&firmwareVersion=&pageIndex=&itemsPerPage=`
  - `GET watchfaces?...&categoryId=`
  - `POST GET/watchface/details`
  - `GET watchfaces/categories?faceType=`
  - `GET watchfaces/onDevice?userDeviceId=`
  - `GET watchfaces/autoRefresh`
  - `POST watchfaces/onDevice`
  - `POST watchface/diy`
- These need the app's API key and auth headers (header map). Each response item contains the file URL
  that the app downloads and passes to 4a.

---------------------------------------------------------------------------------------------------

## 5. Do NOT send these

| Opcode | Name | Effect |
|---|---|---|
| `06 80 04 00` | SET_TURN_OFF_BLE | turns off the watch's BLE radio |
| `06 81 04 00` | SET_RESET_SYSTEM | system reset (factory reset / reboot) |
| `06 82 04 00` | SET_POWER_OFF | powers the watch off |
| `06 85 ...` | SEND_FILE / SEND_UPDATE_FILE | file push. KaHa's OTA helper uses this same opcode for firmware images (`com/coveiot/mki/g.java:60`) |
| `0A 00 ...` | AGPS_FILE_PUSH | almanac upload |
| `09 00`, `09 01`, `09 02` | JieLi OTA mode / send | OTA |
| `00 83 10 00 ...` | SET_MAC_ADDRESS | rewrites the MAC address |
| `00 84 14 00 ...` | SET_SN | rewrites the serial number |
| `00 85 05 00 01` | SET_DEVICE_MODE_TEST | factory test mode (`00 85 05 00 00` = normal) |
| `00 80 08 00 ...` | SET_DEVICE_NAME | renames the BLE device |
| `00 AB 05 00 ..` | SEND_UNBIND_BT_CALL | unbinds BT calling |
| `00 91 14 00 ..` | PairingFlowCmd | pairing state machine |
| `06 07 ..`, `06 08 ..` | diagnostic control / feature test | factory diagnostics |
| `02 90 ..` | delete watch face | lossy but recoverable |
| `02 95 ..` | delete image | lossy but recoverable |
| `01 9A 04 00` | delete nearby device list | lossy but recoverable |
| `01 97 ..` | pause/delete activity session | lossy but recoverable |
| `00 90 05 00 ..` | SET_PROBE | unknown; leave it alone |

**Realtek DFU:** do not write anything to service `0000d0ff-3c17-d293-8e48-14fe2e4da212` (chars
`0000ffd1..ffd8`; a write to `ffd1` puts the watch in OTA mode) or to `00006287-3c17-...` (chars
`00006387/6487/6587-...`). That is the Realsil DFU path used by
`com/coveiot/android/leonardo/more/activities/ActivityFirmwareUpdateKaHaRealTek.java`.
Also avoid the services the app never uses (`6e40000a`, `494d58a9`) until they are understood.

---------------------------------------------------------------------------------------------------

## 6. Watch Face Studio

Short version: **on this model every custom face the app produces reaches the watch as a whole face
file over `02 8E` (section 4a). The app never uses `02 94` / `02 96` for an Ultima Prism.** There are
two ways the app produces that file:

- **(A) Watch Face Studio (web app).** The face is built on KaHa's server. The app only downloads the
  finished `.bin` and pushes it with `02 8E`. The file format is not visible in the APK.
- **(B) Native "Customise watch face" screen.** The app builds the file locally. It takes a bundled
  KaHa template `.bin` and overwrites the background and preview pixels in place (`KHWatchFaceModifier`).
  Then it pushes the result with `02 8E` as face id **996**. This works offline, and the format is
  fully described in 6c.

The `ab569x_*.zip` assets do not belong to this watch (see 6e).

### 6a. Which branch the app takes for ULTIMAPRISM

**Studio entry points.** The dashboard card (`WATCH_FACE_STUDIO`) and the smart-grid item `WF_STUDIO`
appear only when `isDiySupported()` is true (`com/coveiot/android/dashboard2/util/SetupYourWatchDataHelper.java:31-45, 84-88`).
That flag comes from the server: `DeviceModelBean.isDiyWatchFaceSupported`, from the remote device
list (`com/coveiot/android/leonardo/dashboard/ActivityDashboardNew.java:2096-2097`). Both entry points
open `ActivityInAppWebViewerWatchface`, which is a WebView
(`dashboard2/util/SmartGridUtilsKt.java:240-246`, `watchfaceui/utils/AppNavigator.java:28-35`). The
page URL is `SessionManager.getWatchFaceDiyUrl()`. That value is `data.watchface.diyToolUrl` from
`GET app/remote/config` (`ActivityDashboardNew.java:2594-2597`, `coveaccess/CoveApiService.java:844-851`).
The "My designs" tab also opens this page (with an edit URL parameter), or it re-applies a saved
design (`watchfaceui/fragments/FragmentMyDesigns.java:344-351, 832-847`).

**JS bridge** (`watchfaceui/webSupport/JSInterface.java`). The web app calls these methods:
- `appIn({"reqType":"GET_X_HEADERS"})` (lines 187-199). The app answers with `CoveApi.getCustomHeaders()`,
  which holds the API key and auth headers. The web app uses them to talk to the KaHa backend directly.
- `appIn({"reqType":"WF_APPLY_ON_DEVICE","data":{"uid","faceId","faceType"}})` (lines 214-240). This
  calls `ActivityInAppWebViewerWatchface.onClicked(uid, faceId, faceType)`.
- `webOut({"resType":"WF_ASSETS_GENERATED","data":{"uid","faceType"}})` (lines 497-526). This calls
  `onGenerated()`, the "build locally from an asset zip" path. It does nothing for this watch:
  `WatchFaceBuilderFactory.getBuilder()` returns a builder only for `"SMA"`
  (`watchfaceui/vendor/watchfacebuilder/WatchFaceBuilderFactory.java`), and
  `DeviceUtils.getWatchFaceBuilderType()` returns `"SMA"` only for SMA devices and `"DEFAULT"` for
  everything else (`devicemodels/DeviceUtils.java:3281-3284`). So **no local Studio builder exists for
  KaHa devices.**

**Path A, step by step** (`ActivityInAppWebViewerWatchface.java:1191-1236`):
1. `POST GET/watchface/details` with body `{"faceType": <faceType>, "uids": [<uid>]}`
   (`CoveApiService.java:1015-1016`, `coveaccess/watchface/model/WatchfaceByIdRequest.java`).
2. Take `data.items[0]` and read `uid`, `faceId`, `faceType`, `downloadUrl` and `fileMd5Hash`.
3. `WatchFaceDiyViewModel.downloadWatchFaceFromServerSendToWatch("watchface", downloadUrl, bean)`.
   This downloads the file to `filesDir/watchface` and checks the MD5 if the server sent one
   (`viewmodel/WatchFaceDiyViewModel.java:1402-1410`, and the download handler around lines 470-710).
4. `sendWatchFaceToWatch()` parses the face id as **hexadecimal**:
   `faceId = Integer.parseInt(bean.faceId, 16)` (lines 1232-1237). `SetWatchFaceRefreshFlagRequest`
   is only sent when `isAutoWatchFaceRefreshFlagSupported` is set. `UltimaPrismBleApiImpl` never sets
   it (`bleimpl/UltimaPrismBleApiImpl.java:476-563`; `BleApiUtils.java:546-590` does not touch it either).
   So the app goes straight to `sendWatchFaceFileToWatch()` (lines 1206-1216). That builds a
   `CustomWatchFaceFileImageRequest(filePath, faceId)` and calls `bleApi.getData()`.
5. `CZ0LeonardoBleApiImpl.java:1482-1494` turns this into `WatchFaceUploadReq(file, faceId)`, i.e. cmd
   `02 8E`. `UltimaPrismBleApiImpl.getData()` does not override this request.

**Path B, step by step.** `ActivityWatchFace` shows the "Customise" button. It opens
`ActivityBackgroundWatchFace` (`watchfaceui/activities/ActivityWatchFace.java:1231-1245`), which picks
the fragment by device family. **`isCADevice()` is checked first** (`ActivityBackgroundWatchFace.java:504`),
and its list includes `R.string.ultima_prism`, `ultima_chronos` and `wave_convex`
(`DeviceUtils.java:4742-4745`). So the Prism gets **`FragmentWatchFaceBackgroundCA`**. It does not get
the CY1 / CZ2 / Moyang fragments, which are the only callers of the `02 94` + `02 96` background path
in 4b (`sendWatchFaceBackgroundToWatch` / `sendBackgroundWatchFaceToWatch`). That explains why 4b
never produced a face here.

`FragmentWatchFaceBackgroundCA`:
- `imageWidth = 368`, `imageHeight = 448`, and `watchfaceId = 996` is **hard-coded**
  (`fragments/FragmentWatchFaceBackgroundCA.java:87-90`). Only ULC devices switch to 240x280
  (lines 605-607). The Prism is not a ULC device.
- The photo goes through uCrop with `withMaxResultSize(368, 448)` and is saved as JPEG
  (`utils/Utils.java:1285-1318`; called at lines 398 and 407).
- "Apply" calls `sendCAWatchFaceBackgroundToWatch(backGroundType, 996)` (line 361;
  `viewmodel/WatchFaceBackgroundViewModel.java:2093-2100`). The work happens in
  `WatchFaceBackgroundViewModel$sendCAWatchFaceBackgroundToWatch$1$2.java`:
  - Template: `backGroundType == 1` uses `res/raw/ca3_diy_02.bin`, otherwise `res/raw/ca3_diy_01.bin`
    (line 151). ULC devices use `ca5_ulc_diy_1/2.bin` instead.
  - Preview: the photo is resized to 240x280. The app draws `ca3_diy_watch_face_place_holder_transparent_whitef`
    (or `..._blackf` when type 1) on top of it with `putOverlay`.
  - It calls `KHWatchFaceModifier.generateNewBinFile(template, croppedPhoto, preview, filesDir/diy_output_01.bin)`
    (line 194), then `sendWatchFaceFileToWatch(file, 996, type)` (lines 205/209,
    `WatchFaceBackgroundViewModel.java:1816`). That sends the same `CustomWatchFaceFileImageRequest`,
    which becomes `02 8E`.

### 6b. BLE sequence (both paths)

There is only one command, the legacy multi-packet `02 8E` from 4a:
```
generateRequest(cls=0x02, cmd=0x8E, data=<face file bytes>, extra=u16le(faceId), withSize=True, extraFirst=True)
first frame:  7F CK 00 00 N_lo N_hi CK_lo CK_hi 02 8E L_lo L_hi | faceId_lo faceId_hi | u32le(len(file)) | 132 data bytes
later frames: 7F CK seq_lo seq_hi | 146 data bytes
```
(`sdk/ble/api/request/WatchFaceUploadReq.java`. The request takes `putInt(faceId)` little-endian and
keeps only the low 2 bytes.)
- Path B: faceId = 996, so the extra bytes are **`E4 03`**. The template is 565,252 bytes, so the
  size field is `04 A0 08 00`.
- Path A: faceId = `int(server_faceId, 16)`, taken from the `GET/watchface/details` item.
- Pacing on a KaHa Realtek chip (`services/LeonardoBleService.java:243-268`): keep a running payload
  count (first frame len-12, later frames len-4). When `(count-6)//2048` changes, stop and wait for
  `82 8E .. 01`. The final `82 8E .. 01`, with no frames left, means the upload is done. A last byte
  of `00` means "watch busy". Any other value means "watch memory exceeded"
  (`sdk/ble/parser/ProtocolParser.java:4321-4345`).
- **There is no separate "set current face" step.** Neither path sends `02 8F`, `02 96` or a delete
  before or after the upload. On success the app only updates its own preferences
  (`WatchFaceDiyViewModel.java:1103-1127`; `WatchFaceBackgroundViewModel.java` around lines 1890-1920)
  and reports to the server (`callDeviceSpecificSettingsApiDiy`). The firmware appears to activate a
  freshly uploaded face by itself. If it does not, `02 8F 06 00 E4 03` (set current = 996) is the
  obvious thing to try, but the app never sends it, so this is untested.
- The app sends no image id. The face file contains its own image table.

### 6c. KaHa face file format (from `KHWatchFaceModifier` + the bundled templates)

The templates are copied, not modified, to `apk\studio_assets\kaha_templates\`. The originals are in
the APK as `res/raw/ca3_diy_01.bin`, `ca3_diy_02.bin` (565,252 B, 368x448 background) and
`ca5_ulc_diy_1.bin`, `ca5_ulc_diy_2.bin` (246,644 B, 240x280 background). All integers are
little-endian. The app reads only the fields marked *. I decoded the rest from the files themselves
and checked it against both template sizes.
```
0x00 u16  format/version            = 3
0x02 u32  total file size           = 565252 / 246644
0x06 u16  template/face code        = 0x60E1 (CA3), 0xF378 (ULC). Identical in the light and dark
                                      variants, so it is NOT a checksum of the content
0x08 u16  0
0x0A u16  image-table length, bytes = 408 (34 entries x 12)
0x0C      image table, 12 bytes per entry:
            u32 offset | u16 width | u16 height | u32 size  (bit31 set = has alpha)
          entry 0 = preview thumbnail   (* offset @0x0C, w @0x10, h @0x12)  240x280 / 144x168, 2 B/px
          entry 1 = full background     (* offset @0x18, w @0x1C, h @0x1E)  368x448 / 240x280, 2 B/px
          entries 2..11  big digits 0-9    38x50, alpha (CA3)
          entries 12..21 small digits 0-9  14x18, alpha
          entries 22..33 month names JAN..DEC 50x20, alpha
0x0C+tableLen  layout block (143 B in CA3), runs up to entry0.offset (0x233):
          15-byte header  09 00 05 40 00 54 00 00 00 05 00 00 00 00 01   (CA3; ULC has 30 00 38 in
                          place of 40 00 54). Meaning unknown: copy it verbatim.
          then one record per widget:
            u8 0x02 | u8 kind (0x10 = digit, 0x12 = text list) | u16 x | u16 y | u8 elementId |
            u8 n | n x u8 image-table index
          elementIds seen: 5 = hour tens, 6 = hour units, 3 = minute tens, 4 = minute units,
                           9 = day tens, 10 = day units, 21 (0x15) = month (12 frames)
          CA3 positions: HH at x 99/139, MM at x 194/232, y 319. Day at x 137/152, y 389.
          Month at x 180, y 387.
pixel data: entries stored back to back in table order, starting at 0x233. Nothing follows the last one.
```
Pixel encodings:
- No alpha (bit31 clear): **RGB565 big-endian**, 2 bytes per pixel, row-major, top-left first. The
  app gets these bytes by copying an Android `RGB_565` bitmap into a buffer and swapping each byte pair
  (`KHWatchFaceModifier.java:29-82`).
- Alpha (bit31 set): 3 bytes per pixel, `[A8, RGB565_hi, RGB565_lo]`. Alpha 0 is transparent.
- No compression and no RLE in this format. **No checksum or CRC needs updating.** The app copies the
  new pixels over the template and writes the file out without touching any header field
  (`KHWatchFaceModifier.java:84-130`).

Python recipe for path B (exactly what the app does):
```python
import struct
from PIL import Image
t = bytearray(open('ca3_diy_01.bin','rb').read())        # light digits; ca3_diy_02 = dark variant
def put(entry, img):
    off, w, h, sz = struct.unpack_from('<IHHI', t, 12 + 12*entry)
    img = img.convert('RGB').resize((w, h))               # MUST be exactly w x h (the app only checks <=)
    px = bytearray()
    for r, g, b in img.getdata():
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        px += bytes((v >> 8, v & 0xFF))
    t[off:off+len(px)] = px
put(1, Image.open('photo.jpg'))                           # background 368x448
put(0, Image.open('photo.jpg'))                           # preview 240x280 (the app also overlays the placeholder)
open('diy_output_01.bin','wb').write(t)
# then send it with 02 8E, extra = b'\xE4\x03' (faceId 996), withSize, extraFirst, 2048-byte ACK pacing
```
The app writes the background in row order. If uCrop returns something smaller than 368x448, the app
writes fewer bytes and the image comes out sheared. Always resize to exactly the slot size.

**Resolution caveat.** The app sends this 368x448 CA3 template to the Prism unchanged, even though the
screen is 410x502. No 410x502 KaHa template exists in the APK. The CA3 widget coordinates (y up to
407) fit inside 410x502, so the face may render at top-left with a border, or the firmware may scale
it. Only the watch can tell. For a native-resolution face, capture one Studio-built file for this
model (path A `downloadUrl`). If it starts with `03 00 <u32 size>`, the same table layout applies, and
the background can be patched in place at 410x502 the same way.

### 6d. Server dependencies

- Path B needs nothing from the server. The template, the face id (996) and the sizes are all in
  the APK.
- Path A needs, from `https://gateway.cove.kahaapi.com/` with the app's auth headers:
  1. `GET app/remote/config`: `data.watchface.diyToolUrl`, the Studio web app URL.
  2. The web app, using the headers it got through `GET_X_HEADERS`, creates the design on the server.
     Its upload goes through `POST/PUT watchface/diy`, multipart with a `watchfaceJson` part plus files
     (`CoveApiService.java:1441-1447`). It then reports a `uid`.
  3. `POST GET/watchface/details` `{"faceType","uids":[uid]}` returns `faceId` (hex string),
     `downloadUrl` and `fileMd5Hash`.
  4. A download from `downloadUrl` gives the ready-made face `.bin`.
  The APK contains no fallback for path A. The layout JSON, "basic bin" and face id all come from the
  server.

### 6e. What the `ab569x_410x502_*.zip` assets are

They are **not** for KaHa or Realtek watches. `watchfaceui/chromehorizon/WatchFaceBaseFileProvider.java`
(and the `chromeiris` copy) returns `ab569x_410x502_number.zip` / `..._pointer.zip` only for
`TOUCHELX_ULTIMA_VOGUE2`. Other TouchELX models get the other sizes. These are base files for the
TouchGUI SDK (`com/touchgui/sdk`, Bluetrum AB569x chip). Copies are unpacked in `apk\studio_assets\`.
- `number`: `config.json` (`type:"number"`, `changeBackground/changeColor`, 7 styles), `bg.png`,
  `N_style.png` previews, and `cfg_resN.watch`.
- `pointer`: `config.json` (`type:"pointer"`, 5 styles plus `mask` entries), `bg.png`, and per style
  `N/res_cfg.watch`, `time_img.png`, `mask.png`.
- The `.watch` files start with magic `WF` (`57 46`). They are TouchGUI resource blobs that the SDK
  pushes as `cfg_res.watch` / `picture.watch` (`com/touchgui/sdk/c.java:200-267`,
  `internal/AbstractC2310r2.java:13-28`). The KaHa `02 8E` path does not understand them.

### 6f. Why the raw 411,640-byte `02 94` image did nothing

- `02 94` stores a loose image in the watch's image store, which is why it shows up in `02 13`.
  `02 96` then binds that image id to a face that has a replaceable background slot. The built-in
  faces 0-3 evidently have no such slot. The app never uses this pair for an Ultima Prism (6a), so
  nothing in the APK says which face or image ids would work.
- The image size was not the problem. The app has no maximum for `02 94`, and the KaHa face format
  stores uncompressed RGB565 anyway. The only size checks are:
  - `KHWatchFaceModifier`: the new image must fit the slot (`<= w*h*2`, otherwise "Incorrect image size").
  - The watch's own `82 8E` "memory exceeded" status.
- To show a custom picture, wrap it in a face file and upload that with `02 8E` (6b/6c).
