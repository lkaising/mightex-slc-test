"""Mightex SLC LED Controller Python Interface"""

from .controller import MightexSLC, get_controller
from .exceptions import (
    CommandError,
    ConnectionError,
    MightexError,
    TimeoutError,
    ValidationError,
)
from .protocol import DeviceInfo, Mode, TriggerPolarity

__all__ = [
    "CommandError",
    "ConnectionError",
    "DeviceInfo",
    "MightexError",
    "MightexSLC",
    "Mode",
    "TimeoutError",
    "TriggerPolarity",
    "ValidationError",
    "get_controller",
]
__version__ = "0.1.0"
