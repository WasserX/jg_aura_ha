"""Payloads of the SAL01 protocol: thermostat status, commands and stick requests.

Values inside payloads are single printable characters offset by 32, the same
encoding the JG Aura cloud API uses: a temperature T is chr(T * 2 + 32).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import IntEnum

STICK_ADDRESS = 0x0000
BROADCAST_ADDRESS = 0xFFFF

# Payload prefixes. "A" frames go from the host to the stick, "B" frames from the
# stick to the host, and frames starting with a space are link-level receipts.
STATUS_REPORT = b"B1"
COMMAND = b"A2"
COMMAND_CONFIRMATION = b"B3"
DEVICE_LIST_REQUEST = b"A\xb3"
DEVICE_LIST = b"B\xb4"
TIME_SYNC = b"A\xbd"
# Tells the thermostats a gateway is online: they show a solid globe icon while it
# keeps coming, and blink it a few minutes after it stops.
GATEWAY_ONLINE = b"A\xb01"
# Sent to every thermostat: each one sends a status report within half a second.
REPORT_REQUEST = b"A0\x000"
RECEIPT_MARKER = 0x20

ATTR_PRESET = b"B05"
ATTR_TARGET_TEMPERATURE = b"B06"

ZIGBEE_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
# Copied from the gateway's time sync, which always ends with these bytes; their
# meaning is unknown. The thermostats work out the weekday from the date.
TIME_SYNC_TRAILER = b"\x03\x0d\x00"

MIN_TEMPERATURE = 5.0
MAX_TEMPERATURE = 35.0
HEATING_FLAG = 0x10
DURATION_PRESET_DEFAULT = 1


class Preset(IntEnum):
    """Presets that can be set, numbered as the thermostat expects them."""

    AUTO = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    PARTY = 4
    AWAY = 5
    FROST = 6


DURATION_PRESETS = frozenset({Preset.PARTY, Preset.AWAY})


class Mode(IntEnum):
    """Mode as reported in a status report (heating flag removed)."""

    OFFLINE = 0
    AUTO_HIGH = 1
    AUTO_MEDIUM = 2
    AUTO_LOW = 3
    HIGH = 4
    MEDIUM = 5
    LOW = 6
    PARTY = 7
    AWAY = 8
    FROST = 9
    ON = 10
    ON_ALT = 11
    UNKNOWN = 15


MODE_TO_PRESET: dict[Mode, Preset] = {
    Mode.AUTO_HIGH: Preset.AUTO,
    Mode.AUTO_MEDIUM: Preset.AUTO,
    Mode.AUTO_LOW: Preset.AUTO,
    Mode.HIGH: Preset.HIGH,
    Mode.MEDIUM: Preset.MEDIUM,
    Mode.LOW: Preset.LOW,
    Mode.PARTY: Preset.PARTY,
    Mode.AWAY: Preset.AWAY,
    Mode.FROST: Preset.FROST,
}


def decode_char(value: int) -> int:
    """Decode one offset-by-32 character."""
    return value - 32


def decode_temperature(value: int) -> float:
    """Decode one temperature character (half degrees)."""
    return decode_char(value) / 2


def encode_temperature(temperature: float) -> int:
    """Encode a temperature as one character, validating range and 0.5 steps."""
    if not MIN_TEMPERATURE <= temperature <= MAX_TEMPERATURE:
        raise ValueError(
            f"temperature {temperature} outside {MIN_TEMPERATURE}-{MAX_TEMPERATURE}"
        )
    halves = round(temperature * 2)
    if abs(halves - temperature * 2) > 1e-6:
        raise ValueError(f"temperature {temperature} is not a multiple of 0.5")
    return halves + 32


def address_to_cloud_id(address: int) -> str:
    """Return the JG Aura cloud device id of a radio address (bytes swapped)."""
    return address.to_bytes(2, "little").hex()


def cloud_id_to_address(cloud_id: str) -> int:
    """Return the radio address of a JG Aura cloud device id."""
    return int.from_bytes(bytes.fromhex(cloud_id), "little")


@dataclass(frozen=True, slots=True)
class ThermostatStatus:
    """A decoded status report (B1) from one thermostat."""

    address: int
    mode: Mode
    heating: bool
    current_temperature: float
    target_temperature: float
    raw: bytes

    @property
    def cloud_id(self) -> str:
        """Return the JG Aura cloud id, as used in Home Assistant unique ids."""
        return address_to_cloud_id(self.address)

    @property
    def preset(self) -> Preset | None:
        """Return the preset the thermostat is in, if it maps to one."""
        return MODE_TO_PRESET.get(self.mode)


def decode_status(address: int, payload: bytes) -> ThermostatStatus:
    """Decode a B1 status report payload."""
    if not payload.startswith(STATUS_REPORT) or len(payload) < 6:
        raise ValueError(f"not a status report: {payload!r}")
    mode_value = decode_char(payload[3])
    try:
        mode = Mode(mode_value & 0x0F)
    except ValueError:
        mode = Mode.UNKNOWN
    return ThermostatStatus(
        address=address,
        mode=mode,
        heating=bool(mode_value & HEATING_FLAG),
        current_temperature=decode_temperature(payload[4]),
        target_temperature=decode_temperature(payload[5]),
        raw=payload,
    )


def encode_set_preset(
    counter: int, preset: Preset, duration: int = DURATION_PRESET_DEFAULT
) -> bytes:
    """Build the command payload that sets a preset.

    Party and Away take a duration, sent as two digits. The cloud API always sends 01.
    """
    payload = COMMAND + bytes([counter & 0xFF]) + ATTR_PRESET + bytes([preset + 35])
    if preset in DURATION_PRESETS:
        if not 0 <= duration <= 99:
            raise ValueError(f"duration {duration} outside 0-99")
        payload += f"{duration:02d}".encode()
    return payload


def encode_set_temperature(counter: int, temperature: float) -> bytes:
    """Build the command payload that sets the target temperature."""
    return (
        COMMAND
        + bytes([counter & 0xFF])
        + ATTR_TARGET_TEMPERATURE
        + bytes([encode_temperature(temperature)])
    )


def encode_time_sync(now: datetime) -> bytes:
    """Build the time sync payload; the thermostats answer it with status reports.

    The clock is sent as wall-clock seconds since 2000-01-01: the thermostats show
    the time as sent and do not apply daylight saving themselves.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone aware")
    wall_clock = now.replace(tzinfo=UTC)
    seconds = int((wall_clock - ZIGBEE_EPOCH).total_seconds())
    return TIME_SYNC + seconds.to_bytes(4, "little") + TIME_SYNC_TRAILER


def decode_device_list(payload: bytes) -> list[int]:
    """Decode the stick's device list: 2-byte addresses padded with FF FF."""
    if not payload.startswith(DEVICE_LIST):
        raise ValueError(f"not a device list: {payload!r}")
    addresses = []
    body = payload[len(DEVICE_LIST) :]
    for i in range(0, len(body) - 1, 2):
        address = int.from_bytes(body[i : i + 2], "big")
        if address == 0xFFFF:
            break
        addresses.append(address)
    return addresses


def receipt_for(payload: bytes) -> bytes:
    """Return the receipt payload acknowledging a frame with this payload."""
    echo = payload[1:2] or b"\x00"
    return bytes([RECEIPT_MARKER]) + echo + b"\x00"


def is_receipt(payload: bytes) -> bool:
    """Return whether a payload is a link-level receipt."""
    return len(payload) == 3 and payload[0] == RECEIPT_MARKER
