from datetime import UTC, datetime

import pytest

from . import captured
from custom_components.jg_aura.sal01.frame import Frame
from custom_components.jg_aura.sal01.protocol import (
    Mode,
    Preset,
    address_to_cloud_id,
    cloud_id_to_address,
    decode_device_list,
    decode_status,
    encode_set_preset,
    encode_set_temperature,
    encode_time_sync,
    is_receipt,
    receipt_for,
)


def test_status_report() -> None:
    frame = Frame.decode(captured.STATUS_STUDY_BATHROOM)
    status = decode_status(frame.address, frame.payload)
    assert status.cloud_id == "d5ea"
    assert status.mode is Mode.FROST
    assert status.preset is Preset.FROST
    assert status.heating is False
    assert status.current_temperature == 19.0
    assert status.target_temperature == 5.0


def test_status_report_medium() -> None:
    frame = Frame.decode(captured.STATUS_DOWNSTAIRS_MEDIUM)
    status = decode_status(frame.address, frame.payload)
    assert status.cloud_id == "bea0"
    assert status.preset is Preset.MEDIUM
    assert status.current_temperature == 18.5
    assert status.target_temperature == 18.0


@pytest.mark.parametrize(
    ("mode_char", "mode", "heating"),
    [
        (b")", Mode.FROST, False),
        (b"9", Mode.FROST, True),
        (b"6", Mode.LOW, True),  # Low while the room was below its setpoint
        (b"7", Mode.PARTY, True),
        (b"#", Mode.AUTO_LOW, False),
        (b"/", Mode.UNKNOWN, False),  # 15 is not a known mode
    ],
)
def test_status_mode_and_heating_flag(
    mode_char: bytes, mode: Mode, heating: bool
) -> None:
    status = decode_status(0xA0BE, b"B1$" + mode_char + b"EH")
    assert status.mode is mode
    assert status.heating is heating


def test_status_rejects_other_payloads() -> None:
    with pytest.raises(ValueError):
        decode_status(0, b"B3\x01B05%")


def test_set_preset_matches_gateway() -> None:
    assert (
        encode_set_preset(1, Preset.MEDIUM)
        == Frame.decode(captured.GATEWAY_SET_MEDIUM).payload
    )
    assert (
        encode_set_preset(6, Preset.AWAY, 1)
        == Frame.decode(captured.GATEWAY_SET_AWAY).payload
    )


def test_set_preset_duration_only_for_party_and_away() -> None:
    assert encode_set_preset(1, Preset.PARTY, 3).endswith(b"'03")
    assert encode_set_preset(1, Preset.FROST, 3).endswith(b")")
    with pytest.raises(ValueError):
        encode_set_preset(1, Preset.AWAY, 100)


def test_set_temperature() -> None:
    assert encode_set_temperature(2, 19.5) == b"A2\x02B06G"
    with pytest.raises(ValueError):
        encode_set_temperature(2, 19.3)
    with pytest.raises(ValueError):
        encode_set_temperature(2, 40)


@pytest.mark.parametrize(
    ("now", "frame"),
    [
        (datetime(2026, 10, 28, 8, 32, 57, tzinfo=UTC), captured.GATEWAY_TIME_SYNC),
        (
            datetime(2026, 10, 30, 9, 7, 40, tzinfo=UTC),
            captured.GATEWAY_TIME_SYNC_FRIDAY,
        ),
    ],
)
def test_time_sync_matches_gateway(now: datetime, frame: bytes) -> None:
    assert encode_time_sync(now) == Frame.decode(frame).payload


def test_time_sync_needs_timezone() -> None:
    with pytest.raises(ValueError):
        encode_time_sync(datetime(2026, 10, 28))


def test_device_list() -> None:
    frame = Frame.decode(captured.DEVICE_LIST)
    addresses = decode_device_list(frame.payload)
    assert len(addresses) == 12
    assert addresses[0] == 0xCFB2
    assert [address_to_cloud_id(a) for a in addresses[1:3]] == ["bea0", "3a78"]


def test_cloud_id_round_trip() -> None:
    assert address_to_cloud_id(0xB0B7) == "b7b0"
    assert cloud_id_to_address("b7b0") == 0xB0B7


def test_receipts() -> None:
    assert receipt_for(b"B1%)F*") == b" 1\x00"
    assert receipt_for(Frame.decode(captured.GATEWAY_ACK).payload) == b" 1\x00"
    assert is_receipt(b" 1\x00")
    assert not is_receipt(b"B1%)F*")
