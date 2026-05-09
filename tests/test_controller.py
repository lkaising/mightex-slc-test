"""
Layer 3 — Controller tests.

Cover :class:`~mightex_slc.MightexSLC` user-facing API: connect/disconnect,
context manager, convenience wrappers, and the
``set_trigger_follower`` 5-command sequence.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mightex_slc import (
    FOLLOWER_DURATION_US,
    MAX_CURRENT_PULSED_MA,
    MightexConnectionError,
    MightexSLC,
    Mode,
    TriggerPolarity,
    ValidationError,
)


class TestControllerConnection:
    def test_connect_sets_is_connected(self, controller):
        assert controller.is_connected

    def test_disconnect_clears_flag(self, controller):
        controller.disconnect()
        assert not controller.is_connected

    def test_command_when_disconnected_raises(self, controller):
        controller.disconnect()
        # _proto is set to None only before connect, but transport.send
        # will raise MightexConnectionError because the port is closed
        with pytest.raises((MightexConnectionError, Exception)):
            controller.get_device_info()

    def test_context_manager_closes(self, fake_serial):
        with patch("mightex_slc.transport.serial.Serial", return_value=fake_serial):
            with MightexSLC("/dev/fake") as led:
                assert led.is_connected
            assert not fake_serial.is_open


class TestControllerConvenience:
    """The high-level methods that compose multiple protocol calls."""

    def test_enable_channel_default_max(self, controller, fake_serial):
        controller.enable_channel(1, current_ma=50)
        assert any(b"NORMAL 1 1000 50" in w for w in fake_serial.written)

    def test_enable_channel_explicit_max(self, controller, fake_serial):
        controller.enable_channel(1, current_ma=50, max_current_ma=200)
        assert any(b"NORMAL 1 200 50" in w for w in fake_serial.written)

    def test_enable_channel_explicit_max_at_normal_limit(self, controller, fake_serial):
        """Explicit max_current_ma at the NORMAL ceiling should succeed."""
        controller.enable_channel(1, current_ma=500, max_current_ma=1000)

    def test_enable_channel_explicit_max_above_normal_limit(self, controller, fake_serial):
        """Explicit max_current_ma above the NORMAL ceiling should fail."""
        with pytest.raises(ValidationError, match="0-1000"):
            controller.enable_channel(1, current_ma=500, max_current_ma=1001)

    def test_disable_channel(self, controller, fake_serial):
        controller.disable_channel(1)
        assert any(b"MODE 1 0" in w for w in fake_serial.written)

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


class TestTriggerFollower:
    """Tests for the set_trigger_follower convenience method."""

    def test_sends_five_commands_in_order(self, controller, fake_serial):
        """Verify the full safe programming sequence from the spec."""
        controller.set_trigger_follower(1, current_ma=1200)

        cmds = [w.decode("ascii").rstrip("\n\r") for w in fake_serial.written]
        assert cmds == [
            "MODE 1 0",  # Step 1: disable
            "TRIGGER 1 1200 0",  # Step 2: trigger params
            "TRIGP 1 0 1200 9999",  # Step 3: follower step
            "TRIGP 1 1 0 0",  # Step 4: terminator
            "MODE 1 3",  # Step 5: arm trigger mode
        ]

    def test_uses_follower_duration_constant(self, controller, fake_serial):
        """Confirm it uses FOLLOWER_DURATION_US (9999), not a magic number."""
        controller.set_trigger_follower(1, current_ma=600)
        trigp_cmd = [w for w in fake_serial.written if b"TRIGP 1 0" in w][0]
        assert f"TRIGP 1 0 600 {FOLLOWER_DURATION_US}".encode() in trigp_cmd

    def test_max_current_defaults_to_current(self, controller, fake_serial):
        """When max_current_ma is omitted, Imax should equal Iset."""
        controller.set_trigger_follower(2, current_ma=1000)
        trigger_cmd = [w for w in fake_serial.written if b"TRIGGER 2" in w][0]
        assert b"TRIGGER 2 1000 0" in trigger_cmd

    def test_explicit_max_current(self, controller, fake_serial):
        """When max_current_ma is specified, it should be used for Imax."""
        controller.set_trigger_follower(1, current_ma=800, max_current_ma=1200)
        trigger_cmd = [w for w in fake_serial.written if b"TRIGGER 1" in w][0]
        assert b"TRIGGER 1 1200 0" in trigger_cmd
        trigp_cmd = [w for w in fake_serial.written if b"TRIGP 1 0" in w][0]
        assert b"TRIGP 1 0 800 9999" in trigp_cmd

    def test_falling_edge_polarity(self, controller, fake_serial):
        controller.set_trigger_follower(1, current_ma=600, polarity=TriggerPolarity.FALLING)
        trigger_cmd = [w for w in fake_serial.written if b"TRIGGER 1" in w][0]
        assert b"TRIGGER 1 600 1" in trigger_cmd

    def test_invalid_channel_rejected(self, controller, fake_serial):
        with pytest.raises(ValidationError):
            controller.set_trigger_follower(0, current_ma=100)

    def test_current_above_pulsed_max_rejected(self, controller, fake_serial):
        with pytest.raises(ValidationError, match="0-3500"):
            controller.set_trigger_follower(1, current_ma=MAX_CURRENT_PULSED_MA + 1)

    def test_all_three_channels(self, controller, fake_serial):
        """Program all three NIR channels in sequence — matches spec Section 10.2."""
        controller.set_trigger_follower(1, current_ma=1200)
        controller.set_trigger_follower(2, current_ma=1000)
        controller.set_trigger_follower(3, current_ma=600)

        cmds = [w.decode("ascii").rstrip("\n\r") for w in fake_serial.written]

        # Channel 1
        assert "MODE 1 0" in cmds
        assert "TRIGGER 1 1200 0" in cmds
        assert "TRIGP 1 0 1200 9999" in cmds
        assert "TRIGP 1 1 0 0" in cmds
        assert "MODE 1 3" in cmds

        # Channel 2
        assert "MODE 2 0" in cmds
        assert "TRIGGER 2 1000 0" in cmds
        assert "TRIGP 2 0 1000 9999" in cmds
        assert "TRIGP 2 1 0 0" in cmds
        assert "MODE 2 3" in cmds

        # Channel 3
        assert "MODE 3 0" in cmds
        assert "TRIGGER 3 600 0" in cmds
        assert "TRIGP 3 0 600 9999" in cmds
        assert "TRIGP 3 1 0 0" in cmds
        assert "MODE 3 3" in cmds


class TestFollowerDurationConstant:
    """Verify the FOLLOWER_DURATION_US constant is accessible and correct."""

    def test_value(self):
        assert FOLLOWER_DURATION_US == 9999

    def test_importable_from_package(self):
        from mightex_slc import FOLLOWER_DURATION_US as fdu

        assert fdu == 9999
