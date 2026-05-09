"""
Layer 2 — Protocol command formatting.

Cover the bytes :class:`~mightex_slc.protocol.SLCProtocol` puts on the wire:
``MODE``, ``NORMAL``, ``CURRENT``, ``STROBE``, ``STRP``, ``TRIGGER``, ``TRIGP``,
plus stateless system commands (``STORE``, ``RESET``, ``RESTOREDEF``).
"""

from __future__ import annotations

from mightex_slc import Mode, TriggerPolarity


class TestProtocolCommands:
    """Verify commands are formatted correctly on the wire."""

    def test_set_normal_params_format(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.set_normal_params(1, 200, 100)
        assert b"NORMAL 1 200 100\n\r" in fake_serial.written

    def test_set_current_format(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.set_current(1, 75)
        assert b"CURRENT 1 75\n\r" in fake_serial.written

    def test_set_mode_format(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.set_mode(1, Mode.NORMAL)
        assert b"MODE 1 1\n\r" in fake_serial.written

    def test_strobe_params_format(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.set_strobe_params(1, max_current_ma=100, repeat=5)
        assert b"STROBE 1 100 5\n\r" in fake_serial.written

    def test_strobe_step_format(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.set_strobe_step(1, step=0, current_ma=50, duration_us=2000)
        assert b"STRP 1 0 50 2000\n\r" in fake_serial.written

    def test_trigger_params_format(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.set_trigger_params(1, max_current_ma=100, polarity=TriggerPolarity.FALLING)
        assert b"TRIGGER 1 100 1\n\r" in fake_serial.written

    def test_trigger_step_format(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.set_trigger_step(1, step=0, current_ma=50, duration_us=2000)
        assert b"TRIGP 1 0 50 2000\n\r" in fake_serial.written


class TestProtocolSystemCommands:
    def test_store_settings(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.store_settings()  # should not raise

    def test_reset(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.reset()

    def test_restore_defaults(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.restore_defaults()
