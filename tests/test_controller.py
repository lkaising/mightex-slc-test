"""
Test suite for the Mightex SLC LED controller.

Unit tests use a mock serial port and run everywhere.
Integration tests (marked ``@pytest.mark.hardware``) require a real device on
``/dev/ttyUSB0`` and are skipped by default.  Run them explicitly with::

    pytest -m hardware
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from mightex_slc import (
    CommandError,
    ConnectionError,
    DeviceInfo,
    MightexSLC,
    Mode,
    TriggerPolarity,
    ValidationError,
)

# ── Helpers ────────────────────────────────────────────────────────────────

HARDWARE_PORT = "/dev/ttyUSB0"
SAFE_CURRENT = 10  # mA — low enough to be safe for any LED


# ══════════════════════════════════════════════════════════════════════════
#  Unit tests (no hardware required)
# ══════════════════════════════════════════════════════════════════════════


class TestDeviceInfoParsing:
    """DeviceInfo.from_response is pure parsing — no serial needed."""

    def test_standard_response(self):
        raw = (
            "Mightex LED Driver:3.1.8 Device Module No.:SLC-SA04-U/S "
            "Device Serial No.:04-251013-011"
        )
        info = DeviceInfo.from_response(raw)
        assert info.firmware_version == "3.1.8"
        assert info.module_number == "SLC-SA04-U/S"
        assert info.serial_number == "04-251013-011"

    def test_missing_fields_gracefully_default(self):
        info = DeviceInfo.from_response("unexpected garbage")
        assert info.firmware_version == "Unknown"
        assert info.module_number == "Unknown"
        assert info.serial_number == "Unknown"

    def test_partial_response(self):
        info = DeviceInfo.from_response("Mightex LED Driver:2.0.0")
        assert info.firmware_version == "2.0.0"
        assert info.module_number == "Unknown"


class TestModeEnum:
    """Sanity checks for the Mode IntEnum."""

    def test_values(self):
        assert Mode.DISABLE == 0
        assert Mode.NORMAL == 1
        assert Mode.STROBE == 2
        assert Mode.TRIGGER == 3

    def test_mode_from_int(self):
        assert Mode(1) is Mode.NORMAL

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            Mode(99)


class TestTriggerPolarityEnum:
    def test_values(self):
        assert TriggerPolarity.RISING == 0
        assert TriggerPolarity.FALLING == 1


# ── Validation ────────────────────────────────────────────────────────────


class TestInputValidation:
    """Validation fires before anything touches the serial port."""

    @pytest.mark.parametrize("channel", [-1, 0, 5, 100])
    def test_invalid_channel_rejected(self, controller, channel):
        with pytest.raises(ValidationError):
            controller.set_mode(channel, Mode.DISABLE)

    @pytest.mark.parametrize("current", [-1, 2001, 99999])
    def test_invalid_current_rejected(self, controller, current):
        with pytest.raises(ValidationError):
            controller.set_current(1, current)

    def test_set_current_exceeding_max_rejected(self, controller):
        with pytest.raises(ValidationError, match="cannot exceed"):
            controller.set_normal_mode(channel=1, max_current_ma=50, set_current_ma=100)

    def test_invalid_mode_rejected(self, controller):
        with pytest.raises(ValidationError):
            controller.set_mode(1, 99)


# ── Connection ────────────────────────────────────────────────────────────


class TestConnection:
    def test_connect_sets_is_connected(self, controller):
        assert controller.is_connected

    def test_disconnect_clears_flag(self, controller):
        controller.disconnect()
        assert not controller.is_connected

    def test_command_when_disconnected_raises(self, controller):
        controller.disconnect()
        with pytest.raises(ConnectionError):
            controller.get_device_info()

    def test_context_manager_closes(self, fake_serial):
        with patch("mightex_slc.controller.serial.Serial", return_value=fake_serial):
            with MightexSLC("/dev/fake") as led:
                assert led.is_connected
            assert not fake_serial.is_open

    def test_serial_open_failure_raises_connection_error(self):
        import serial as _serial

        with patch(
            "mightex_slc.controller.serial.Serial",
            side_effect=_serial.SerialException("port busy"),
        ):
            with pytest.raises(ConnectionError, match="Cannot open"):
                MightexSLC("/dev/nonexistent").connect()


# ── Command I/O ───────────────────────────────────────────────────────────


class TestSendCommand:
    def test_command_is_written_with_termination(self, controller, fake_serial):
        fake_serial.set_response("##\n\r")
        controller._send_command("STORE")
        assert fake_serial.written[-1] == b"STORE\n\r"

    def test_error_response_raises(self, controller, fake_serial):
        fake_serial.set_response("#!\n\r")
        with pytest.raises(CommandError, match="Controller error"):
            controller._send_command("BAD")

    def test_bad_arg_response_raises(self, controller, fake_serial):
        fake_serial.set_response("#?\n\r")
        with pytest.raises(CommandError, match="Invalid argument"):
            controller._send_command("MODE 1 99")

    def test_undefined_command_raises(self, controller, fake_serial):
        fake_serial.set_response("FOOBAR is not defined\n\r")
        with pytest.raises(CommandError, match="Unknown command"):
            controller._send_command("FOOBAR")


# ── Device info ───────────────────────────────────────────────────────────


class TestGetDeviceInfo:
    def test_returns_device_info(self, controller, fake_serial):
        fake_serial.set_response(
            "Mightex LED Driver:3.1.8 Device Module No.:SLC-SA04-U/S "
            "Device Serial No.:04-251013-011\n\r"
        )
        info = controller.get_device_info()
        assert info.module_number == "SLC-SA04-U/S"
        assert info.firmware_version == "3.1.8"
        assert info.serial_number == "04-251013-011"


# ── Mode control ──────────────────────────────────────────────────────────


class TestModeControl:
    @pytest.mark.parametrize("mode", list(Mode))
    def test_set_mode_succeeds(self, controller, fake_serial, mode):
        fake_serial.set_response("##\n\r")
        assert controller.set_mode(1, mode) is True

    def test_get_mode_parses_response(self, controller, fake_serial):
        fake_serial.set_response("#1\n\r")
        assert controller.get_mode(1) == Mode.NORMAL

    def test_get_mode_bad_response_raises(self, controller, fake_serial):
        fake_serial.set_response("#garbage\n\r")
        with pytest.raises(CommandError, match="Unexpected mode"):
            controller.get_mode(1)


# ── Normal mode parameters ────────────────────────────────────────────────


class TestNormalMode:
    def test_set_normal_mode_sends_correct_command(self, controller, fake_serial):
        fake_serial.set_response("##\n\r")
        controller.set_normal_mode(1, 200, 100)
        assert b"NORMAL 1 200 100\n\r" in fake_serial.written

    def test_get_normal_params(self, controller, fake_serial):
        # Response has calibration values, then Imax and Iset at the end
        fake_serial.set_response("#50 60 200 100\n\r")
        max_ma, set_ma = controller.get_normal_params(1)
        assert max_ma == 200
        assert set_ma == 100

    def test_get_normal_params_bad_response_raises(self, controller, fake_serial):
        fake_serial.set_response("#\n\r")
        with pytest.raises(CommandError, match="Cannot parse"):
            controller.get_normal_params(1)

    def test_set_current(self, controller, fake_serial):
        fake_serial.set_response("##\n\r")
        assert controller.set_current(1, 75) is True
        assert b"CURRENT 1 75\n\r" in fake_serial.written


# ── Convenience methods ───────────────────────────────────────────────────


class TestConvenience:
    def test_enable_channel_default_max(self, controller, fake_serial):
        fake_serial.set_response("##\n\r")
        assert controller.enable_channel(1, current_ma=50) is True
        # Should have sent NORMAL with max = 2 * 50 = 100
        assert any(b"NORMAL 1 100 50" in w for w in fake_serial.written)

    def test_enable_channel_explicit_max(self, controller, fake_serial):
        fake_serial.set_response("##\n\r")
        assert controller.enable_channel(1, current_ma=50, max_current_ma=200) is True
        assert any(b"NORMAL 1 200 50" in w for w in fake_serial.written)

    def test_disable_channel(self, controller, fake_serial):
        fake_serial.set_response("##\n\r")
        assert controller.disable_channel(1) is True
        assert any(b"MODE 1 0" in w for w in fake_serial.written)


# ── Strobe & trigger ──────────────────────────────────────────────────────


class TestStrobeMode:
    def test_set_strobe_params(self, controller, fake_serial):
        fake_serial.set_response("##\n\r")
        assert controller.set_strobe_params(1, max_current_ma=100, repeat=5) is True
        assert b"STROBE 1 100 5\n\r" in fake_serial.written

    def test_set_strobe_step(self, controller, fake_serial):
        fake_serial.set_response("##\n\r")
        assert controller.set_strobe_step(1, step=0, current_ma=50, duration_us=2000) is True
        assert b"STRP 1 0 50 2000\n\r" in fake_serial.written


class TestTriggerMode:
    def test_set_trigger_params(self, controller, fake_serial):
        fake_serial.set_response("##\n\r")
        assert (
            controller.set_trigger_params(1, max_current_ma=100, polarity=TriggerPolarity.FALLING)
            is True
        )
        assert b"TRIGGER 1 100 1\n\r" in fake_serial.written

    def test_set_trigger_step(self, controller, fake_serial):
        fake_serial.set_response("##\n\r")
        assert controller.set_trigger_step(1, step=0, current_ma=50, duration_us=2000) is True
        assert b"TRIGP 1 0 50 2000\n\r" in fake_serial.written


# ── System commands ───────────────────────────────────────────────────────


class TestSystemCommands:
    def test_store_settings(self, controller, fake_serial):
        fake_serial.set_response("##\n\r")
        assert controller.store_settings() is True

    def test_reset(self, controller, fake_serial):
        fake_serial.set_response("##\n\r")
        assert controller.reset() is True

    def test_restore_defaults(self, controller, fake_serial):
        fake_serial.set_response("##\n\r")
        assert controller.restore_defaults() is True

    def test_get_load_voltage(self, controller, fake_serial):
        fake_serial.set_response("#1:3200\n\r")
        assert controller.get_load_voltage(1) == 3200

    def test_get_load_voltage_bad_response(self, controller, fake_serial):
        fake_serial.set_response("#garbage\n\r")
        with pytest.raises(CommandError, match="Cannot parse"):
            controller.get_load_voltage(1)


# ── Backward compatibility ────────────────────────────────────────────────


class TestBackwardCompat:
    """The old class-level MODE_* constants should still work."""

    def test_class_mode_constants(self):
        assert MightexSLC.MODE_DISABLE == 0
        assert MightexSLC.MODE_NORMAL == 1
        assert MightexSLC.MODE_STROBE == 2
        assert MightexSLC.MODE_TRIGGER == 3


# ══════════════════════════════════════════════════════════════════════════
#  Hardware integration tests — require a real device
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.hardware
class TestHardwareIntegration:
    """Run only with ``pytest -m hardware``.

    These tests talk to a real SLC controller on ``/dev/ttyUSB0``.
    """

    @pytest.fixture(autouse=True)
    def _open_device(self):
        self.led = MightexSLC(HARDWARE_PORT)
        self.led.connect()
        yield
        # Safety: disable all channels on teardown
        for ch in range(1, 5):
            try:
                self.led.disable_channel(ch)
            except Exception:
                pass
        self.led.disconnect()

    def test_device_info(self):
        info = self.led.get_device_info()
        assert "SLC" in info.module_number
        assert len(info.serial_number) > 0

    def test_mode_roundtrip(self):
        self.led.set_mode(1, Mode.DISABLE)
        assert self.led.get_mode(1) == Mode.DISABLE

        self.led.set_mode(1, Mode.NORMAL)
        assert self.led.get_mode(1) == Mode.NORMAL

        self.led.set_mode(1, Mode.DISABLE)

    def test_normal_params_roundtrip(self):
        self.led.set_normal_mode(1, 100, SAFE_CURRENT)
        time.sleep(0.3)
        max_ma, set_ma = self.led.get_normal_params(1)
        assert max_ma == 100
        assert set_ma == SAFE_CURRENT

    def test_enable_disable(self):
        assert self.led.enable_channel(1, SAFE_CURRENT)
        assert self.led.get_mode(1) == Mode.NORMAL
        assert self.led.disable_channel(1)
        assert self.led.get_mode(1) == Mode.DISABLE

    def test_all_channels_respond(self):
        for ch in range(1, 5):
            assert self.led.disable_channel(ch)
            assert self.led.get_mode(ch) == Mode.DISABLE
