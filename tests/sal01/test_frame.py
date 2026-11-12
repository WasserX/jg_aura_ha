import pytest

from . import captured
from custom_components.jg_aura.sal01.frame import Frame, FrameDecoder

ALL_CAPTURED = [
    captured.STATUS_STUDY_BATHROOM,
    captured.STATUS_DOWNSTAIRS_MEDIUM,
    captured.GATEWAY_SET_MEDIUM,
    captured.GATEWAY_SET_AWAY,
    captured.CONFIRM_MEDIUM,
    captured.RECEIPT,
    captured.GATEWAY_ACK,
    captured.DEVICE_LIST,
    captured.GATEWAY_TIME_SYNC,
]


@pytest.mark.parametrize("raw", ALL_CAPTURED)
def test_captured_frames_round_trip(raw: bytes) -> None:
    assert Frame.decode(raw).encode() == raw


def test_decode_fields() -> None:
    frame = Frame.decode(captured.GATEWAY_SET_MEDIUM)
    assert frame.seq == 0x11
    assert frame.flags == 0
    assert frame.address == 0xB0B7
    assert frame.payload == b"A2\x01B05%"


@pytest.mark.parametrize(
    "raw",
    [
        captured.RECEIPT[:-1] + b"\x00",  # bad checksum
        captured.RECEIPT[:-2],  # truncated
        b"\x00" + captured.RECEIPT[1:],  # no start byte
    ],
)
def test_decode_rejects_bad_frames(raw: bytes) -> None:
    with pytest.raises(ValueError):
        Frame.decode(raw)


def test_decoder_splits_concatenated_frames() -> None:
    stream = captured.STATUS_STUDY_BATHROOM + captured.CONFIRM_MEDIUM + captured.RECEIPT
    frames = FrameDecoder().feed(stream)
    assert [f.encode() for f in frames] == [
        captured.STATUS_STUDY_BATHROOM,
        captured.CONFIRM_MEDIUM,
        captured.RECEIPT,
    ]


def test_decoder_handles_byte_by_byte_input() -> None:
    decoder = FrameDecoder()
    frames = []
    for byte in captured.DEVICE_LIST:
        frames += decoder.feed(bytes([byte]))
    assert [f.encode() for f in frames] == [captured.DEVICE_LIST]


def test_decoder_skips_noise() -> None:
    noise = b"\x00\x13\x7c\x02\xff"
    frames = FrameDecoder().feed(
        noise + captured.RECEIPT + b"\x7c" + captured.CONFIRM_MEDIUM
    )
    assert [f.encode() for f in frames] == [captured.RECEIPT, captured.CONFIRM_MEDIUM]


def test_decoder_noise_with_long_length_does_not_block_a_frame() -> None:
    # 7C FF looks like the start of a 255-byte frame; the real frame after it must
    # still come out without waiting for 255 bytes.
    frames = FrameDecoder().feed(b"\x7c\xff" + captured.RECEIPT)
    assert [f.encode() for f in frames] == [captured.RECEIPT]


def test_encode_rejects_oversized_payload() -> None:
    with pytest.raises(ValueError):
        Frame(seq=0, address=0, payload=bytes(250)).encode()
