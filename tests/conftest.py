"""Shared pytest fixtures for Mightex SLC tests."""

from __future__ import annotations

from collections import deque
from unittest.mock import patch

import pytest

from mightex_slc import MightexSLC
from mightex_slc.protocol import SLCProtocol
from mightex_slc.transport import SerialTransport


class FakeSerial:
    """Lightweight stand-in for ``serial.Serial``.

    Implements the subset of the pyserial API used by
    :class:`~mightex_slc.transport.SerialTransport`:
    ``write``, ``read``, ``read_until``, ``in_waiting``, ``flush``,
    ``reset_input_buffer``, ``close``, and ``is_open``.

    By default every command gets a ``##\\n\\r`` (success ack) response.
    Tests can override that default with either:

    * :meth:`set_response` — stage a single response for the next command.
    * :meth:`queue_responses` — stage a sequence of responses, one per
      upcoming command. Useful for code paths that issue several queries
      in a row (e.g. ``verify_channel`` reads ``?MODE``, ``?TRIGGER``,
      ``?TRIGP``).

    Once the queue drains, subsequent commands receive the default ack
    again, so multi-command methods like ``enable_channel`` keep working
    without extra setup.

    The response buffer refreshes on each :meth:`write` call (i.e. when a
    new command is sent), which matches the transport's pattern of
    ``reset_input_buffer → write → flush → read_until → drain``.
    """

    _DEFAULT = b"##\n\r"

    def __init__(self) -> None:
        self.is_open: bool = True
        self.written: list[bytes] = []
        self._response: bytes = self._DEFAULT
        self._queue: deque[bytes] = deque()

    # -- Helpers for tests --------------------------------------------------

    def set_response(self, text: str) -> None:
        """Stage a single response for the next command (write cycle).

        Replaces any previously queued responses.
        """
        self._queue.clear()
        self._queue.append(text.encode("ascii"))

    def queue_responses(self, responses: list[str]) -> None:
        """Stage a sequence of responses, one per upcoming write() call.

        After the queue drains, subsequent writes get the default
        ``##\\n\\r`` ack. Replaces any previously queued responses.
        """
        self._queue.clear()
        self._queue.extend(text.encode("ascii") for text in responses)

    # -- pyserial interface -------------------------------------------------

    def write(self, data: bytes) -> int:
        self.written.append(data)
        # Load the next staged response (or default) for the upcoming reads
        if self._queue:
            self._response = self._queue.popleft()
        else:
            self._response = self._DEFAULT
        return len(data)

    @property
    def in_waiting(self) -> int:
        return len(self._response)

    def read(self, size: int = 1) -> bytes:
        data = self._response[:size]
        self._response = self._response[size:]
        return data

    def read_until(self, terminator: bytes = b"\n", size: int | None = None) -> bytes:
        """Return everything up to and including *terminator*."""
        idx = self._response.find(terminator)
        if idx == -1:
            # Terminator not found — return everything (mimics timeout)
            data = self._response
            self._response = b""
        else:
            end = idx + len(terminator)
            data = self._response[:end]
            self._response = self._response[end:]
        return data

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        pass  # no-op — we don't want to discard the staged response

    def close(self) -> None:
        self.is_open = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_serial() -> FakeSerial:
    """Return a fresh ``FakeSerial`` instance."""
    return FakeSerial()


@pytest.fixture()
def transport(fake_serial: FakeSerial) -> SerialTransport:
    """Return a ``SerialTransport`` wired to a fake serial port."""
    with patch("mightex_slc.transport.serial.Serial", return_value=fake_serial):
        tx = SerialTransport("/dev/fake")
        tx.open()
        fake_serial.written.clear()
        fake_serial.set_response("##\n\r")
        return tx


@pytest.fixture()
def protocol(transport: SerialTransport) -> SLCProtocol:
    """Return an ``SLCProtocol`` wired to a fake transport."""
    return SLCProtocol(transport)


@pytest.fixture()
def controller(fake_serial: FakeSerial) -> MightexSLC:
    """Return a fully connected ``MightexSLC`` wired to a fake serial port."""
    with patch("mightex_slc.transport.serial.Serial", return_value=fake_serial):
        led = MightexSLC("/dev/fake")
        led.connect()
        # Reset so tests don't see ECHOOFF
        fake_serial.written.clear()
        fake_serial.set_response("##\n\r")
        return led
