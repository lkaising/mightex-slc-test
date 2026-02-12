"""
Mightex SLC LED Controller Interface

Clean Python API for controlling Mightex Sirius LED drivers via RS232.
Supports the SLC-SA04-U/S (4-channel) and compatible controllers.

Protocol details:
    - Baud: 9600, 8N1
    - Command termination: LF+CR (0x0A 0x0D)
    - Response codes: ## (ok), #! (error), #? (bad arg), #data (data response)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

import serial

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MightexError(Exception):
    """Base exception for all Mightex SLC errors."""


class ConnectionError(MightexError):  # noqa: A001 – intentional shadow of builtin
    """Raised when the serial connection is unavailable or fails."""


class CommandError(MightexError):
    """Raised when the controller returns an error response."""


class ValidationError(MightexError):
    """Raised when an argument fails pre-send validation."""


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
    """Device information returned from the DEVICEINFO command."""

    firmware_version: str
    module_number: str
    serial_number: str

    @classmethod
    def from_response(cls, response: str) -> DeviceInfo:
        """Parse a raw DEVICEINFO response string.

        Expected format (single line):
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
_MAX_CURRENT_MA = 2000  # conservative upper bound for SA modules


def _validate_channel(channel: int) -> None:
    if not (_MIN_CHANNEL <= channel <= _MAX_CHANNEL):
        raise ValidationError(f"Channel must be {_MIN_CHANNEL}–{_MAX_CHANNEL}, got {channel}")


def _validate_current(current_ma: int, label: str = "current") -> None:
    if not (0 <= current_ma <= _MAX_CURRENT_MA):
        raise ValidationError(f"{label} must be 0–{_MAX_CURRENT_MA} mA, got {current_ma}")


def _validate_mode(mode: int) -> None:
    try:
        Mode(mode)
    except ValueError:
        raise ValidationError(f"Invalid mode {mode}; expected one of {list(Mode)}")


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------


class MightexSLC:
    """Interface for Mightex SLC LED Controller via RS232.

    Use as a context manager for automatic connection handling::

        with MightexSLC('/dev/ttyUSB0') as led:
            led.enable_channel(1, current_ma=50)
    """

    # Keep class-level aliases for backward compatibility
    MODE_DISABLE = Mode.DISABLE
    MODE_NORMAL = Mode.NORMAL
    MODE_STROBE = Mode.STROBE
    MODE_TRIGGER = Mode.TRIGGER

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baud: int = 9600,
        timeout: float = 1.0,
    ) -> None:
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._ser: Optional[serial.Serial] = None

    # -- Context manager ----------------------------------------------------

    def __enter__(self) -> MightexSLC:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()

    # -- Connection ---------------------------------------------------------

    def connect(self) -> None:
        """Open the serial connection and disable command echo."""
        logger.info("Opening serial port %s at %d baud", self.port, self.baud)
        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
            )
        except serial.SerialException as exc:
            raise ConnectionError(f"Cannot open {self.port}: {exc}") from exc

        self._send_command("ECHOOFF")
        logger.debug("Echo disabled")

    def disconnect(self) -> None:
        """Close the serial connection (safe to call multiple times)."""
        if self._ser and self._ser.is_open:
            self._ser.close()
            logger.info("Serial port %s closed", self.port)

    @property
    def is_connected(self) -> bool:
        """Return True if the serial port is open."""
        return self._ser is not None and self._ser.is_open

    # -- Low-level I/O ------------------------------------------------------

    def _send_command(self, cmd: str, delay: float = 0.2) -> str:
        """Send a command string and return the stripped response.

        Args:
            cmd: Command without termination characters.
            delay: Seconds to wait after writing before reading.

        Returns:
            Decoded response with leading/trailing whitespace removed.

        Raises:
            ConnectionError: If the port is not open.
            CommandError: If the controller signals an error.
        """
        if not self.is_connected:
            raise ConnectionError("Serial port not open — call connect() first.")

        assert self._ser is not None  # for type-checker after is_connected
        logger.debug("TX: %s", cmd)

        self._ser.write(f"{cmd}\n\r".encode("ascii"))
        time.sleep(delay)

        n = self._ser.in_waiting
        raw = self._ser.read(n) if n else b""
        response = raw.decode("ascii", errors="replace").strip()
        logger.debug("RX: %s", response)

        # Check for controller-reported errors
        if response.startswith("#!"):
            raise CommandError(f"Controller error for '{cmd}': {response}")
        if response.startswith("#?"):
            raise CommandError(f"Invalid argument for '{cmd}': {response}")
        if "is not defined" in response:
            raise CommandError(f"Unknown command '{cmd}': {response}")

        return response

    # -- Information --------------------------------------------------------

    def get_device_info(self) -> DeviceInfo:
        """Query model, firmware version, and serial number."""
        response = self._send_command("DEVICEINFO")
        return DeviceInfo.from_response(response)

    def get_mode(self, channel: int) -> Mode:
        """Return the current operating mode of *channel*."""
        _validate_channel(channel)
        response = self._send_command(f"?MODE {channel}")
        mode_str = response.replace("#", "").strip()
        try:
            return Mode(int(mode_str))
        except (ValueError, TypeError) as exc:
            raise CommandError(
                f"Unexpected mode response for channel {channel}: {response!r}"
            ) from exc

    def get_normal_params(self, channel: int) -> tuple[int, int]:
        """Return ``(max_current_ma, set_current_ma)`` for *channel*.

        The response contains calibration values followed by Imax and Iset as
        the last two integers.
        """
        _validate_channel(channel)
        response = self._send_command(f"?CURRENT {channel}")
        parts = response.replace("#", "").split()
        if len(parts) >= 2:
            return int(parts[-2]), int(parts[-1])
        raise CommandError(f"Cannot parse normal params from {response!r}")

    def get_load_voltage(self, channel: int) -> int:
        """Return the LED load voltage for *channel* in millivolts."""
        _validate_channel(channel)
        response = self._send_command(f"LoadVoltage {channel}")
        # Expected: #<channel>:<voltage_mv>
        try:
            return int(response.split(":")[1])
        except (IndexError, ValueError) as exc:
            raise CommandError(f"Cannot parse load voltage from {response!r}") from exc

    # -- Mode control -------------------------------------------------------

    def set_mode(self, channel: int, mode: int) -> bool:
        """Set *channel* to *mode* (see :class:`Mode`).

        Returns:
            ``True`` if the controller acknowledged successfully.
        """
        _validate_channel(channel)
        _validate_mode(mode)
        response = self._send_command(f"MODE {channel} {mode}")
        return "##" in response

    # -- Normal mode --------------------------------------------------------

    def set_normal_mode(self, channel: int, max_current_ma: int, set_current_ma: int) -> bool:
        """Configure normal-mode parameters for *channel*.

        Args:
            channel: Channel number (1-based).
            max_current_ma: Maximum allowed current (mA).
            set_current_ma: Working current (mA).
        """
        _validate_channel(channel)
        _validate_current(max_current_ma, "max_current_ma")
        _validate_current(set_current_ma, "set_current_ma")
        if set_current_ma > max_current_ma:
            raise ValidationError(
                f"set_current_ma ({set_current_ma}) cannot exceed max_current_ma ({max_current_ma})"
            )
        response = self._send_command(f"NORMAL {channel} {max_current_ma} {set_current_ma}")
        return "##" in response

    def set_current(self, channel: int, current_ma: int) -> bool:
        """Quick-set the working current while already in NORMAL mode.

        Args:
            channel: Channel number (1-based).
            current_ma: Working current (mA).
        """
        _validate_channel(channel)
        _validate_current(current_ma)
        response = self._send_command(f"CURRENT {channel} {current_ma}")
        return "##" in response

    # -- Convenience --------------------------------------------------------

    def enable_channel(
        self,
        channel: int,
        current_ma: int,
        max_current_ma: Optional[int] = None,
    ) -> bool:
        """Enable *channel* in NORMAL mode at *current_ma*.

        If *max_current_ma* is not given it defaults to ``2 × current_ma``.
        """
        if max_current_ma is None:
            max_current_ma = current_ma * 2

        if not self.set_normal_mode(channel, max_current_ma, current_ma):
            return False
        return self.set_mode(channel, Mode.NORMAL)

    def disable_channel(self, channel: int) -> bool:
        """Disable *channel* (turn the LED off)."""
        return self.set_mode(channel, Mode.DISABLE)

    # -- Strobe mode --------------------------------------------------------

    def set_strobe_params(self, channel: int, max_current_ma: int, repeat: int) -> bool:
        """Configure strobe mode for *channel*.

        Args:
            channel: Channel number (1-based).
            max_current_ma: Maximum current (mA).
            repeat: Number of repetitions (0 = continuous).
        """
        _validate_channel(channel)
        _validate_current(max_current_ma, "max_current_ma")
        response = self._send_command(f"STROBE {channel} {max_current_ma} {repeat}")
        return "##" in response

    def set_strobe_step(
        self,
        channel: int,
        step: int,
        current_ma: int,
        duration_us: int,
    ) -> bool:
        """Set a single strobe profile step.

        Use ``current_ma=0, duration_us=0`` as the end-of-profile marker.
        """
        _validate_channel(channel)
        response = self._send_command(f"STRP {channel} {step} {current_ma} {duration_us}")
        return "##" in response

    # -- Trigger mode -------------------------------------------------------

    def set_trigger_params(
        self,
        channel: int,
        max_current_ma: int,
        polarity: TriggerPolarity = TriggerPolarity.RISING,
    ) -> bool:
        """Configure trigger mode for *channel*."""
        _validate_channel(channel)
        _validate_current(max_current_ma, "max_current_ma")
        response = self._send_command(f"TRIGGER {channel} {max_current_ma} {int(polarity)}")
        return "##" in response

    def set_trigger_step(
        self,
        channel: int,
        step: int,
        current_ma: int,
        duration_us: int,
    ) -> bool:
        """Set a single trigger profile step."""
        _validate_channel(channel)
        response = self._send_command(f"TRIGP {channel} {step} {current_ma} {duration_us}")
        return "##" in response

    # -- System -------------------------------------------------------------

    def store_settings(self) -> bool:
        """Save current settings to non-volatile memory."""
        response = self._send_command("STORE")
        return "##" in response

    def reset(self) -> bool:
        """Perform a soft reset."""
        response = self._send_command("RESET")
        return "##" in response

    def restore_defaults(self) -> bool:
        """Restore factory defaults."""
        response = self._send_command("RESTOREDEF")
        return "##" in response


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def get_controller(port: str = "/dev/ttyUSB0") -> MightexSLC:
    """Return a controller instance (use as a context manager).

    Example::

        with get_controller('/dev/ttyUSB0') as led:
            led.enable_channel(1, current_ma=50)
    """
    return MightexSLC(port)
