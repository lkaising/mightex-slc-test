"""
Layer 2 — Protocol input validation.

Cover the bad-input-rejection paths in :class:`~mightex_slc.protocol.SLCProtocol`:
channel range, current ceilings, mode enum, step indices/durations, repeat count.
The protocol must reject invalid arguments before they reach the wire.
"""

from __future__ import annotations

import pytest

from mightex_slc import (
    MAX_CURRENT_NORMAL_MA,
    MAX_CURRENT_PULSED_MA,
    Mode,
    ValidationError,
)


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
