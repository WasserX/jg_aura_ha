"""HTTP client utilities."""

from __future__ import annotations

import asyncio
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)


async def call_url_with_retry(url: str, attempts: int = 3) -> str:
    """Call a URL with retry logic."""
    for attempt in range(attempts):
        try:
            async with aiohttp.ClientSession() as session, session.get(url) as response:
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
                "Unexpected error calling URL on attempt %d: %s", attempt + 1, err
            )

    raise TimeoutError(f"Failed to call URL after {attempts} attempts")
