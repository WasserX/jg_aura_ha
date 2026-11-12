"""Client tests against a simulated stick."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from . import captured
from custom_components.jg_aura.sal01 import client as client_module
from custom_components.jg_aura.sal01.client import SAL01Client
from custom_components.jg_aura.sal01.exceptions import (
    SAL01ConnectionError,
    SAL01TimeoutError,
)
from custom_components.jg_aura.sal01.frame import Frame, FrameDecoder
from custom_components.jg_aura.sal01.protocol import Preset, ThermostatStatus


class FakeStick(asyncio.Transport):
    """Transport that records writes and answers like the SAL01."""

    def __init__(
        self, client: SAL01Client, *, answer: bool = True, confirm: bool = True
    ):
        super().__init__()
        self.client = client
        self.answer = answer
        self.confirm = confirm
        self.sent: list[Frame] = []
        self._decoder = FrameDecoder()
        self._closing = False
        self._seq = 0x40

    def write(self, data: bytes) -> None:
        for frame in self._decoder.feed(bytes(data)):
            self.sent.append(frame)
            if self.answer and not frame.payload.startswith(b" "):
                asyncio.get_running_loop().call_soon(self._respond, frame)

    def _respond(self, frame: Frame) -> None:
        receipt = Frame(
            seq=frame.seq,
            address=frame.address,
            payload=b" " + frame.payload[1:2] + b"\x00",
        )
        self.client.data_received(receipt.encode())
        if frame.payload.startswith(b"A2") and self.confirm:
            self._seq += 1
            confirmation = Frame(
                seq=self._seq, address=frame.address, payload=b"B3" + frame.payload[2:]
            )
            self.client.data_received(confirmation.encode())
        if frame.payload == b"A\xb3":
            self.client.data_received(captured.DEVICE_LIST)

    def is_closing(self) -> bool:
        return self._closing

    def close(self) -> None:
        self._closing = True
        self.client.connection_lost(None)


@pytest.fixture
def client() -> SAL01Client:
    client = SAL01Client("/dev/fake")
    client._counter = 0  # counters start at random values; pin them for assertions
    return client


@pytest.fixture(autouse=True)
def fast_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "RECEIPT_TIMEOUT", 0.05)
    monkeypatch.setattr(client_module, "CONFIRMATION_TIMEOUT", 0.1)
    monkeypatch.setattr(client_module, "DEVICE_LIST_TIMEOUT", 0.1)


def attach(client: SAL01Client, **kwargs: bool) -> FakeStick:
    stick = FakeStick(client, **kwargs)
    client.connection_made(stick)
    return stick


async def test_status_report_is_acked_and_published(client: SAL01Client) -> None:
    stick = attach(client)
    seen: list[ThermostatStatus] = []
    client.subscribe(seen.append)

    client.data_received(captured.STATUS_STUDY_BATHROOM)

    assert [s.cloud_id for s in seen] == ["d5ea"]
    assert client.statuses[0xEAD5].target_temperature == 5.0
    ack = stick.sent[-1]
    assert (ack.seq, ack.address, ack.payload) == (0x06, 0xEAD5, b" 1\x00")


async def test_unsubscribe(client: SAL01Client) -> None:
    attach(client)
    seen: list[ThermostatStatus] = []
    unsubscribe = client.subscribe(seen.append)
    unsubscribe()
    client.data_received(captured.STATUS_STUDY_BATHROOM)
    assert seen == []


async def test_set_preset_waits_for_confirmation(client: SAL01Client) -> None:
    stick = attach(client)
    await client.set_preset(0xA0BE, Preset.MEDIUM)
    command = next(f for f in stick.sent if f.payload.startswith(b"A2"))
    assert command.address == 0xA0BE
    assert command.payload == b"A2\x01B05%"
    # The confirmation from the stick was acknowledged too.
    assert stick.sent[-1].payload == b" 3\x00"


async def test_set_temperature(client: SAL01Client) -> None:
    stick = attach(client)
    await client.set_temperature(0xA0BE, 19.5)
    assert stick.sent[0].payload == b"A2\x01B06G"


async def test_command_counter_increments(client: SAL01Client) -> None:
    stick = attach(client)
    await client.set_preset(0xA0BE, Preset.LOW)
    await client.set_preset(0xA0BE, Preset.FROST)
    counters = [f.payload[2] for f in stick.sent if f.payload.startswith(b"A2")]
    assert counters == [1, 2]


async def test_missing_confirmation_times_out(client: SAL01Client) -> None:
    attach(client, confirm=False)
    with pytest.raises(SAL01TimeoutError):
        await client.set_preset(0xA0BE, Preset.LOW)


async def test_missing_receipt_retries_then_fails(client: SAL01Client) -> None:
    stick = attach(client, answer=False)
    with pytest.raises(SAL01TimeoutError):
        await client.refresh(datetime(2026, 10, 28, tzinfo=UTC))
    assert len(stick.sent) == client_module.RECEIPT_ATTEMPTS
    assert len({f.seq for f in stick.sent}) == client_module.RECEIPT_ATTEMPTS


async def test_refresh_sends_time_sync(client: SAL01Client) -> None:
    stick = attach(client)
    await client.refresh(datetime(2026, 10, 28, 8, 32, 57, tzinfo=UTC))
    assert stick.sent[0].address == 0
    assert stick.sent[0].payload == Frame.decode(captured.GATEWAY_TIME_SYNC).payload


async def test_request_reports(client: SAL01Client) -> None:
    stick = attach(client)
    await client.request_reports()
    expected = Frame.decode(captured.GATEWAY_REPORT_REQUEST)
    assert (stick.sent[0].address, stick.sent[0].payload) == (
        expected.address,
        expected.payload,
    )


async def test_announce_online(client: SAL01Client) -> None:
    stick = attach(client)
    await client.announce_online()
    assert stick.sent[0].address == 0
    assert stick.sent[0].payload == Frame.decode(captured.GATEWAY_ONLINE).payload


async def test_get_devices(client: SAL01Client) -> None:
    attach(client)
    devices = await client.get_devices()
    assert len(devices) == 12


async def test_connect_waits_for_connection_made(
    client: SAL01Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    # serial_asyncio_fast calls connection_made on a later loop iteration, after
    # create_serial_connection has returned.
    async def fake_create(loop, factory, port, **kwargs):  # type: ignore[no-untyped-def]
        protocol = factory()
        loop.call_soon(protocol.connection_made, FakeStick(protocol))
        return None, protocol

    import serial_asyncio_fast

    monkeypatch.setattr(serial_asyncio_fast, "create_serial_connection", fake_create)
    await client.connect()
    assert client.connected
    await client.set_preset(0xA0BE, Preset.LOW)


async def test_connect_fails_for_missing_port(client: SAL01Client) -> None:
    with pytest.raises(SAL01ConnectionError):
        await client.connect()


async def test_commands_fail_when_not_connected(client: SAL01Client) -> None:
    with pytest.raises(SAL01ConnectionError):
        await client.set_preset(0xA0BE, Preset.LOW)


async def test_connection_lost_fails_pending_and_notifies(client: SAL01Client) -> None:
    stick = attach(client, confirm=False)
    lost: list[Exception | None] = []
    client.on_disconnect(lost.append)

    task = asyncio.create_task(client.set_preset(0xA0BE, Preset.LOW))
    await asyncio.sleep(0.01)
    stick.close()

    with pytest.raises(SAL01ConnectionError):
        await task
    assert lost == [None]
    assert not client.connected
