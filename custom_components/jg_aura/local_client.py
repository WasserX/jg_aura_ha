"""Client for local control through a SAL01 USB stick, with the same interface as JGClient."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
import logging
import time

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from . import gateway, thermostat
from .jg_client import MODES, RUN_MODES
from .sal01 import (
    Preset,
    SAL01Client,
    SAL01Error,
    ThermostatStatus,
    cloud_id_to_address,
)

_LOGGER = logging.getLogger(__name__)

# The cloud and the stick number presets and modes the same way.
PRESETS_BY_NAME = dict(zip(RUN_MODES, Preset, strict=True))

# How often maintain() should run: it keeps the thermostats' globe icon solid (the
# gateway does so every 6 to 12 minutes).
MAINTENANCE_INTERVAL = timedelta(minutes=5)
# A time sync makes every thermostat report and keeps their clocks right.
SYNC_INTERVAL_SECONDS = 30 * 60
# At startup, stop waiting for reports once none arrived for this long.
STARTUP_QUIET_SECONDS = 2
STARTUP_MAX_SECONDS = 30


class LocalClient:
    """Thermostat access through a SAL01 stick plugged into the Home Assistant host."""

    # Status reports arrive before the command is confirmed: no need to wait.
    refresh_delay = 0.0

    def __init__(self, port: str, names: dict[str, str] | None = None) -> None:
        """Initialize the client; names maps cloud ids to thermostat names."""
        self._sal01 = SAL01Client(port)
        self._names = names or {}
        self._last_sync = 0.0
        self._closing = False

    @property
    def port(self) -> str:
        """Return the serial port."""
        return self._sal01.port

    @property
    def statuses(self) -> dict[int, ThermostatStatus]:
        """Return the latest status of every thermostat that has reported."""
        return self._sal01.statuses

    async def connect(self) -> None:
        """Open the stick and wait for every thermostat to report."""
        self._closing = False
        await self._sal01.connect()
        reported = asyncio.Event()
        unsubscribe = self._sal01.subscribe(lambda _status: reported.set())
        try:
            await self._sync()
            await self._sal01.announce_online()
            # Reports would follow the sync after about 15 s; this gets them at once.
            await self._sal01.request_reports()
            deadline = time.monotonic() + STARTUP_MAX_SECONDS
            while time.monotonic() < deadline:
                reported.clear()
                try:
                    async with asyncio.timeout(STARTUP_QUIET_SECONDS):
                        await reported.wait()
                except TimeoutError:
                    if self.statuses:
                        break
        except SAL01Error:
            await self._sal01.close()
            raise
        finally:
            unsubscribe()
        _LOGGER.debug("%d thermostats reported", len(self.statuses))

    async def close(self) -> None:
        """Close the stick."""
        self._closing = True
        await self._sal01.close()

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Call callback whenever a thermostat reports."""
        return self._sal01.subscribe(lambda _status: callback())

    def on_disconnect(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Call callback when the stick goes away, unless close() was called."""

        def _lost(_exc: Exception | None) -> None:
            if not self._closing:
                callback()

        return self._sal01.on_disconnect(_lost)

    async def get_thermostats(self) -> gateway.Gateway:
        """Return the latest known state (the stick pushes every change)."""
        return self.gateway()

    async def maintain(self) -> None:
        """Keep the globe icon solid and the clocks right; call every MAINTENANCE_INTERVAL."""
        await self._sal01.announce_online()
        if time.monotonic() - self._last_sync > SYNC_INTERVAL_SECONDS:
            await self._sync()

    def gateway(self) -> gateway.Gateway:
        """Build the gateway model from the latest reports."""
        thermostats = [
            _to_thermostat(status, self._names.get(status.cloud_id))
            for status in sorted(self.statuses.values(), key=lambda s: s.cloud_id)
        ]
        return gateway.Gateway("JG-SAL01", "JG Aura SAL01", thermostats)

    async def set_thermostat_preset(self, device_id: str, state_name: str) -> None:
        """Set thermostat preset mode."""
        try:
            await self._sal01.set_preset(
                cloud_id_to_address(device_id), PRESETS_BY_NAME[state_name]
            )
        except SAL01Error as err:
            raise HomeAssistantError(
                f"Could not set {state_name} on thermostat {device_id}: {err}"
            ) from err

    async def set_thermostat_temperature(
        self, device_id: str, temperature: float
    ) -> None:
        """Set thermostat target temperature."""
        try:
            await self._sal01.set_temperature(
                cloud_id_to_address(device_id), temperature
            )
        except (SAL01Error, ValueError) as err:
            raise HomeAssistantError(
                f"Could not set {temperature} on thermostat {device_id}: {err}"
            ) from err

    async def _sync(self) -> None:
        # The thermostats show the time as sent and know nothing of daylight saving:
        # send Home Assistant's local time. Regular syncs carry clock changes over.
        await self._sal01.refresh(dt_util.now())
        self._last_sync = time.monotonic()


def _to_thermostat(status: ThermostatStatus, name: str | None) -> thermostat.Thermostat:
    return thermostat.Thermostat(
        id=status.cloud_id,
        name=name or f"Thermostat {status.cloud_id}",
        on=status.heating,
        state_name=MODES[status.mode],
        temp_current=status.current_temperature,
        temp_set_point=status.target_temperature,
    )
