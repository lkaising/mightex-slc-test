"""
Layer 2 — Protocol response handling.

Cover everything that comes back from the device: ack/error code handling
(``##``, ``#!``, ``#?``, undefined-command strings), structured response parsing
(``DeviceInfo``, mode, normal params, load voltage, trigger params/profile),
and the data-type sanity of the enums those responses are parsed into.
"""

from __future__ import annotations

import pytest

from mightex_slc import (
    CommandError,
    DeviceInfo,
    Mode,
    TriggerPolarity,
)

# ══════════════════════════════════════════════════════════════════════════
#  Data-type sanity (enums + DeviceInfo parsing)
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
#  Structured response parsing
# ══════════════════════════════════════════════════════════════════════════


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
