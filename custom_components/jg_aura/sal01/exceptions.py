"""Exceptions raised by the SAL01 client."""


class SAL01Error(Exception):
    """Base class for SAL01 errors."""


class SAL01ConnectionError(SAL01Error):
    """The serial port could not be opened or was lost."""


class SAL01TimeoutError(SAL01Error):
    """The stick or a thermostat did not answer in time."""
