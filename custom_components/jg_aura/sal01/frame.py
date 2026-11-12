"""Framing of the SAL01 serial protocol.

Every message on the wire, in both directions, is one frame:

    7C | len | seq | flags | addr_hi addr_lo | 00 00 00 | payload | xor

``len`` counts the whole frame, ``xor`` is the XOR of every byte before it.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

_LOGGER = logging.getLogger(__name__)

START_BYTE = 0x7C
HEADER_LEN = 9
MIN_FRAME_LEN = HEADER_LEN + 1
MAX_FRAME_LEN = 0xFF
RESERVED = b"\x00\x00\x00"


def checksum(data: bytes) -> int:
    """Return the XOR of all bytes."""
    result = 0
    for byte in data:
        result ^= byte
    return result


@dataclass(frozen=True, slots=True)
class Frame:
    """One SAL01 frame."""

    seq: int
    address: int
    payload: bytes
    flags: int = 0
    reserved: bytes = RESERVED

    def encode(self) -> bytes:
        """Return the frame as bytes on the wire."""
        length = HEADER_LEN + len(self.payload) + 1
        if length > MAX_FRAME_LEN:
            raise ValueError(f"payload too long: {len(self.payload)} bytes")
        body = (
            bytes([START_BYTE, length, self.seq & 0xFF, self.flags & 0xFF])
            + self.address.to_bytes(2, "big")
            + self.reserved
            + self.payload
        )
        return body + bytes([checksum(body)])

    @classmethod
    def decode(cls, data: bytes) -> Frame:
        """Decode exactly one frame, raising ValueError when it is malformed."""
        if len(data) < MIN_FRAME_LEN or data[0] != START_BYTE:
            raise ValueError("not a frame")
        if data[1] != len(data):
            raise ValueError("length mismatch")
        if checksum(data[:-1]) != data[-1]:
            raise ValueError("checksum mismatch")
        return cls(
            seq=data[2],
            flags=data[3],
            address=int.from_bytes(data[4:6], "big"),
            reserved=bytes(data[6:9]),
            payload=bytes(data[HEADER_LEN:-1]),
        )


class FrameDecoder:
    """Split a byte stream into frames, skipping anything that does not check out."""

    def __init__(self) -> None:
        """Initialize an empty buffer."""
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        """Add received bytes and return every complete frame found."""
        self._buffer += data
        frames: list[Frame] = []
        while True:
            start = self._buffer.find(START_BYTE)
            if start < 0:
                if self._buffer:
                    _LOGGER.debug("Dropping %d stray bytes", len(self._buffer))
                self._buffer.clear()
                return frames
            if start:
                _LOGGER.debug("Dropping %d stray bytes", start)
                del self._buffer[:start]
            if len(self._buffer) < 2:
                return frames
            length = self._buffer[1]
            if length < MIN_FRAME_LEN:
                del self._buffer[:1]
                continue
            if len(self._buffer) < length:
                # Either the frame is still arriving, or this 0x7C was noise with a
                # bogus length. Do not let noise hold back a complete frame behind it.
                later = self._find_complete_frame(1)
                if later is None:
                    return frames
                _LOGGER.debug("Dropping %d stray bytes", later)
                del self._buffer[:later]
                continue
            candidate = bytes(self._buffer[:length])
            try:
                frame = Frame.decode(candidate)
            except ValueError:
                # A 0x7C inside a payload or a corrupted frame: resync one byte later.
                del self._buffer[:1]
                continue
            del self._buffer[:length]
            frames.append(frame)

    def _find_complete_frame(self, offset: int) -> int | None:
        """Return the position of the first valid complete frame at or after offset."""
        pos = self._buffer.find(START_BYTE, offset)
        while pos >= 0:
            if pos + 1 < len(self._buffer):
                length = self._buffer[pos + 1]
                if length >= MIN_FRAME_LEN and pos + length <= len(self._buffer):
                    try:
                        Frame.decode(bytes(self._buffer[pos : pos + length]))
                    except ValueError:
                        pass
                    else:
                        return pos
            pos = self._buffer.find(START_BYTE, pos + 1)
        return None
