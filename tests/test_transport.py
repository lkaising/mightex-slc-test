"""
Layer 1 — Transport tests.

Cover serial I/O, framing, timeouts, and connection state on
:class:`~mightex_slc.transport.SerialTransport`.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mightex_slc import MightexConnectionError, MightexTimeoutError


class TestTransportConnection:
    """Opening, closing, and connection state."""

    def test_open_sets_is_open(self, transport):
        assert transport.is_open

    def test_close_clears_flag(self, transport):
        transport.close()
        assert not transport.is_open

    def test_send_when_closed_raises(self, transport):
        transport.close()
        with pytest.raises(MightexConnectionError, match="not open"):
            transport.send("DEVICEINFO")

    def test_open_failure_raises_connection_error(self):
        import serial as _serial

        with (
            patch(
                "mightex_slc.transport.serial.Serial",
                side_effect=_serial.SerialException("port busy"),
            ),
            pytest.raises(MightexConnectionError, match="Cannot open"),
        ):
            from mightex_slc.transport import SerialTransport

            SerialTransport("/dev/nonexistent").open()


class TestTransportSend:
    """Command framing, termination, and response reading."""

    def test_command_bytes_include_terminator(self, transport, fake_serial):
        fake_serial.set_response("##\n\r")
        transport.send("STORE")
        assert fake_serial.written[-1] == b"STORE\n\r"

    def test_returns_stripped_response(self, transport, fake_serial):
        fake_serial.set_response("##\n\r")
        assert transport.send("STORE") == "##"

    def test_empty_response_raises_timeout(self, transport, fake_serial):
        fake_serial.set_response("")
        with pytest.raises(MightexTimeoutError, match="No response"):
            transport.send("STORE")

    def test_multiline_response_fully_read(self, transport, fake_serial):
        # Simulate a response with extra trailing data
        fake_serial.set_response(
            "Mightex LED Driver:3.1.8 Device Module No.:SLC-SA04-U/S "
            "Device Serial No.:04-251013-011\r\n"
        )
        resp = transport.send("DEVICEINFO")
        assert "SLC-SA04-U/S" in resp
