"""Fixtures for JGAura tests."""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any, ClassVar
from unittest.mock import patch

import pytest

from custom_components.jg_aura import local_client
from custom_components.jg_aura.sal01 import (
    Preset,
    SAL01ConnectionError,
    ThermostatStatus,
)
from custom_components.jg_aura.sal01.protocol import decode_status

pytest_plugins = "pytest_homeassistant_custom_component"

PORT = "/dev/serial/by-id/usb-Silicon_Labs_CP2104_USB_to_UART_Bridge_Controller_014E32FB-if00-port0"

# Status payloads as captured from real thermostats.
DOWNSTAIRS_BATHROOM = decode_status(0xA0BE, b'B1$)E*0000"LDH*fKW?c  =P,')  # bea0
STUDY = decode_status(0xB0B7, b"B1%)F*0000$NF.*fKW?c  =P,")  # b7b0


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Enable custom integrations in every test."""


@pytest.fixture(autouse=True)
def fast_startup() -> Generator[None]:
    """Do not wait seconds for thermostats at startup."""
    with patch.object(local_client, "STARTUP_QUIET_SECONDS", 0.01):
        yield


class FakeSAL01:
    """Stand-in for SAL01Client that behaves like a stick with two thermostats."""

    instances: ClassVar[list[FakeSAL01]] = []
    fail_connect: ClassVar[bool] = False

    def __init__(self, port: str) -> None:
        self.port = port
        self.statuses: dict[int, ThermostatStatus] = {}
        self.commands: list[tuple[Any, ...]] = []
        self.connected = False
        self._status_callbacks: list[Callable[[ThermostatStatus], None]] = []
        self._disconnect_callbacks: list[Callable[[Exception | None], None]] = []
        FakeSAL01.instances.append(self)

    async def connect(self) -> None:
        if FakeSAL01.fail_connect:
            raise SAL01ConnectionError("no such port")
        self.connected = True

    async def close(self) -> None:
        if self.connected:
            self.connected = False
            self.lose_connection()

    def lose_connection(self) -> None:
        self.connected = False
        for callback in list(self._disconnect_callbacks):
            callback(None)

    def subscribe(
        self, callback: Callable[[ThermostatStatus], None]
    ) -> Callable[[], None]:
        self._status_callbacks.append(callback)
        return lambda: self._status_callbacks.remove(callback)

    def on_disconnect(
        self, callback: Callable[[Exception | None], None]
    ) -> Callable[[], None]:
        self._disconnect_callbacks.append(callback)
        return lambda: self._disconnect_callbacks.remove(callback)

    async def refresh(self, now: Any = None) -> None:
        # The real thermostats only report about 15 s after a time sync.
        self.commands.append(("refresh",))
        self.synced_at = now

    async def request_reports(self) -> None:
        self.commands.append(("report",))
        for status in (DOWNSTAIRS_BATHROOM, STUDY):
            self.report(status)

    async def announce_online(self) -> None:
        self.commands.append(("online",))

    async def get_devices(self) -> list[int]:
        return [0xCFB2, 0xA0BE, 0xB0B7]

    async def set_preset(self, address: int, preset: Preset, duration: int = 1) -> None:
        self.commands.append(("preset", address, preset))

    async def set_temperature(self, address: int, temperature: float) -> None:
        self.commands.append(("temperature", address, temperature))

    def report(self, status: ThermostatStatus) -> None:
        self.statuses[status.address] = status
        for callback in list(self._status_callbacks):
            callback(status)


@pytest.fixture
def fake_stick() -> Generator[type[FakeSAL01]]:
    """Replace the SAL01 client with FakeSAL01."""
    FakeSAL01.instances = []
    FakeSAL01.fail_connect = False
    with patch.object(local_client, "SAL01Client", FakeSAL01):
        yield FakeSAL01
