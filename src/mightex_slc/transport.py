"""
Serial transport layer for the Mightex SLC LED controller.

This module owns the physical serial connection and byte-level I/O:
- opens/closes the serial port
- frames outbound commands
- reads responses with terminator detection
- performs basic buffer hygiene

It deliberately does not interpret command meaning; that belongs in the protocol/controller layers.
"""

from __future__ import annotations

import logging
import time

import serial

from .constants import DEFAULT_BAUD, DEFAULT_PORT, DEFAULT_TIMEOUT
from .exceptions import ConnectionError, TimeoutError

logger = logging.getLogger(__name__)

# Protocol framing
_CMD_TERMINATOR = b"\n\r"  # what we append to outgoing commands (LF + CR)
_RESP_TERMINATOR = b"\r"  # what the device ends responses with (CR)

# Implementation details
_ENCODING = "ascii"
_DRAIN_DELAY_S = 0.02


class SerialTransport:
    """Manages a serial connection to a Mightex SLC controller.

    Args:
        port: Serial port path (e.g. ``/dev/ttyUSB0``).
        baudrate: Baud rate (default 9600).
        timeout: Per-read timeout in seconds. Also acts as the upper bound
                 for waiting on a response in :meth:`send`.
    """

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baudrate: int = DEFAULT_BAUD,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser: serial.Serial | None = None

    # -- Lifecycle ----------------------------------------------------------

    def open(self) -> None:
        """Open the serial port.

        Raises:
            ConnectionError: If the port cannot be opened.
        """
        if self.is_open:
            return

        logger.info("Opening serial port %s at %d baud", self.port, self.baudrate)
        try:
            ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
            )
        except serial.SerialException as exc:
            raise ConnectionError(f"Cannot open {self.port}: {exc}") from exc

        self._ser = ser

    def close(self) -> None:
        """Close the serial port (safe to call multiple times)."""
        ser, self._ser = self._ser, None
        if ser is None:
            return
        if ser.is_open:
            ser.close()
            logger.info("Serial port %s closed", self.port)

    @property
    def is_open(self) -> bool:
        """True if the serial port is currently open."""
        return self._ser is not None and self._ser.is_open

    def __enter__(self) -> SerialTransport:
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- I/O ----------------------------------------------------------------

    def send(self, cmd: str) -> str:
        """Send *cmd* and return the decoded response.

        Args:
            cmd: Command string without termination characters.

        Returns:
            Decoded response with surrounding whitespace stripped.

        Raises:
            ConnectionError: If the port is not open.
            TimeoutError: If no response is received.
        """
        ser = self._require_open()
        logger.debug("TX: %s", cmd)

        ser.reset_input_buffer()
        ser.write(cmd.encode(_ENCODING) + _CMD_TERMINATOR)
        ser.flush()

        raw = self._read_response(ser)
        response = raw.decode(_ENCODING, errors="replace").strip()
        logger.debug("RX: %s", response)

        if not response:
            raise TimeoutError(f"No response from controller for '{cmd}'")

        return response

    # -- Internals ----------------------------------------------------------

    def _require_open(self) -> serial.Serial:
        """Return the open serial port or raise."""
        if not self.is_open:
            raise ConnectionError("Serial port not open — call open() first.")
        assert self._ser is not None  # for type-checkers
        return self._ser

    def _read_response(self, ser: serial.Serial) -> bytes:
        """Read bytes until the response terminator or the serial timeout.

        Uses ``read_until`` (bounded by the serial driver's timeout), then
        performs a small best-effort drain to capture any bytes that arrive
        immediately after the terminator.
        """
        data = ser.read_until(_RESP_TERMINATOR)

        time.sleep(_DRAIN_DELAY_S)
        extra = ser.in_waiting
        if extra:
            data += ser.read(extra)

        return data
