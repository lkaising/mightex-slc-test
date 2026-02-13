"""
Mightex SLC RS232 protocol: command building, ack checking, and response parsing.

This module sits between the transport (raw serial I/O) and the controller
(user-facing API).  It knows how to:

* validate parameters before they become commands,
* build properly formatted command strings,
* check response ack codes (``##``, ``#!``, ``#?``),
* parse typed data out of response strings.

It does **not** own the serial port — that belongs to
:class:`~mightex_slc.transport.SerialTransport`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum

from .exceptions import CommandError, ValidationError
from .transport import SerialTransport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums & Data
# ---------------------------------------------------------------------------


class Mode(IntEnum):
    """LED operating modes."""

    DISABLE = 0
    NORMAL = 1
    STROBE = 2
    TRIGGER = 3


class TriggerPolarity(IntEnum):
    """Trigger edge polarity."""

    RISING = 0
    FALLING = 1


@dataclass(frozen=True)
class DeviceInfo:
    """Device information returned from the ``DEVICEINFO`` command."""

    firmware_version: str
    module_number: str
    serial_number: str

    @classmethod
    def from_response(cls, response: str) -> DeviceInfo:
        """Parse a raw ``DEVICEINFO`` response string.

        Expected format::

            Mightex LED Driver:<fw> Device Module No.:<model> Device Serial No.:<sn>
        """
        firmware = "Unknown"
        module = "Unknown"
        serial_no = "Unknown"

        try:
            if "Driver:" in response:
                firmware = response.split("Driver:")[1].split()[0]
            if "Module No.:" in response:
                module = response.split("Module No.:")[1].split()[0]
            if "Serial No.:" in response:
                serial_no = response.split("Serial No.:")[1].split()[0]
        except (IndexError, AttributeError):
            logger.warning("Failed to fully parse DEVICEINFO response: %r", response)

        return cls(firmware, module, serial_no)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_MIN_CHANNEL = 1
_MAX_CHANNEL = 4
_MAX_STEP = 127
_MAX_DURATION_US = 99_999_999
MAX_CURRENT_NORMAL_MA = 1000
MAX_CURRENT_PULSED_MA = 3500


def _validate_channel(channel: int) -> None:
    if not (_MIN_CHANNEL <= channel <= _MAX_CHANNEL):
        raise ValidationError(f"Channel must be {_MIN_CHANNEL}-{_MAX_CHANNEL}, got {channel}")


def _validate_current(current_ma: int, max_ma: int, label: str = "current") -> None:
    """Validate that *current_ma* is within ``0..max_ma``."""
    if not (0 <= current_ma <= max_ma):
        raise ValidationError(f"{label} must be 0-{max_ma} mA, got {current_ma}")


def _validate_mode(mode: int) -> None:
    try:
        Mode(mode)
    except ValueError as err:
        raise ValidationError(f"Invalid mode {mode}; expected one of {list(Mode)}") from err


def _validate_step(step: int) -> None:
    if not (0 <= step <= _MAX_STEP):
        raise ValidationError(f"Step must be 0-{_MAX_STEP}, got {step}")


def _validate_duration(duration_us: int) -> None:
    if not (0 <= duration_us <= _MAX_DURATION_US):
        raise ValidationError(f"Duration must be 0-{_MAX_DURATION_US} µs, got {duration_us}")


def _validate_repeat(repeat: int) -> None:
    if repeat < 0:
        raise ValidationError(f"Repeat must be >= 0, got {repeat}")


# ---------------------------------------------------------------------------
# Ack checking
# ---------------------------------------------------------------------------


def _check_ack(response: str, cmd: str) -> str:
    """Inspect a response for error codes and raise if found.

    Returns the response string unmodified if no error was detected.
    """
    if response.startswith("#!"):
        raise CommandError(f"Controller error for '{cmd}': {response}")
    if response.startswith("#?"):
        raise CommandError(f"Invalid argument for '{cmd}': {response}")
    if "is not defined" in response:
        raise CommandError(f"Unknown command '{cmd}': {response}")
    return response


def _expect_ack(response: str, cmd: str) -> None:
    """Assert that *response* contains the ``##`` success marker."""
    _check_ack(response, cmd)
    if "##" not in response:
        raise CommandError(f"Expected '##' acknowledgement for '{cmd}', got: {response!r}")


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------


def _parse_mode(response: str, channel: int) -> Mode:
    """Extract a :class:`Mode` value from a ``?MODE`` response."""
    mode_str = response.replace("#", "").strip()
    try:
        return Mode(int(mode_str))
    except (ValueError, TypeError) as exc:
        raise CommandError(f"Unexpected mode response for channel {channel}: {response!r}") from exc


def _parse_normal_params(response: str) -> tuple[int, int]:
    """Extract ``(max_current_ma, set_current_ma)`` from a ``?CURRENT`` response."""
    parts = response.replace("#", "").split()
    if len(parts) < 2:
        raise CommandError(f"Cannot parse normal params from {response!r}")
    try:
        return int(parts[-2]), int(parts[-1])
    except (ValueError, TypeError) as exc:
        raise CommandError(f"Cannot parse normal params from {response!r}") from exc


def _parse_load_voltage(response: str) -> int:
    """Extract a millivolt value from a ``LoadVoltage`` response."""
    try:
        return int(response.split(":")[1])
    except (IndexError, ValueError) as exc:
        raise CommandError(f"Cannot parse load voltage from {response!r}") from exc


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class SLCProtocol:
    """Builds commands, sends them via a transport, and parses responses.

    Args:
        transport: An open :class:`~mightex_slc.transport.SerialTransport`.
    """

    def __init__(self, transport: SerialTransport) -> None:
        self._tx = transport

    # -- Transport helpers --------------------------------------------------

    def _cmd(self, cmd: str) -> str:
        """Send *cmd* through the transport, check for errors, and return."""
        response = self._tx.send(cmd)
        return _check_ack(response, cmd)

    def _cmd_ack(self, cmd: str) -> None:
        """Send *cmd* and assert the controller returns ``##``."""
        response = self._tx.send(cmd)
        _expect_ack(response, cmd)

    # -- Information --------------------------------------------------------

    def device_info(self) -> DeviceInfo:
        """Query model, firmware version, and serial number."""
        response = self._cmd("DEVICEINFO")
        return DeviceInfo.from_response(response)

    def get_mode(self, channel: int) -> Mode:
        """Return the current operating mode of *channel*."""
        _validate_channel(channel)
        response = self._cmd(f"?MODE {channel}")
        return _parse_mode(response, channel)

    def get_normal_params(self, channel: int) -> tuple[int, int]:
        """Return ``(max_current_ma, set_current_ma)`` for *channel*."""
        _validate_channel(channel)
        response = self._cmd(f"?CURRENT {channel}")
        return _parse_normal_params(response)

    def get_load_voltage(self, channel: int) -> int:
        """Return the LED load voltage for *channel* in millivolts."""
        _validate_channel(channel)
        response = self._cmd(f"LoadVoltage {channel}")
        return _parse_load_voltage(response)

    # -- Mode control -------------------------------------------------------

    def set_mode(self, channel: int, mode: int) -> None:
        """Set *channel* to *mode*."""
        _validate_channel(channel)
        _validate_mode(mode)
        self._cmd_ack(f"MODE {channel} {mode}")

    # -- Normal mode --------------------------------------------------------

    def set_normal_params(self, channel: int, max_current_ma: int, set_current_ma: int) -> None:
        """Configure normal-mode parameters for *channel*.

        Both *max_current_ma* and *set_current_ma* are validated against the
        NORMAL-mode ceiling of :data:`MAX_CURRENT_NORMAL_MA` (1000 mA).
        """
        _validate_channel(channel)
        _validate_current(max_current_ma, MAX_CURRENT_NORMAL_MA, "max_current_ma")
        _validate_current(set_current_ma, MAX_CURRENT_NORMAL_MA, "set_current_ma")
        if set_current_ma > max_current_ma:
            raise ValidationError(
                f"set_current_ma ({set_current_ma}) cannot exceed max_current_ma ({max_current_ma})"
            )
        self._cmd_ack(f"NORMAL {channel} {max_current_ma} {set_current_ma}")

    def set_current(self, channel: int, current_ma: int) -> None:
        """Quick-set working current (channel must already be in NORMAL mode).

        Validated against the NORMAL-mode ceiling of
        :data:`MAX_CURRENT_NORMAL_MA` (1000 mA).
        """
        _validate_channel(channel)
        _validate_current(current_ma, MAX_CURRENT_NORMAL_MA)
        self._cmd_ack(f"CURRENT {channel} {current_ma}")

    # -- Strobe mode --------------------------------------------------------

    def set_strobe_params(self, channel: int, max_current_ma: int, repeat: int) -> None:
        """Configure strobe mode for *channel*.

        *max_current_ma* is validated against the pulsed-mode ceiling of
        :data:`MAX_CURRENT_PULSED_MA` (3500 mA).
        """
        _validate_channel(channel)
        _validate_current(max_current_ma, MAX_CURRENT_PULSED_MA, "max_current_ma")
        _validate_repeat(repeat)
        self._cmd_ack(f"STROBE {channel} {max_current_ma} {repeat}")

    def set_strobe_step(self, channel: int, step: int, current_ma: int, duration_us: int) -> None:
        """Set a single strobe profile step.

        *current_ma* is validated against the pulsed-mode ceiling of
        :data:`MAX_CURRENT_PULSED_MA` (3500 mA).
        """
        _validate_channel(channel)
        _validate_step(step)
        _validate_current(current_ma, MAX_CURRENT_PULSED_MA, "current_ma")
        _validate_duration(duration_us)
        self._cmd_ack(f"STRP {channel} {step} {current_ma} {duration_us}")

    # -- Trigger mode -------------------------------------------------------

    def set_trigger_params(
        self,
        channel: int,
        max_current_ma: int,
        polarity: TriggerPolarity = TriggerPolarity.RISING,
    ) -> None:
        """Configure trigger mode for *channel*.

        *max_current_ma* is validated against the pulsed-mode ceiling of
        :data:`MAX_CURRENT_PULSED_MA` (3500 mA).
        """
        _validate_channel(channel)
        _validate_current(max_current_ma, MAX_CURRENT_PULSED_MA, "max_current_ma")
        self._cmd_ack(f"TRIGGER {channel} {max_current_ma} {int(polarity)}")

    def set_trigger_step(self, channel: int, step: int, current_ma: int, duration_us: int) -> None:
        """Set a single trigger profile step.

        *current_ma* is validated against the pulsed-mode ceiling of
        :data:`MAX_CURRENT_PULSED_MA` (3500 mA).
        """
        _validate_channel(channel)
        _validate_step(step)
        _validate_current(current_ma, MAX_CURRENT_PULSED_MA, "current_ma")
        _validate_duration(duration_us)
        self._cmd_ack(f"TRIGP {channel} {step} {current_ma} {duration_us}")

    # -- System -------------------------------------------------------------

    def store_settings(self) -> None:
        """Save current settings to non-volatile memory."""
        self._cmd_ack("STORE")

    def reset(self) -> None:
        """Perform a soft reset."""
        self._cmd_ack("RESET")

    def restore_defaults(self) -> None:
        """Restore factory defaults."""
        self._cmd_ack("RESTOREDEF")

    def echo_off(self) -> None:
        """Disable command echo (recommended for programmatic use)."""
        # Intentionally bypasses _cmd_ack — the controller does not ack ECHOOFF
        self._tx.send("ECHOOFF")
