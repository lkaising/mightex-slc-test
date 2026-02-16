"""
Mightex SLC LED Controller — user-facing API.

This is the primary interface for controlling Mightex Sirius LED drivers.
It composes :class:`~mightex_slc.transport.SerialTransport` and
:class:`~mightex_slc.protocol.SLCProtocol` behind a clean, high-level API.

Example::

    from mightex_slc import get_controller

    with get_controller('/dev/ttyUSB0') as led:
        led.enable_channel(1, current_ma=50)
        led.set_current(1, 100)
        led.disable_channel(1)
"""

from __future__ import annotations

from .constants import (
    DEFAULT_BAUD,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    FOLLOWER_DURATION_US,
    MAX_CURRENT_NORMAL_MA,
)
from .protocol import (
    DeviceInfo,
    Mode,
    SLCProtocol,
    TriggerPolarity,
)
from .transport import SerialTransport


class MightexSLC:
    """Interface for Mightex SLC LED Controller via RS232.

    Use as a context manager for automatic connection handling::

        with MightexSLC('/dev/ttyUSB0') as led:
            led.enable_channel(1, current_ma=50)
    """

    # Class-level aliases for backward compatibility
    MODE_DISABLE = Mode.DISABLE
    MODE_NORMAL = Mode.NORMAL
    MODE_STROBE = Mode.STROBE
    MODE_TRIGGER = Mode.TRIGGER

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baud: int = DEFAULT_BAUD,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._transport = SerialTransport(port=port, baudrate=baud, timeout=timeout)
        self._proto: SLCProtocol | None = None

    # -- Context manager ----------------------------------------------------

    def __enter__(self) -> MightexSLC:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()

    # -- Connection ---------------------------------------------------------

    def connect(self) -> None:
        """Open the serial connection and disable command echo.

        Safe to call when already connected (returns immediately).
        """
        if self.is_connected:
            return
        self._transport.open()
        self._proto = SLCProtocol(self._transport)
        self._proto.echo_off()

    def disconnect(self) -> None:
        """Close the serial connection.

        Clears the protocol reference so that subsequent commands fail
        with a clear "Not connected" error rather than a transport-level
        error on a closed port.  Safe to call repeatedly.
        """
        self._transport.close()
        self._proto = None

    @property
    def is_connected(self) -> bool:
        """Return ``True`` if the serial port is open."""
        return self._transport.is_open

    # -- Internal -----------------------------------------------------------

    @property
    def _p(self) -> SLCProtocol:
        """Return the protocol instance, or raise if not connected."""
        if self._proto is None:
            from .exceptions import ConnectionError

            raise ConnectionError("Not connected — call connect() first.")
        return self._proto

    # -- Information --------------------------------------------------------

    def get_device_info(self) -> DeviceInfo:
        """Query model, firmware version, and serial number."""
        return self._p.device_info()

    def get_mode(self, channel: int) -> Mode:
        """Return the current operating mode of *channel*."""
        return self._p.get_mode(channel)

    def get_normal_params(self, channel: int) -> tuple[int, int]:
        """Return ``(max_current_ma, set_current_ma)`` for *channel*."""
        return self._p.get_normal_params(channel)

    def get_load_voltage(self, channel: int) -> int:
        """Return the LED load voltage for *channel* in millivolts."""
        return self._p.get_load_voltage(channel)

    # -- Mode control -------------------------------------------------------

    def set_mode(self, channel: int, mode: int) -> bool:
        """Set *channel* to *mode* (see :class:`Mode`).

        Returns ``True`` on success.  Raises on any failure.
        """
        self._p.set_mode(channel, mode)
        return True

    # -- Normal mode --------------------------------------------------------

    def set_normal_mode(self, channel: int, max_current_ma: int, set_current_ma: int) -> bool:
        """Configure normal-mode parameters for *channel*.

        Returns ``True`` on success.  Raises on any failure.
        """
        self._p.set_normal_params(channel, max_current_ma, set_current_ma)
        return True

    def set_current(self, channel: int, current_ma: int) -> bool:
        """Quick-set the working current while already in NORMAL mode.

        Returns ``True`` on success.  Raises on any failure.
        """
        self._p.set_current(channel, current_ma)
        return True

    # -- Convenience --------------------------------------------------------

    def enable_channel(
        self,
        channel: int,
        current_ma: int,
        max_current_ma: int = MAX_CURRENT_NORMAL_MA,
    ) -> bool:
        """Enable *channel* in NORMAL mode at *current_ma*.

        *max_current_ma* sets the per-channel safety ceiling (Imax) and
        defaults to the NORMAL-mode maximum of 1000 mA.  Set it lower to
        match your LED's rating and prevent accidental over-driving.

        Returns ``True`` on success.  Raises on any failure.
        """
        self.set_normal_mode(channel, max_current_ma, current_ma)
        self.set_mode(channel, Mode.NORMAL)
        return True

    def disable_channel(self, channel: int) -> bool:
        """Disable *channel* (turn the LED off).

        Returns ``True`` on success.  Raises on any failure.
        """
        self.set_mode(channel, Mode.DISABLE)
        return True

    # -- Strobe mode --------------------------------------------------------

    def set_strobe_params(self, channel: int, max_current_ma: int, repeat: int) -> bool:
        """Configure strobe mode for *channel*.

        Returns ``True`` on success.  Raises on any failure.
        """
        self._p.set_strobe_params(channel, max_current_ma, repeat)
        return True

    def set_strobe_step(
        self,
        channel: int,
        step: int,
        current_ma: int,
        duration_us: int,
    ) -> bool:
        """Set a single strobe profile step.

        Use ``current_ma=0, duration_us=0`` as the end-of-profile marker.
        Returns ``True`` on success.  Raises on any failure.
        """
        self._p.set_strobe_step(channel, step, current_ma, duration_us)
        return True

    # -- Trigger mode -------------------------------------------------------

    def set_trigger_params(
        self,
        channel: int,
        max_current_ma: int,
        polarity: TriggerPolarity = TriggerPolarity.RISING,
    ) -> bool:
        """Configure trigger mode for *channel*.

        Returns ``True`` on success.  Raises on any failure.
        """
        self._p.set_trigger_params(channel, max_current_ma, polarity)
        return True

    def set_trigger_step(
        self,
        channel: int,
        step: int,
        current_ma: int,
        duration_us: int,
    ) -> bool:
        """Set a single trigger profile step.

        Returns ``True`` on success.  Raises on any failure.
        """
        self._p.set_trigger_step(channel, step, current_ma, duration_us)
        return True

    def set_trigger_follower(
        self,
        channel: int,
        current_ma: int,
        max_current_ma: int | None = None,
        polarity: TriggerPolarity = TriggerPolarity.RISING,
    ) -> bool:
        """Configure *channel* for trigger follower mode.

        In follower mode the LED is ON at *current_ma* while the trigger
        input is HIGH, and OFF when the trigger input goes LOW.  This is
        the recommended mode for frame-synchronized imaging systems where
        an external controller (e.g. Arduino) drives the trigger pulse.

        Executes the full safe programming sequence::

            MODE ch 0                      # disable first
            TRIGGER ch max_current polarity
            TRIGP ch 0 current_ma 9999     # follower step
            TRIGP ch 1 0 0                 # terminator
            MODE ch 3                      # arm trigger mode

        Args:
            channel: SLC channel (1-4).
            current_ma: LED drive current in mA.
            max_current_ma: Per-channel current ceiling (Imax).  Defaults
                to *current_ma* if not specified.
            polarity: Trigger edge polarity (default: rising edge).

        Returns ``True`` on success.  Raises on any failure.
        """
        if max_current_ma is None:
            max_current_ma = current_ma

        self.set_mode(channel, Mode.DISABLE)
        self.set_trigger_params(channel, max_current_ma, polarity)
        self.set_trigger_step(
            channel, step=0, current_ma=current_ma, duration_us=FOLLOWER_DURATION_US
        )
        self.set_trigger_step(channel, step=1, current_ma=0, duration_us=0)
        self.set_mode(channel, Mode.TRIGGER)
        return True

    # -- System -------------------------------------------------------------

    def store_settings(self) -> bool:
        """Save current settings to non-volatile memory.

        Returns ``True`` on success.  Raises on any failure.
        """
        self._p.store_settings()
        return True

    def reset(self) -> bool:
        """Perform a soft reset.

        Returns ``True`` on success.  Raises on any failure.
        """
        self._p.reset()
        return True

    def restore_defaults(self) -> bool:
        """Restore factory defaults.

        Returns ``True`` on success.  Raises on any failure.
        """
        self._p.restore_defaults()
        return True


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def get_controller(port: str = DEFAULT_PORT) -> MightexSLC:
    """Return a controller instance (use as a context manager).

    Example::

        with get_controller('/dev/ttyUSB0') as led:
            led.enable_channel(1, current_ma=50)
    """
    return MightexSLC(port)
