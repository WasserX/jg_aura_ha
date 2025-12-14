"""Client for JGAura API."""

from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
import logging
from typing import Any
import urllib.parse

import aiohttp
from defusedxml import ElementTree as ET

from . import gateway, hotwater, thermostat

_LOGGER = logging.getLogger(__name__)

APPID = "1097"
RUN_MODES = [
    "Auto",
    "High",
    "Medium",
    "Low",
    "Party",
    "Away",
    "Frost",
]
RUN_MODES_WITH_DURATION = [
    "Party",
    "Away",
]
HEATING_MODES = [
    "Auto",
    "High",
    "Medium",
    "Low",
    "Party",
]

# There are more modes than actual presets. However, if a mode does not match
# a preset HA can show the mode, but the preset is left blank. As such, make
# sure the values match the 'preset' you want to display.
MODES = [
    "OFFLINE",
    "Auto",  # Auto High
    "Auto",  # Auto Medium
    "Auto",  # Auto Low
    "High",
    "Medium",
    "Low",
    "Party",
    "Away",
    "Frost",
    "ON",
    "ON",
    "UNDEFINED",
    "UNDEFINED",
    "UNDEFINED",
    "UNDEFINED",
    "OFFLINE",
    "Auto",  # Auto High
    "Auto",  # Auto Medium
    "Auto",  # Auto Low
    "High",
    "Medium",
    "Low",
    "Party",
    "Frost",
    "ON",
]

# When setting values through the API, a delay is required to get the updated values,
# otherwise the API may return stale data.
API_DELAY_SECONDS = 1.5


class JGClient:
    """Client for interacting with JGAura API."""

    def __init__(self, host: str, email: str, password: str) -> None:
        """Initialize the client."""
        self.host = host
        self.email = email
        self.hashed_password = hashlib.md5(password.encode()).hexdigest()
        self.gateway_device_id: str | None = None
        self.logged_in = False
        self.security_token: str | None = None

    async def get_thermostats(self) -> gateway.Gateway:
        """Get all thermostats from the gateway."""
        if not self.logged_in:
            await self._login()
        return await self._request_devices(self._extract_thermostats)

    async def get_hot_water(self) -> hotwater.HotWater:
        """Get hot water status from the gateway."""
        if not self.logged_in:
            await self._login()
        return await self._request_devices(self._extract_hot_water)

    async def set_thermostat_preset(self, device_id: str, state_name: str) -> None:
        """Set thermostat preset mode."""
        if not self.logged_in:
            await self._login()
        await self._set_preset(device_id, state_name)

    async def set_thermostat_temperature(
        self, device_id: str, temperature: float
    ) -> None:
        """Set thermostat target temperature."""
        if not self.logged_in:
            await self._login()
        await self._set_temperature(device_id, temperature)

    async def set_hot_water(self, device_id: str, is_on: bool) -> None:
        """Set hot water on or off."""
        if not self.logged_in:
            await self._login()
        await self._set_hot_water(device_id, is_on)

    async def _login(self) -> None:
        """Log in to the API."""
        _LOGGER.info("Attempting login for %s", self.email)
        self.gateway_device_id = await self._request_gateway_device_id()
        _LOGGER.info("Connected to device %s", self.gateway_device_id)
        self.logged_in = True

    async def _request_gateway_device_id(self) -> str:
        """Request and return the gateway device ID."""
        login_url = (
            f"{self.host}/userLogin?appId={APPID}&name={self.email}"
            f"&password={self.hashed_password}&timestamp={self._get_date()}"
        )
        result = await self._call_url_with_retry(login_url)
        user_id = self._extract_user_details_from_login(result)

        device_id_url = (
            f"{self.host}/getDeviceList?secToken={self.security_token}"
            f"&userId={user_id}&timestamp={self._get_date()}"
        )
        result = await self._call_url_with_retry(device_id_url)
        return self._extract_gateway_device_id(result)

    async def _request_devices(
        self, parse_function: Any
    ) -> gateway.Gateway | hotwater.HotWater:
        """Request device data from the API."""
        assert self.gateway_device_id is not None
        url = (
            f"{self.host}/setMultiDeviceAttributes2?secToken={self.security_token}"
            f"&devId={self.gateway_device_id}&name1=B01&value1=5"
            f"&timestamp={self._get_date()}"
        )
        await self._fetch_url_with_login_retry(url)

        url = (
            f"{self.host}/getDeviceAttributesWithValues?secToken={self.security_token}"
            f"&devId={self.gateway_device_id}&deviceTypeId=1&timestamp={self._get_date()}"
        )
        response_content = await self._fetch_url_with_login_retry(url)
        return parse_function(response_content)

    async def _set_preset(self, device_id: str, state_name: str) -> None:
        """Set thermostat preset mode."""
        duration = str(1).zfill(2) if state_name in RUN_MODES_WITH_DURATION else ""

        payload = urllib.parse.quote(
            f"!{device_id}{chr(int(RUN_MODES.index(state_name) + 35))}{duration}"
        )
        assert self.gateway_device_id is not None
        url = (
            f"{self.host}/setMultiDeviceAttributes2?secToken={self.security_token}"
            f"&devId={self.gateway_device_id}&name1=B05&value1={payload}"
            f"&timestamp={self._get_date()}"
        )
        result = await self._fetch_url_with_login_retry(url)
        self._validate_operation_response(result)

    async def _set_temperature(self, device_id: str, temperature: float) -> None:
        """Set thermostat target temperature."""
        payload = urllib.parse.quote(f"!{device_id}{chr(int(temperature * 2 + 32))}")
        assert self.gateway_device_id is not None
        url = (
            f"{self.host}/setMultiDeviceAttributes2?secToken={self.security_token}"
            f"&devId={self.gateway_device_id}&name1=B06&value1={payload}"
            f"&timestamp={self._get_date()}"
        )
        result = await self._fetch_url_with_login_retry(url)
        self._validate_operation_response(result)

    async def _set_hot_water(self, device_id: str, is_on: bool) -> None:
        """Set hot water on or off."""
        heating_state = "# " if is_on else "$ "
        payload = urllib.parse.quote(f"!{device_id}{heating_state}")
        assert self.gateway_device_id is not None
        url = (
            f"{self.host}/setMultiDeviceAttributes2?secToken={self.security_token}"
            f"&devId={self.gateway_device_id}&name1=B05&value1={payload}"
            f"&timestamp={self._get_date()}"
        )
        result = await self._fetch_url_with_login_retry(url)
        self._validate_operation_response(result)

    async def _fetch_url_with_login_retry(self, url: str) -> str:
        """Fetch a URL with automatic login retry on failure."""
        response_content = None
        for attempt in range(3):
            try:
                async with (
                    aiohttp.ClientSession() as session,
                    session.get(url) as response,
                ):
                    if response.status == 200:
                        response_content = await response.text()
                        break

                    _LOGGER.error(
                        "Request to URL failed with status code %s on attempt %d,"
                        " retrying",
                        response.status,
                        attempt + 1,
                    )
                    self.logged_in = False
                    await self._login()
            except aiohttp.ClientError as err:
                _LOGGER.error(
                    "Unexpected error making request to URL on attempt %d: %s",
                    attempt + 1,
                    err,
                )

        if response_content is None:
            raise TimeoutError("Failed to fetch URL after 3 attempts")
        return response_content

    async def _call_url_with_retry(self, url: str, attempts: int = 3) -> str:
        """Call a URL with retry logic."""
        for attempt in range(attempts):
            try:
                async with (
                    aiohttp.ClientSession() as session,
                    session.get(url) as response,
                ):
                    if response.status == 200:
                        return await response.text()

                    _LOGGER.warning(
                        "Calling URL resulted in status code %s on attempt %d",
                        response.status,
                        attempt + 1,
                    )
                    await asyncio.sleep(1)
            except aiohttp.ClientError as err:
                _LOGGER.error(
                    "Unexpected error calling URL on attempt %d: %s",
                    attempt + 1,
                    err,
                )

        raise TimeoutError(f"Failed to call URL after {attempts} attempts")

    def _extract_gateway_device_id(self, response: str) -> str:
        """Extract gateway device ID from login response."""
        tree = ET.fromstring(response)
        dev_id = tree.findtext("devList/devId")
        if dev_id is None:
            raise ValueError("Could not extract device ID from response")
        return dev_id

    def _extract_user_details_from_login(self, response: str) -> str:
        """Extract user details from login response."""
        tree = ET.fromstring(response)
        self.security_token = tree.findtext("securityToken")
        user_id = tree.findtext("userId")
        if user_id is None:
            raise ValueError("Could not extract user ID from response")
        return user_id

    def _get_date(self) -> str:
        """Get current timestamp for API requests."""
        return str(datetime.now().timestamp()).replace(".", "")

    def _extract_thermostats(self, response: str) -> gateway.Gateway:
        """Extract thermostat information from API response."""
        tree = ET.fromstring(response)
        try:
            thermostat_display_node_names = ["S02", "S03"]
            summary_node_names = ["001", "002", "003"]

            items = []
            for element in tree.findall("./attrList"):
                name = element.findtext("name")
                if name in thermostat_display_node_names or name in summary_node_names:
                    value = element.findtext("value")
                    if value is not None:
                        value = (
                            value.replace("&lt;", "<")
                            .replace("&gt;", ">")
                            .replace("&amp;", "&")
                        )
                        items.append(
                            {"Id": element.findtext("id"), "Name": name, "Value": value}
                        )

            summaries = {}
            for entry_value in (
                x.get("Value") for x in items if x.get("Name") in summary_node_names
            ):
                for element in (
                    entry_value[i : i + 8] for i in range(0, len(entry_value), 8)
                ):
                    if len(element) == 8:
                        id_val = element[0:4]
                        summaries[id_val] = element[4:]

            thermostats = []
            for entry_value in (
                x.get("Value")
                for x in items
                if x.get("Name") in thermostat_display_node_names
            ):
                for element in (x for x in entry_value.split(",") if len(x) > 4):
                    id_val = element[0:4]
                    summary = summaries.get(id_val)
                    if summary is not None:
                        thermostats.append(
                            thermostat.Thermostat(
                                id_val,
                                element[4:],
                                ord(summary[1]) - 32 > 9,
                                MODES[ord(summary[1]) - 32],
                                (ord(summary[2]) - 32) * 0.5,
                                (ord(summary[3]) - 32) * 0.5,
                            )
                        )

            return gateway.Gateway("JG-Gateway", "JG-Gateway", thermostats)

        except Exception as err:
            _LOGGER.error(
                "Unexpected error processing thermostat results: %s\n%s", err, response
            )
            raise

    def _extract_hot_water(self, response: str) -> hotwater.HotWater:
        """Extract hot water information from API response."""
        tree = ET.fromstring(response)
        try:
            items = []
            for element in tree.findall("./attrList"):
                value = element.findtext("value")
                if value is not None:
                    value = (
                        value.replace("&lt;", "<")
                        .replace("&gt;", ">")
                        .replace("&amp;", "&")
                    )
                    items.append({"Id": element.findtext("id"), "Value": value})

            hot_water_on = False
            hot_water_id_items = [item for item in items if item.get("Id") == "2272"]
            if not hot_water_id_items:
                raise ValueError("Could not find hot water ID in response")  # noqa: TRY301

            hot_water_id = hot_water_id_items[0].get("Value", "").strip()
            hot_water_id = hot_water_id[1 : len(hot_water_id) - 1]

            summary_items = [item for item in items if item.get("Id") == "2257"]
            if not summary_items:
                raise ValueError("Could not find hot water summary in response")  # noqa: TRY301

            summary_value = summary_items[0].get("Value", "")
            for element in [
                summary_value[i : i + 8] for i in range(0, len(summary_value), 8)
            ]:
                if hot_water_id in element:
                    hot_water_on = element[0 : len(hot_water_id) + 2].endswith("3")
                    break

            return hotwater.HotWater(hot_water_id, hot_water_on)

        except Exception as err:
            _LOGGER.error(
                "Unexpected error processing hot water results: %s\n%s", err, response
            )
            raise

    def _validate_operation_response(self, response: str) -> None:
        """Validate the response from a set operation."""
        tree = ET.fromstring(response)
        response_code = tree.find("retCode")
        if response_code is None or response_code.text != "0":
            raise ValueError("Operation failed; unexpected response code")
