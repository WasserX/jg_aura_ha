"""Local control of JG Aura (Salus/Computime) thermostats through a SAL01 USB stick."""

from .client import SAL01Client
from .exceptions import SAL01ConnectionError, SAL01Error, SAL01TimeoutError
from .frame import Frame, FrameDecoder
from .protocol import (
    Mode,
    Preset,
    ThermostatStatus,
    address_to_cloud_id,
    cloud_id_to_address,
)

__all__ = [
    "Frame",
    "FrameDecoder",
    "Mode",
    "Preset",
    "SAL01Client",
    "SAL01ConnectionError",
    "SAL01Error",
    "SAL01TimeoutError",
    "ThermostatStatus",
    "address_to_cloud_id",
    "cloud_id_to_address",
]
