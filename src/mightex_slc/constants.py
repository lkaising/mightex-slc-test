"""Shared runtime constants for the Mightex SLC LED controller.

This is the canonical source of truth for protocol limits and controller
defaults.  Other modules should import from here rather than defining
their own copies.
"""

# ---------------------------------------------------------------------------
# Protocol / validation limits
# ---------------------------------------------------------------------------

MIN_CHANNEL = 1
MAX_CHANNEL = 4
MAX_STEP = 127
MAX_DURATION_US = 99_999_999
MAX_CURRENT_NORMAL_MA = 1000
MAX_CURRENT_PULSED_MA = 3500
FOLLOWER_DURATION_US = 9999  # Special Tset value: output follows trigger input level

# ---------------------------------------------------------------------------
# Controller / runtime defaults
# ---------------------------------------------------------------------------

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 9600
DEFAULT_TIMEOUT = 1.0
