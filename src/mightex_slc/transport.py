"""
Serial transport layer for the Mightex SLC LED controller.

Handles the physical serial connection, byte framing, read-loop with
terminator detection, and buffer hygiene.  Knows nothing about what
commands mean — that's :mod:`protocol`'s job.

Typical usage (via :class:`~mightex_slc.controller.MightexSLC`)::

    transport = SerialTransport("/dev/ttyUSB0")
    transport.open()
    response = transport.send("DEVICEINFO")
    transport.close()
"""

from __future__ import annotations

import logging
import time

import serial

from .exceptions import ConnectionError, TimeoutError

logger = logging.getLogger(__name__)

# Protocol framing constants
_CMD_TERMINATOR = b"\n\r"  # LF + CR — what we append to outgoing commands
_RESP_TERMINATOR = b"\r"  # CR — what the device ends responses with


class SerialTransport:
    """Manages a serial connection to a Mightex SLC controller.

    Args:
        port: Serial port path (e.g. ``/dev/ttyUSB0``).
        baudrate: Baud rate (default 9600).
        timeout: Per-read timeout in seconds.  Also serves as the upper
            bound on how long :meth:`send` will wait for a response.
    """

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        timeout: float = 1.0,
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
        logger.info("Opening serial port %s at %d baud", self.port, self.baudrate)
        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
            )
        except serial.SerialException as exc:
            raise ConnectionError(f"Cannot open {self.port}: {exc}") from exc

    def close(self) -> None:
        """Close the serial port (safe to call multiple times)."""
        if self._ser and self._ser.is_open:
            self._ser.close()
            logger.info("Serial port %s closed", self.port)

    @property
    def is_open(self) -> bool:
        """Return ``True`` if the serial port is currently open."""
        return self._ser is not None and self._ser.is_open

    # -- I/O ----------------------------------------------------------------

    def send(self, cmd: str) -> str:
        """Send *cmd* and return the controller's decoded response.

        Steps:
            1. Flush any stale bytes from the input buffer.
            2. Write the command with ``LF CR`` termination.
            3. Flush the output buffer to ensure bytes leave the process.
            4. Read until a response terminator (``CR``) is received or the
               serial timeout expires.
            5. Decode and strip the response.

        Args:
            cmd: Command string without termination characters.

        Returns:
            Decoded response with whitespace stripped.

        Raises:
            ConnectionError: If the port is not open.
            TimeoutError: If no response is received.
        """
        ser = self._require_open()
        logger.debug("TX: %s", cmd)

        # 1. Discard stale bytes from previous commands
        ser.reset_input_buffer()

        # 2. Write command
        ser.write(f"{cmd}".encode("ascii") + _CMD_TERMINATOR)

        # 3. Ensure bytes leave the OS buffer
        ser.flush()

        # 4. Read until terminator or timeout
        raw = self._read_response(ser)

        # 5. Decode
        response = raw.decode("ascii", errors="replace").strip()
        logger.debug("RX: %s", response)

        if not response:
            raise TimeoutError(f"No response from controller for '{cmd}'")

        return response

    # -- Internal -----------------------------------------------------------

    def _require_open(self) -> serial.Serial:
        """Return the open serial port or raise."""
        if not self.is_open:
            raise ConnectionError("Serial port not open — call open() first.")
        assert self._ser is not None  # for type-checker
        return self._ser

    def _read_response(self, ser: serial.Serial) -> bytes:
        """Read bytes until the response terminator or timeout.

        Uses ``read_until`` with a deadline so we never hang indefinitely,
        even if the device sends data without a clean terminator.

        Falls back to a small inter-byte-timeout drain to catch any trailing
        bytes that arrive after the terminator (e.g. multi-line responses).
        """
        # read_until blocks until it sees the terminator or the serial
        # timeout expires — exactly the behaviour we want.
        data = ser.read_until(_RESP_TERMINATOR)

        # Drain any trailing bytes (e.g. a LF after the CR) with a very
        # short pause so we don't leave garbage for the next command.
        time.sleep(0.02)
        extra = ser.in_waiting
        if extra:
            data += ser.read(extra)

        return data
