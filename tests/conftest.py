"""Shared pytest fixtures for Mightex SLC tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mightex_slc import MightexSLC


class FakeSerial:
    """Lightweight stand-in for ``serial.Serial``.

    By default every read returns ``##\\n\\r`` (success).  Call
    ``set_response`` to override the *next* read; after that read the
    default is restored automatically so multi-command methods work.
    """

    _DEFAULT = b"##\n\r"

    def __init__(self) -> None:
        self.is_open: bool = True
        self.written: list[bytes] = []
        self._response: bytes = self._DEFAULT
        self._sticky: bool = True  # True → keep returning _DEFAULT

    # -- helpers for tests --------------------------------------------------

    def set_response(self, text: str) -> None:
        """Set the response for the **next** read, then revert to ``##``."""
        self._response = text.encode("ascii")
        self._sticky = False

    # -- serial.Serial interface --------------------------------------------

    def write(self, data: bytes) -> int:
        self.written.append(data)
        return len(data)

    @property
    def in_waiting(self) -> int:
        return len(self._response)

    def read(self, size: int = 1) -> bytes:
        data = self._response[:size]
        self._response = self._response[size:]
        # After the buffer is fully consumed, reset to default
        if not self._response and not self._sticky:
            self._response = self._DEFAULT
            self._sticky = True
        return data

    def close(self) -> None:
        self.is_open = False


@pytest.fixture()
def fake_serial() -> FakeSerial:
    """Return a fresh ``FakeSerial`` instance."""
    return FakeSerial()


@pytest.fixture()
def controller(fake_serial: FakeSerial) -> MightexSLC:
    """Return a ``MightexSLC`` wired to a fake serial port (already connected)."""
    with patch("mightex_slc.controller.serial.Serial", return_value=fake_serial):
        led = MightexSLC("/dev/fake")
        led.connect()
        # Reset written buffer so tests don't see the ECHOOFF command
        fake_serial.written.clear()
        fake_serial.set_response("##\n\r")
        return led
