"""Asyncio client for the SAL01 USB radio stick."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
import logging
import random
from typing import Any

from .exceptions import SAL01ConnectionError, SAL01TimeoutError
from .frame import Frame, FrameDecoder
from .protocol import (
    BROADCAST_ADDRESS,
    COMMAND_CONFIRMATION,
    DEVICE_LIST,
    DEVICE_LIST_REQUEST,
    GATEWAY_ONLINE,
    REPORT_REQUEST,
    STATUS_REPORT,
    STICK_ADDRESS,
    Preset,
    ThermostatStatus,
    decode_device_list,
    decode_status,
    encode_set_preset,
    encode_set_temperature,
    encode_time_sync,
    is_receipt,
    receipt_for,
)

_LOGGER = logging.getLogger(__name__)

BAUDRATE = 115200
CONNECT_TIMEOUT = 5.0
RECEIPT_TIMEOUT = 1.0
RECEIPT_ATTEMPTS = 3
CONFIRMATION_TIMEOUT = 10.0
DEVICE_LIST_TIMEOUT = 3.0

StatusCallback = Callable[[ThermostatStatus], None]
DisconnectCallback = Callable[[Exception | None], None]


class SAL01Client(asyncio.Protocol):
    """Talk to JG Aura (Salus) thermostats through a SAL01 stick.

    The stick pushes a status report whenever a thermostat changes; every report is
    acknowledged and passed to the subscribed callbacks. Commands are confirmed by
    the stick once the thermostat has accepted them.
    """

    def __init__(self, port: str) -> None:
        """Initialize the client for a serial port, e.g. /dev/ttyUSB0."""
        self.port = port
        self.statuses: dict[int, ThermostatStatus] = {}
        self._transport: asyncio.Transport | None = None
        self._connection_made = asyncio.Event()
        self._decoder = FrameDecoder()
        # The stick ignores a request whose seq or command counter matches a recent
        # one (it treats it as a retransmission), so never restart from a fixed value.
        self._seq = random.randrange(256)
        self._counter = random.randrange(255)
        self._send_lock = asyncio.Lock()
        self._receipts: dict[int, asyncio.Future[Frame]] = {}
        self._confirmations: dict[tuple[int, int], asyncio.Future[None]] = {}
        self._device_list: asyncio.Future[list[int]] | None = None
        self._status_callbacks: list[StatusCallback] = []
        self._disconnect_callbacks: list[DisconnectCallback] = []

    # Connection handling

    async def connect(self) -> None:
        """Open the serial port."""
        # Imported here so the protocol code and its tests work without pyserial.
        import serial_asyncio_fast

        loop = asyncio.get_running_loop()
        try:
            await serial_asyncio_fast.create_serial_connection(
                loop, lambda: self, self.port, baudrate=BAUDRATE, rtscts=False
            )
            # The transport calls connection_made on a later loop iteration.
            async with asyncio.timeout(CONNECT_TIMEOUT):
                await self._connection_made.wait()
        except (OSError, ValueError) as err:
            raise SAL01ConnectionError(f"Cannot open {self.port}: {err}") from err
        except TimeoutError as err:
            raise SAL01ConnectionError(f"Cannot open {self.port}") from err

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Set up the port: the stick only talks while RTS is on."""
        assert isinstance(transport, asyncio.Transport)
        self._transport = transport
        port = getattr(transport, "serial", None)
        if port is not None:
            port.dtr = False
            port.rts = True
        self._connection_made.set()
        _LOGGER.debug("Connected to %s", self.port)

    def connection_lost(self, exc: Exception | None) -> None:
        """Fail pending requests and tell subscribers."""
        _LOGGER.debug("Connection to %s lost: %s", self.port, exc)
        self._transport = None
        self._connection_made.clear()
        error = SAL01ConnectionError(f"Connection to {self.port} lost")
        pending: list[asyncio.Future[Any]] = [
            *self._receipts.values(),
            *self._confirmations.values(),
        ]
        if self._device_list is not None:
            pending.append(self._device_list)
        for future in pending:
            if not future.done():
                future.set_exception(error)
        for callback in list(self._disconnect_callbacks):
            callback(exc)

    async def close(self) -> None:
        """Close the serial port."""
        if self._transport is not None:
            self._transport.close()

    @property
    def connected(self) -> bool:
        """Return whether the port is open."""
        return self._transport is not None and not self._transport.is_closing()

    # Subscriptions

    def subscribe(self, callback: StatusCallback) -> Callable[[], None]:
        """Call callback for every status report; returns an unsubscribe function."""
        self._status_callbacks.append(callback)
        return lambda: self._status_callbacks.remove(callback)

    def on_disconnect(self, callback: DisconnectCallback) -> Callable[[], None]:
        """Call callback when the port closes; returns an unsubscribe function."""
        self._disconnect_callbacks.append(callback)
        return lambda: self._disconnect_callbacks.remove(callback)

    # Commands

    async def set_preset(self, address: int, preset: Preset, duration: int = 1) -> None:
        """Set a thermostat's preset and wait for the stick to confirm it."""
        counter = self._next_counter()
        await self._command(
            address, counter, encode_set_preset(counter, preset, duration)
        )

    async def set_temperature(self, address: int, temperature: float) -> None:
        """Set a thermostat's target temperature and wait for confirmation.

        Thermostats in Frost confirm this command but ignore it.
        """
        counter = self._next_counter()
        await self._command(
            address, counter, encode_set_temperature(counter, temperature)
        )

    async def refresh(self, now: datetime | None = None) -> None:
        """Sync the thermostats' clocks; each one then sends a status report."""
        await self._request(
            STICK_ADDRESS, encode_time_sync(now or datetime.now().astimezone())
        )

    async def request_reports(self) -> None:
        """Ask every thermostat for a status report now."""
        await self._request(BROADCAST_ADDRESS, REPORT_REQUEST)

    async def announce_online(self) -> None:
        """Tell the thermostats a gateway is online; repeat every few minutes.

        The gateway sends this every 6 to 12 minutes.
        """
        await self._request(STICK_ADDRESS, GATEWAY_ONLINE)

    async def get_devices(self) -> list[int]:
        """Return the addresses the stick knows (thermostats and other devices)."""
        loop = asyncio.get_running_loop()
        self._device_list = loop.create_future()
        try:
            await self._request(STICK_ADDRESS, DEVICE_LIST_REQUEST)
            async with asyncio.timeout(DEVICE_LIST_TIMEOUT):
                return await self._device_list
        except TimeoutError as err:
            raise SAL01TimeoutError("No device list from the stick") from err
        finally:
            self._device_list = None

    # Internals

    def _next_counter(self) -> int:
        self._counter = self._counter % 255 + 1
        return self._counter

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    async def _command(self, address: int, counter: int, payload: bytes) -> None:
        loop = asyncio.get_running_loop()
        key = (address, counter)
        confirmation: asyncio.Future[None] = loop.create_future()
        self._confirmations[key] = confirmation
        try:
            await self._request(address, payload)
            async with asyncio.timeout(CONFIRMATION_TIMEOUT):
                await confirmation
        except TimeoutError as err:
            raise SAL01TimeoutError(
                f"Thermostat {address:04x} did not confirm {payload!r}"
            ) from err
        finally:
            self._confirmations.pop(key, None)

    async def _request(self, address: int, payload: bytes) -> None:
        """Send a frame and wait for the stick's receipt, retrying a few times."""
        async with self._send_lock:
            loop = asyncio.get_running_loop()
            for _ in range(RECEIPT_ATTEMPTS):
                seq = self._next_seq()
                receipt: asyncio.Future[Frame] = loop.create_future()
                self._receipts[seq] = receipt
                try:
                    self._write(Frame(seq=seq, address=address, payload=payload))
                    async with asyncio.timeout(RECEIPT_TIMEOUT):
                        await receipt
                    return
                except TimeoutError:
                    _LOGGER.debug("No receipt for seq %d, retrying", seq)
                finally:
                    self._receipts.pop(seq, None)
        raise SAL01TimeoutError(f"No receipt from the stick for {payload!r}")

    def _write(self, frame: Frame) -> None:
        if self._transport is None or self._transport.is_closing():
            raise SAL01ConnectionError(f"Not connected to {self.port}")
        _LOGGER.debug("TX %s", frame)
        self._transport.write(frame.encode())

    def data_received(self, data: bytes) -> None:
        """Handle bytes from the stick."""
        for frame in self._decoder.feed(data):
            try:
                self._handle_frame(frame)
            except Exception:
                _LOGGER.exception("Error handling frame %s", frame)

    def _handle_frame(self, frame: Frame) -> None:
        _LOGGER.debug("RX %s", frame)
        payload = frame.payload
        if is_receipt(payload):
            receipt = self._receipts.get(frame.seq)
            if receipt is not None and not receipt.done():
                receipt.set_result(frame)
            return

        # Everything else the stick sends must be acknowledged, or it repeats it.
        if self.connected:
            self._write(
                Frame(
                    seq=frame.seq, address=frame.address, payload=receipt_for(payload)
                )
            )

        if payload.startswith(STATUS_REPORT):
            status = decode_status(frame.address, payload)
            self.statuses[frame.address] = status
            for callback in list(self._status_callbacks):
                callback(status)
        elif payload.startswith(COMMAND_CONFIRMATION) and len(payload) > 2:
            confirmation = self._confirmations.get((frame.address, payload[2]))
            if confirmation is not None and not confirmation.done():
                confirmation.set_result(None)
        elif payload.startswith(DEVICE_LIST):
            if self._device_list is not None and not self._device_list.done():
                self._device_list.set_result(decode_device_list(payload))

    def __repr__(self) -> str:
        """Return a short description."""
        return f"SAL01Client({self.port!r}, connected={self.connected})"
