"""
Test suite for the Mightex SLC LED controller.

Organised by layer:

* **Transport** — serial I/O, timeouts, buffer hygiene
* **Protocol** — parsing, validation, ack checking, command formatting
* **Controller** — user-facing API, convenience methods, backward compat
* **Hardware** — integration tests against a real device (skipped by default)

Run unit tests::

    pytest

Run hardware integration tests::

    pytest -m hardware
"""

from __future__ import annotations

import time
from contextlib import suppress
from unittest.mock import patch

import pytest

from mightex_slc import (
    MAX_CURRENT_NORMAL_MA,
    MAX_CURRENT_PULSED_MA,
    CommandError,
    ConnectionError,
    DeviceInfo,
    MightexSLC,
    Mode,
    TimeoutError,
    TriggerPolarity,
    ValidationError,
)

# ── Constants ─────────────────────────────────────────────────────────────

HARDWARE_PORT = "/dev/ttyUSB0"
SAFE_CURRENT = 10  # mA — low enough to be safe for any LED


# ══════════════════════════════════════════════════════════════════════════
#  Layer 1: Transport
# ══════════════════════════════════════════════════════════════════════════


class TestTransportConnection:
    """Opening, closing, and connection state."""

    def test_open_sets_is_open(self, transport):
        assert transport.is_open

    def test_close_clears_flag(self, transport):
        transport.close()
        assert not transport.is_open

    def test_send_when_closed_raises(self, transport):
        transport.close()
        with pytest.raises(ConnectionError, match="not open"):
            transport.send("DEVICEINFO")

    def test_open_failure_raises_connection_error(self):
        import serial as _serial

        with (
            patch(
                "mightex_slc.transport.serial.Serial",
                side_effect=_serial.SerialException("port busy"),
            ),
            pytest.raises(ConnectionError, match="Cannot open"),
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
        with pytest.raises(TimeoutError, match="No response"):
            transport.send("STORE")

    def test_multiline_response_fully_read(self, transport, fake_serial):
        # Simulate a response with extra trailing data
        fake_serial.set_response(
            "Mightex LED Driver:3.1.8 Device Module No.:SLC-SA04-U/S "
            "Device Serial No.:04-251013-011\r\n"
        )
        resp = transport.send("DEVICEINFO")
        assert "SLC-SA04-U/S" in resp


# ══════════════════════════════════════════════════════════════════════════
#  Layer 2: Protocol — Parsing
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


# ══════════════════════════════════════════════════════════════════════════
#  Layer 2: Protocol — Validation
# ══════════════════════════════════════════════════════════════════════════


class TestChannelValidation:
    @pytest.mark.parametrize("channel", [-1, 0, 5, 100])
    def test_invalid_channel_rejected(self, protocol, fake_serial, channel):
        with pytest.raises(ValidationError):
            protocol.set_mode(channel, Mode.DISABLE)


class TestNormalCurrentValidation:
    """NORMAL-mode commands enforce the 1000 mA ceiling."""

    def test_set_current_at_normal_max_accepted(self, protocol, fake_serial):
        """Boundary: exactly MAX_CURRENT_NORMAL_MA should succeed."""
        fake_serial.set_response("##\n\r")
        protocol.set_current(1, MAX_CURRENT_NORMAL_MA)

    def test_set_current_above_normal_max_rejected(self, protocol, fake_serial):
        """Boundary: one above MAX_CURRENT_NORMAL_MA must fail."""
        with pytest.raises(ValidationError, match="0-1000"):
            protocol.set_current(1, MAX_CURRENT_NORMAL_MA + 1)

    def test_set_normal_params_at_max_accepted(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.set_normal_params(1, MAX_CURRENT_NORMAL_MA, MAX_CURRENT_NORMAL_MA)

    def test_set_normal_params_above_max_rejected(self, protocol, fake_serial):
        with pytest.raises(ValidationError, match="0-1000"):
            protocol.set_normal_params(1, MAX_CURRENT_NORMAL_MA + 1, 100)

    def test_set_normal_params_set_above_max_rejected(self, protocol, fake_serial):
        with pytest.raises(ValidationError, match="0-1000"):
            protocol.set_normal_params(1, 500, MAX_CURRENT_NORMAL_MA + 1)

    def test_negative_current_rejected(self, protocol, fake_serial):
        with pytest.raises(ValidationError):
            protocol.set_current(1, -1)

    def test_set_current_exceeding_max_rejected(self, protocol):
        with pytest.raises(ValidationError, match="cannot exceed"):
            protocol.set_normal_params(channel=1, max_current_ma=50, set_current_ma=100)


class TestPulsedCurrentValidation:
    """STROBE/TRIGGER commands enforce the 3500 mA ceiling."""

    def test_strobe_params_at_pulsed_max_accepted(self, protocol, fake_serial):
        """Boundary: exactly MAX_CURRENT_PULSED_MA should succeed."""
        fake_serial.set_response("##\n\r")
        protocol.set_strobe_params(1, MAX_CURRENT_PULSED_MA, repeat=1)

    def test_strobe_params_above_pulsed_max_rejected(self, protocol, fake_serial):
        """Boundary: one above MAX_CURRENT_PULSED_MA must fail."""
        with pytest.raises(ValidationError, match="0-3500"):
            protocol.set_strobe_params(1, MAX_CURRENT_PULSED_MA + 1, repeat=1)

    def test_strobe_step_at_pulsed_max_accepted(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.set_strobe_step(1, step=0, current_ma=MAX_CURRENT_PULSED_MA, duration_us=1000)

    def test_strobe_step_above_pulsed_max_rejected(self, protocol, fake_serial):
        with pytest.raises(ValidationError, match="0-3500"):
            protocol.set_strobe_step(
                1, step=0, current_ma=MAX_CURRENT_PULSED_MA + 1, duration_us=1000
            )

    def test_trigger_params_at_pulsed_max_accepted(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.set_trigger_params(1, MAX_CURRENT_PULSED_MA)

    def test_trigger_params_above_pulsed_max_rejected(self, protocol, fake_serial):
        with pytest.raises(ValidationError, match="0-3500"):
            protocol.set_trigger_params(1, MAX_CURRENT_PULSED_MA + 1)

    def test_trigger_step_at_pulsed_max_accepted(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.set_trigger_step(1, step=0, current_ma=MAX_CURRENT_PULSED_MA, duration_us=1000)

    def test_trigger_step_above_pulsed_max_rejected(self, protocol, fake_serial):
        with pytest.raises(ValidationError, match="0-3500"):
            protocol.set_trigger_step(
                1, step=0, current_ma=MAX_CURRENT_PULSED_MA + 1, duration_us=1000
            )

    def test_strobe_accepts_above_normal_max(self, protocol, fake_serial):
        """Values between 1001-3500 must be valid for pulsed modes."""
        fake_serial.set_response("##\n\r")
        protocol.set_strobe_params(1, 2000, repeat=1)

    def test_trigger_accepts_above_normal_max(self, protocol, fake_serial):
        fake_serial.set_response("##\n\r")
        protocol.set_trigger_params(1, 2500)


class TestModeValidation:
    def test_invalid_mode_rejected(self, protocol):
        with pytest.raises(ValidationError):
            protocol.set_mode(1, 99)


class TestStepValidation:
    """Strobe/trigger step parameter validation."""

    def test_negative_step_rejected(self, protocol):
        with pytest.raises(ValidationError, match="Step"):
            protocol.set_strobe_step(1, step=-1, current_ma=50, duration_us=1000)

    def test_step_too_large_rejected(self, protocol):
        with pytest.raises(ValidationError, match="Step"):
            protocol.set_strobe_step(1, step=200, current_ma=50, duration_us=1000)

    def test_negative_duration_rejected(self, protocol):
        with pytest.raises(ValidationError, match="Duration"):
            protocol.set_strobe_step(1, step=0, current_ma=50, duration_us=-1)

    def test_current_in_step_validated(self, protocol):
        with pytest.raises(ValidationError, match="current"):
            protocol.set_strobe_step(1, step=0, current_ma=5000, duration_us=1000)

    def test_trigger_step_validates_same(self, protocol):
        with pytest.raises(ValidationError, match="Step"):
            protocol.set_trigger_step(1, step=-1, current_ma=50, duration_us=1000)

    def test_negative_repeat_rejected(self, protocol):
        with pytest.raises(ValidationError, match="Repeat"):
            protocol.set_strobe_params(1, max_current_ma=100, repeat=-1)


# ══════════════════════════════════════════════════════════════════════════
#  Layer 2: Protocol — Ack checking & error responses
# ══════════════════════════════════════════════════════════════════════════


class TestAckChecking:
    def test_controller_error_raises(self, protocol, fake_serial):
        fake_serial.set_response("#!\n\r")
        with pytest.raises(CommandError, match="Controller error"):
            protocol.set_mode(1, Mode.DISABLE)

    def test_bad_arg_response_raises(self, protocol, fake_serial):
        fake_serial.set_response("#?\n\r")
        with pytest.raises(CommandError, match="Invalid argument"):
            protocol.set_mode(1, Mode.DISABLE)

    def test_undefined_command_raises(self, protocol, fake_serial):
        fake_serial.set_response("FOOBAR is not defined\n\r")
        with pytest.raises(CommandError, match="Unknown command"):
            protocol._cmd("FOOBAR")

    def test_unexpected_non_ack_response_raises(self, protocol, fake_serial):
        fake_serial.set_response("some garbage\n\r")
        with pytest.raises(CommandError, match="Expected '##'"):
            protocol.set_mode(1, Mode.DISABLE)


# ══════════════════════════════════════════════════════════════════════════
#  Layer 2: Protocol — Command formatting & response parsing
# ══════════════════════════════════════════════════════════════════════════


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


class TestProtocolParsing:
    """Verify response parsing extracts the right values."""

    def test_get_device_info(self, protocol, fake_serial):
        fake_serial.set_response(
            "Mightex LED Driver:3.1.8 Device Module No.:SLC-SA04-U/S "
            "Device Serial No.:04-251013-011\n\r"
        )
        info = protocol.device_info()
        assert info.module_number == "SLC-SA04-U/S"
        assert info.firmware_version == "3.1.8"
        assert info.serial_number == "04-251013-011"

    def test_get_mode_parses_response(self, protocol, fake_serial):
        fake_serial.set_response("#1\n\r")
        assert protocol.get_mode(1) == Mode.NORMAL

    def test_get_mode_bad_response_raises(self, protocol, fake_serial):
        fake_serial.set_response("#garbage\n\r")
        with pytest.raises(CommandError, match="Unexpected mode"):
            protocol.get_mode(1)

    def test_get_normal_params(self, protocol, fake_serial):
        fake_serial.set_response("#50 60 200 100\n\r")
        max_ma, set_ma = protocol.get_normal_params(1)
        assert max_ma == 200
        assert set_ma == 100

    def test_get_normal_params_too_few_fields(self, protocol, fake_serial):
        fake_serial.set_response("#\n\r")
        with pytest.raises(CommandError, match="Cannot parse"):
            protocol.get_normal_params(1)

    def test_get_normal_params_non_numeric_raises(self, protocol, fake_serial):
        fake_serial.set_response("#abc def\n\r")
        with pytest.raises(CommandError, match="Cannot parse"):
            protocol.get_normal_params(1)

    def test_get_load_voltage(self, protocol, fake_serial):
        fake_serial.set_response("#1:3200\n\r")
        assert protocol.get_load_voltage(1) == 3200

    def test_get_load_voltage_bad_response(self, protocol, fake_serial):
        fake_serial.set_response("#garbage\n\r")
        with pytest.raises(CommandError, match="Cannot parse"):
            protocol.get_load_voltage(1)


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


# ══════════════════════════════════════════════════════════════════════════
#  Layer 3: Controller — User-facing API
# ══════════════════════════════════════════════════════════════════════════


class TestControllerConnection:
    def test_connect_sets_is_connected(self, controller):
        assert controller.is_connected

    def test_disconnect_clears_flag(self, controller):
        controller.disconnect()
        assert not controller.is_connected

    def test_command_when_disconnected_raises(self, controller):
        controller.disconnect()
        # _proto is set to None only before connect, but transport.send
        # will raise ConnectionError because the port is closed
        with pytest.raises((ConnectionError, Exception)):
            controller.get_device_info()

    def test_context_manager_closes(self, fake_serial):
        with patch("mightex_slc.transport.serial.Serial", return_value=fake_serial):
            with MightexSLC("/dev/fake") as led:
                assert led.is_connected
            assert not fake_serial.is_open


class TestControllerConvenience:
    """The high-level methods that compose multiple protocol calls."""

    def test_enable_channel_default_max(self, controller, fake_serial):
        assert controller.enable_channel(1, current_ma=50) is True
        assert any(b"NORMAL 1 1000 50" in w for w in fake_serial.written)

    def test_enable_channel_explicit_max(self, controller, fake_serial):
        assert controller.enable_channel(1, current_ma=50, max_current_ma=200) is True
        assert any(b"NORMAL 1 200 50" in w for w in fake_serial.written)

    def test_enable_channel_explicit_max_at_normal_limit(self, controller, fake_serial):
        """Explicit max_current_ma at the NORMAL ceiling should succeed."""
        assert controller.enable_channel(1, current_ma=500, max_current_ma=1000) is True

    def test_enable_channel_explicit_max_above_normal_limit(self, controller, fake_serial):
        """Explicit max_current_ma above the NORMAL ceiling should fail."""
        with pytest.raises(ValidationError, match="0-1000"):
            controller.enable_channel(1, current_ma=500, max_current_ma=1001)

    def test_disable_channel(self, controller, fake_serial):
        assert controller.disable_channel(1) is True
        assert any(b"MODE 1 0" in w for w in fake_serial.written)

    def test_set_mode_returns_true(self, controller, fake_serial):
        assert controller.set_mode(1, Mode.NORMAL) is True

    def test_set_normal_mode_returns_true(self, controller, fake_serial):
        assert controller.set_normal_mode(1, 200, 100) is True

    def test_set_current_returns_true(self, controller, fake_serial):
        assert controller.set_current(1, 75) is True

    def test_store_settings_returns_true(self, controller, fake_serial):
        assert controller.store_settings() is True

    def test_reset_returns_true(self, controller, fake_serial):
        assert controller.reset() is True

    def test_restore_defaults_returns_true(self, controller, fake_serial):
        assert controller.restore_defaults() is True

    def test_set_strobe_params_returns_true(self, controller, fake_serial):
        assert controller.set_strobe_params(1, max_current_ma=100, repeat=5) is True

    def test_set_strobe_step_returns_true(self, controller, fake_serial):
        assert controller.set_strobe_step(1, step=0, current_ma=50, duration_us=2000) is True

    def test_set_trigger_params_returns_true(self, controller, fake_serial):
        assert (
            controller.set_trigger_params(1, max_current_ma=100, polarity=TriggerPolarity.FALLING)
            is True
        )

    def test_set_trigger_step_returns_true(self, controller, fake_serial):
        assert controller.set_trigger_step(1, step=0, current_ma=50, duration_us=2000) is True

    def test_get_device_info(self, controller, fake_serial):
        fake_serial.set_response(
            "Mightex LED Driver:3.1.8 Device Module No.:SLC-SA04-U/S "
            "Device Serial No.:04-251013-011\n\r"
        )
        info = controller.get_device_info()
        assert info.module_number == "SLC-SA04-U/S"

    def test_get_mode(self, controller, fake_serial):
        fake_serial.set_response("#1\n\r")
        assert controller.get_mode(1) == Mode.NORMAL

    def test_get_normal_params(self, controller, fake_serial):
        fake_serial.set_response("#50 60 200 100\n\r")
        max_ma, set_ma = controller.get_normal_params(1)
        assert (max_ma, set_ma) == (200, 100)

    def test_get_load_voltage(self, controller, fake_serial):
        fake_serial.set_response("#1:3200\n\r")
        assert controller.get_load_voltage(1) == 3200


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
        for ch in range(1, 5):
            with suppress(Exception):
                self.led.disable_channel(ch)
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
