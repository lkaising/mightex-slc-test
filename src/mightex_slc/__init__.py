"""Mightex SLC LED Controller Python Interface"""

from .constants import (
    FOLLOWER_DURATION_US,
    MAX_CURRENT_NORMAL_MA,
    MAX_CURRENT_PULSED_MA,
)
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
    "FOLLOWER_DURATION_US",
    "MightexError",
    "MightexSLC",
    "Mode",
    "TimeoutError",
    "TriggerPolarity",
    "ValidationError",
    "get_controller",
    "MAX_CURRENT_NORMAL_MA",
    "MAX_CURRENT_PULSED_MA",
]
__version__ = "0.1.0"
