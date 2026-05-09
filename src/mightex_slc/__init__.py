"""Mightex SLC LED Controller Python Interface"""

from .constants import (
    FOLLOWER_DURATION_US,
    MAX_CURRENT_NORMAL_MA,
    MAX_CURRENT_PULSED_MA,
)
from .controller import MightexSLC
from .exceptions import (
    CommandError,
    MightexConnectionError,
    MightexError,
    MightexTimeoutError,
    ValidationError,
)
from .protocol import DeviceInfo, Mode, TriggerPolarity

__all__ = [
    "CommandError",
    "DeviceInfo",
    "FOLLOWER_DURATION_US",
    "MAX_CURRENT_NORMAL_MA",
    "MAX_CURRENT_PULSED_MA",
    "MightexConnectionError",
    "MightexError",
    "MightexSLC",
    "MightexTimeoutError",
    "Mode",
    "TriggerPolarity",
    "ValidationError",
]
__version__ = "0.1.0"
