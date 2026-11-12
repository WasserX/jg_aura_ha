# SAL01 serial protocol

The SAL01 is the USB radio stick that plugs into the JG Aura internet gateway (SALJG30). It talks
to the thermostats over the radio and to its host over a CP2104 USB serial port at 115200 baud,
8N1. The host must keep RTS on (and DTR off), or the stick stays silent. The code is in
`custom_components/jg_aura/sal01/`.

Everything here was worked out by recording the traffic between the gateway and the stick, and
verified by controlling real thermostats without the gateway.

## Frames

Every message, in both directions, is one frame:

```
7C | len | seq | flags | addr_hi addr_lo | 00 00 00 | payload | xor
```

- `len`: length of the whole frame, including `7C` and `xor`.
- `seq`: sequence number, chosen by the sender.
- `flags`: always 00 so far.
- `addr`: the thermostat's 2-byte radio address, or `00 00` for the stick itself.
- `xor`: XOR of every byte before it.

## Receipts

Every frame that is not itself a receipt is answered with a receipt: same `seq` and `addr`,
payload `20 <second payload byte> 00`. If the host does not acknowledge a frame from the stick,
the stick sends it twice more, about 120 ms apart, and eventually stops reporting.

The stick ignores a host request whose `seq`, or whose command counter (below), repeats a recent
one. It still sends the receipt, but does nothing. Never restart counters from a fixed value.

## Payloads

Values are single characters offset by 32, as in the JG Aura cloud API. A temperature `T` is
`chr(T * 2 + 32)`.

| Payload | Direction | Meaning |
|---|---|---|
| `B1` + status | stick → host | Thermostat status report, sent on every change. |
| `A2` + counter + `B05` + chr(preset + 35) [+ 2 digits] | host → stick | Set a preset. The 2 digits are a duration, only for Party and Away. |
| `A2` + counter + `B06` + chr(temp × 2 + 32) | host → stick | Set the target temperature. Ignored in Frost. |
| `B3` + counter + echo | stick → host | The thermostat accepted the command. |
| `A½` (`41 BD`) + local wall-clock seconds since 2000-01-01 (4 bytes, little endian) + `03 0D 00` | host → stick (addr 0000) | Time sync. The thermostats display the time as sent and do not apply daylight saving themselves, so send local time. About 15 s later every thermostat sends a status report. |
| `A°1` (`41 B0 31`) | host → stick (addr 0000) | A gateway is online. The thermostats show a solid globe icon while this keeps coming, and blink it some minutes (6 to over 20) after it stops. The gateway sends it about 4 minutes after starting, then every 6 to 12 minutes. |
| `A0` (`41 30`) + `00 30` | host → stick (addr FFFF) | Every thermostat sends a status report at once. The gateway also sends it to CF B2 at startup. |
| `A³` (`41 B3`) / `B´` (`42 B4`) + addresses | host ↔ stick | Device list: 2-byte addresses padded with `FF FF`. |
| `A±` (`41 B1`) / `B²` (`42 B2`) | host ↔ stick | Unknown block, probably network settings. |
| `A»` (`41 BB`) `05 00` / `B¼` (`42 BC`) | host ↔ stick | Unknown block of digits, probably versions and dates. |

Presets for commands: Auto 0, High 1, Medium 2, Low 3, Party 4, Away 5, Frost 6.

### Status report

`B1` followed by:

| Offset | Meaning |
|---|---|
| 2 | Wiring centre the thermostat belongs to (`$` and `%` seen, one per wiring centre) |
| 3 | Mode: low 4 bits = 1-3 Auto, 4 High, 5 Medium, 6 Low, 7 Party, 8 Away, 9 Frost; bit 0x10 = calling for heat |
| 4 | Room temperature |
| 5 | Target temperature |
| 6-9 | Always `0000` |
| 10 | Unknown: 0, 2, 4 or 18 so far (offset by 32), possibly settings flags |
| 11 | High temperature, also used by Party |
| 12 | Medium temperature (a target set while in Medium changes it) |
| 13 | Low temperature |
| 14 | Frost temperature; with 15, the duration digits in Party and Away |
| 15 | Always `f` (35.0), probably the maximum setpoint |
| 16+ | 7 groups of 9 characters ending in `,`, probably the weekly schedule |

## Addresses and cloud ids

The JG Aura cloud, and this integration's unique ids (`jg_aura_<id>`), use the radio address
with its two bytes swapped: address `A0 BE` is cloud id `bea0`.

## Open questions

- Hot water: its frames have not been captured.
- The device list holds a 12th address, `CF B2`, that is not a thermostat, a wiring centre or
  hot water. At startup the gateway sends it `A0 00 30` and `B01 = 5`, a few times each about 8 s
  apart; it acknowledges them but never confirms.
- The meaning of the time sync's `03 0D 00` ending (the thermostats work out the weekday from the
  date), of the `B²` and `B¼` blocks, and of status
  offset 2.

## Command line

For debugging, the client can be run directly. It needs Home Assistant's Python environment, so
run it inside the Home Assistant container, from the config folder, while the integration is not
using the stick (disable the JG Aura entry first):

```bash
docker exec -w /config homeassistant python -m custom_components.jg_aura.sal01 /dev/ttyUSB0 refresh
docker exec -w /config homeassistant python -m custom_components.jg_aura.sal01 /dev/ttyUSB0 preset bea0 medium
docker exec -w /config homeassistant python -m custom_components.jg_aura.sal01 /dev/ttyUSB0 temperature bea0 19.5
docker exec -w /config homeassistant python -m custom_components.jg_aura.sal01 /dev/ttyUSB0 monitor --wait 600
```
