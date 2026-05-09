"""
Layer 2 — Protocol tests.

Cover :class:`~mightex_slc.protocol.SLCProtocol` parsing, validation,
ack checking, and command formatting (every byte the protocol sends on
the wire and every byte it parses back).
"""

from __future__ import annotations

import pytest

from mightex_slc import (
    MAX_CURRENT_NORMAL_MA,
    MAX_CURRENT_PULSED_MA,
    CommandError,
    DeviceInfo,
    Mode,
    TriggerPolarity,
    ValidationError,
)

# ══════════════════════════════════════════════════════════════════════════
#  Parsing
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
#  Validation
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
#  Ack checking & error responses
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
            protocol.set_mode(1, Mode.DISABLE)

    def test_unexpected_non_ack_response_raises(self, protocol, fake_serial):
        fake_serial.set_response("some garbage\n\r")
        with pytest.raises(CommandError, match="Expected '##'"):
            protocol.set_mode(1, Mode.DISABLE)


# ══════════════════════════════════════════════════════════════════════════
#  Command formatting & response parsing
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

    def test_get_trigger_params(self, protocol, fake_serial):
        fake_serial.set_response("#1200 0\n\r")
        imax, polarity = protocol.get_trigger_params(1)
        assert imax == 1200
        assert polarity == TriggerPolarity.RISING

    def test_get_trigger_params_falling(self, protocol, fake_serial):
        fake_serial.set_response("#600 1\n\r")
        imax, polarity = protocol.get_trigger_params(1)
        assert imax == 600
        assert polarity == TriggerPolarity.FALLING

    def test_get_trigger_params_too_few_fields(self, protocol, fake_serial):
        fake_serial.set_response("#1200\n\r")
        with pytest.raises(CommandError, match="Cannot parse trigger"):
            protocol.get_trigger_params(1)

    def test_get_trigger_profile_single_step(self, protocol, fake_serial):
        fake_serial.set_response("#1200 9999\n\r")
        assert protocol.get_trigger_profile(1) == [(1200, 9999)]

    def test_get_trigger_profile_with_terminator(self, protocol, fake_serial):
        fake_serial.set_response("#1200 9999 0 0\n\r")
        assert protocol.get_trigger_profile(1) == [(1200, 9999), (0, 0)]

    def test_get_trigger_profile_empty(self, protocol, fake_serial):
        fake_serial.set_response("#\n\r")
        assert protocol.get_trigger_profile(1) == []

    def test_get_trigger_profile_odd_token_count_raises(self, protocol, fake_serial):
        fake_serial.set_response("#1200 9999 0\n\r")
        with pytest.raises(CommandError, match="odd token count"):
            protocol.get_trigger_profile(1)


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
