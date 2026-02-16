"""
Tests for the trigger programmer module.

Covers:
* Config loading and validation (valid YAML, missing fields, bad values)
* Channel programming (success, failure, all-channels)
* Channel verification (pass, fail, query errors)
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from mightex_slc import ValidationError
from mightex_slc.protocol import TriggerPolarity
from mightex_slc.trigger_programmer import (
    ChannelConfig,
    TriggerConfig,
    load_config,
    program_all,
    program_channel,
    verify_all,
    verify_channel,
)

# ══════════════════════════════════════════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def config_dir(tmp_path: Path) -> Path:
    """Return a temp directory for config files."""
    return tmp_path


def write_config(path: Path, content: str) -> Path:
    """Write a YAML config file and return its path."""
    config_file = path / "test_config.yaml"
    config_file.write_text(textwrap.dedent(content))
    return config_file


VALID_CONFIG = """\
    port: /dev/ttyUSB0
    store: true
    channels:
      1:
        name: M850L3
        wavelength_nm: 850
        band: NIR-I
        current_ma: 1200
        max_current_ma: 1200
        polarity: rising
      2:
        name: M940L3
        wavelength_nm: 940
        band: NIR-I
        current_ma: 1000
        max_current_ma: 1000
        polarity: rising
      3:
        name: M1050L4
        wavelength_nm: 1050
        band: NIR-II
        current_ma: 600
        max_current_ma: 600
        polarity: rising
"""

MINIMAL_CONFIG = """\
    port: /dev/ttyUSB0
    channels:
      1:
        name: TestLED
        wavelength_nm: 850
        band: NIR-I
        current_ma: 100
        max_current_ma: 200
"""


# ══════════════════════════════════════════════════════════════════════════
#  Config loading — valid configs
# ══════════════════════════════════════════════════════════════════════════


class TestLoadConfigValid:
    def test_loads_three_channels(self, config_dir):
        path = write_config(config_dir, VALID_CONFIG)
        config = load_config(path)
        assert len(config.channels) == 3

    def test_port(self, config_dir):
        path = write_config(config_dir, VALID_CONFIG)
        config = load_config(path)
        assert config.port == "/dev/ttyUSB0"

    def test_store_flag(self, config_dir):
        path = write_config(config_dir, VALID_CONFIG)
        config = load_config(path)
        assert config.store is True

    def test_store_defaults_true(self, config_dir):
        path = write_config(config_dir, MINIMAL_CONFIG)
        config = load_config(path)
        assert config.store is True

    def test_channel_values(self, config_dir):
        path = write_config(config_dir, VALID_CONFIG)
        config = load_config(path)
        ch1 = config.channels[0]
        assert ch1.channel == 1
        assert ch1.name == "M850L3"
        assert ch1.wavelength_nm == 850
        assert ch1.band == "NIR-I"
        assert ch1.current_ma == 1200
        assert ch1.max_current_ma == 1200
        assert ch1.polarity == TriggerPolarity.RISING

    def test_channels_sorted_by_number(self, config_dir):
        # Write channels out of order
        content = """\
            port: /dev/ttyUSB0
            channels:
              3:
                name: LED3
                wavelength_nm: 1050
                band: NIR-II
                current_ma: 600
                max_current_ma: 600
              1:
                name: LED1
                wavelength_nm: 850
                band: NIR-I
                current_ma: 1200
                max_current_ma: 1200
        """
        path = write_config(config_dir, content)
        config = load_config(path)
        assert [ch.channel for ch in config.channels] == [1, 3]

    def test_falling_polarity(self, config_dir):
        content = """\
            port: /dev/ttyUSB0
            channels:
              1:
                name: LED1
                wavelength_nm: 850
                band: NIR-I
                current_ma: 100
                max_current_ma: 200
                polarity: falling
        """
        path = write_config(config_dir, content)
        config = load_config(path)
        assert config.channels[0].polarity == TriggerPolarity.FALLING

    def test_polarity_defaults_rising(self, config_dir):
        path = write_config(config_dir, MINIMAL_CONFIG)
        config = load_config(path)
        assert config.channels[0].polarity == TriggerPolarity.RISING

    def test_channel_label(self, config_dir):
        path = write_config(config_dir, VALID_CONFIG)
        config = load_config(path)
        assert config.channels[0].label == "CH1 M850L3 (850 nm)"


# ══════════════════════════════════════════════════════════════════════════
#  Config loading — invalid configs
# ══════════════════════════════════════════════════════════════════════════


class TestLoadConfigInvalid:
    def test_file_not_found(self, config_dir):
        with pytest.raises(FileNotFoundError):
            load_config(config_dir / "nonexistent.yaml")

    def test_not_a_mapping(self, config_dir):
        path = write_config(config_dir, "- just\n- a\n- list\n")
        with pytest.raises(ValidationError, match="mapping"):
            load_config(path)

    def test_missing_port(self, config_dir):
        content = """\
            channels:
              1:
                name: LED
                wavelength_nm: 850
                band: NIR
                current_ma: 100
                max_current_ma: 200
        """
        path = write_config(config_dir, content)
        with pytest.raises(ValidationError, match="port"):
            load_config(path)

    def test_missing_channels(self, config_dir):
        content = "port: /dev/ttyUSB0\n"
        path = write_config(config_dir, content)
        with pytest.raises(ValidationError, match="channels"):
            load_config(path)

    def test_empty_channels(self, config_dir):
        content = """\
            port: /dev/ttyUSB0
            channels: {}
        """
        path = write_config(config_dir, content)
        with pytest.raises(ValidationError, match="channels"):
            load_config(path)

    def test_channel_number_out_of_range(self, config_dir):
        content = """\
            port: /dev/ttyUSB0
            channels:
              9:
                name: LED
                wavelength_nm: 850
                band: NIR
                current_ma: 100
                max_current_ma: 200
        """
        path = write_config(config_dir, content)
        with pytest.raises(ValidationError, match="1-4"):
            load_config(path)

    def test_missing_name(self, config_dir):
        content = """\
            port: /dev/ttyUSB0
            channels:
              1:
                wavelength_nm: 850
                band: NIR
                current_ma: 100
                max_current_ma: 200
        """
        path = write_config(config_dir, content)
        with pytest.raises(ValidationError, match="name"):
            load_config(path)

    def test_missing_current(self, config_dir):
        content = """\
            port: /dev/ttyUSB0
            channels:
              1:
                name: LED
                wavelength_nm: 850
                band: NIR
                max_current_ma: 200
        """
        path = write_config(config_dir, content)
        with pytest.raises(ValidationError, match="current_ma"):
            load_config(path)

    def test_current_exceeds_max(self, config_dir):
        content = """\
            port: /dev/ttyUSB0
            channels:
              1:
                name: LED
                wavelength_nm: 850
                band: NIR
                current_ma: 500
                max_current_ma: 200
        """
        path = write_config(config_dir, content)
        with pytest.raises(ValidationError, match="exceeds"):
            load_config(path)

    def test_max_current_exceeds_pulsed_limit(self, config_dir):
        content = """\
            port: /dev/ttyUSB0
            channels:
              1:
                name: LED
                wavelength_nm: 850
                band: NIR
                current_ma: 100
                max_current_ma: 4000
        """
        path = write_config(config_dir, content)
        with pytest.raises(ValidationError, match="3500"):
            load_config(path)

    def test_invalid_polarity(self, config_dir):
        content = """\
            port: /dev/ttyUSB0
            channels:
              1:
                name: LED
                wavelength_nm: 850
                band: NIR
                current_ma: 100
                max_current_ma: 200
                polarity: both_edges
        """
        path = write_config(config_dir, content)
        with pytest.raises(ValidationError, match="polarity"):
            load_config(path)

    def test_store_not_bool(self, config_dir):
        content = """\
            port: /dev/ttyUSB0
            store: "yes"
            channels:
              1:
                name: LED
                wavelength_nm: 850
                band: NIR
                current_ma: 100
                max_current_ma: 200
        """
        path = write_config(config_dir, content)
        with pytest.raises(ValidationError, match="store.*bool"):
            load_config(path)


# ══════════════════════════════════════════════════════════════════════════
#  Programming
# ══════════════════════════════════════════════════════════════════════════


class TestProgramChannel:
    """Tests for program_channel using mock serial."""

    def test_success(self, controller, fake_serial):
        ch = ChannelConfig(
            channel=1,
            name="M850L3",
            wavelength_nm=850,
            band="NIR-I",
            current_ma=1200,
            max_current_ma=1200,
            polarity=TriggerPolarity.RISING,
        )
        result = program_channel(controller, ch)
        assert result.success is True
        assert "1200 mA" in result.message

    def test_sends_correct_commands(self, controller, fake_serial):
        ch = ChannelConfig(
            channel=2,
            name="M940L3",
            wavelength_nm=940,
            band="NIR-I",
            current_ma=1000,
            max_current_ma=1000,
            polarity=TriggerPolarity.RISING,
        )
        program_channel(controller, ch)
        cmds = [w.decode("ascii").rstrip("\n\r") for w in fake_serial.written]
        assert "MODE 2 0" in cmds
        assert "TRIGGER 2 1000 0" in cmds
        assert "TRIGP 2 0 1000 9999" in cmds
        assert "TRIGP 2 1 0 0" in cmds
        assert "MODE 2 3" in cmds

    def test_failure_returns_error_result(self, controller, fake_serial):
        # Make the first command fail
        fake_serial.set_response("#!\n\r")
        ch = ChannelConfig(
            channel=1,
            name="M850L3",
            wavelength_nm=850,
            band="NIR-I",
            current_ma=1200,
            max_current_ma=1200,
            polarity=TriggerPolarity.RISING,
        )
        result = program_channel(controller, ch)
        assert result.success is False
        assert "FAILED" in result.message


class TestProgramAll:
    def test_programs_all_channels(self, controller, fake_serial):
        config = TriggerConfig(
            port="/dev/fake",
            store=True,
            channels=[
                ChannelConfig(1, "M850L3", 850, "NIR-I", 1200, 1200, TriggerPolarity.RISING),
                ChannelConfig(2, "M940L3", 940, "NIR-I", 1000, 1000, TriggerPolarity.RISING),
                ChannelConfig(3, "M1050L4", 1050, "NIR-II", 600, 600, TriggerPolarity.RISING),
            ],
        )
        report = program_all(controller, config)
        assert report.all_ok
        assert len(report.results) == 3
        assert report.summary == "3/3 channels OK"

    def test_partial_failure(self, controller, fake_serial):
        """If one channel fails, the report reflects it but others still run."""
        config = TriggerConfig(
            port="/dev/fake",
            store=True,
            channels=[
                ChannelConfig(1, "LED1", 850, "NIR-I", 1200, 1200, TriggerPolarity.RISING),
                ChannelConfig(2, "LED2", 940, "NIR-I", 1000, 1000, TriggerPolarity.RISING),
            ],
        )

        # We need to make the 6th command fail (first cmd of channel 2's sequence).
        # Channel 1 sends 5 commands, then channel 2 starts with MODE 2 0.
        # FakeSerial resets to default after each staged response, so we need
        # a different approach: patch set_trigger_follower for channel 2 only.
        original = controller.set_trigger_follower

        def side_effect(channel, **kwargs):
            if channel == 2:
                from mightex_slc.exceptions import CommandError

                raise CommandError("Simulated failure")
            return original(channel, **kwargs)

        with patch.object(controller, "set_trigger_follower", side_effect=side_effect):
            report = program_all(controller, config)

        assert not report.all_ok
        assert report.results[0].success is True
        assert report.results[1].success is False
        assert report.summary == "1/2 channels FAILED"


# ══════════════════════════════════════════════════════════════════════════
#  Verification
# ══════════════════════════════════════════════════════════════════════════


class TestVerifyChannel:
    def _make_ch(self, channel=1, current_ma=1200, max_current_ma=1200):
        return ChannelConfig(
            channel=channel,
            name="M850L3",
            wavelength_nm=850,
            band="NIR-I",
            current_ma=current_ma,
            max_current_ma=max_current_ma,
            polarity=TriggerPolarity.RISING,
        )

    def test_passes_when_correct(self, controller, fake_serial):
        """Set up staged responses that match the expected config."""
        ch = self._make_ch()

        # verify_channel sends 3 queries: ?MODE, ?TRIGGER, ?TRIGP
        # FakeSerial auto-resets to "##" after each staged response, so we
        # need to intercept at the protocol level.
        responses = iter(
            [
                "#3\n\r",  # ?MODE 1 → TRIGGER (3)
                "#1200 0\n\r",  # ?TRIGGER 1 → Imax=1200, polarity=0
                "#1200 9999\n\r",  # ?TRIGP 1 → contains 1200
            ]
        )

        original_send = controller._transport.send

        def mock_send(cmd):
            if cmd.startswith("?"):
                # Intercept query commands with our staged responses
                resp = next(responses)
                return resp.strip()
            return original_send(cmd)

        with patch.object(controller._transport, "send", side_effect=mock_send):
            result = verify_channel(controller, ch)

        assert result.success is True
        assert "verified OK" in result.message

    def test_fails_on_wrong_mode(self, controller, fake_serial):
        ch = self._make_ch()

        responses = iter(
            [
                "#1\n\r",  # ?MODE 1 → NORMAL (wrong!)
                "#1200 0\n\r",  # ?TRIGGER 1
                "#1200 9999\n\r",  # ?TRIGP 1
            ]
        )

        original_send = controller._transport.send

        def mock_send(cmd):
            if cmd.startswith("?"):
                return next(responses).strip()
            return original_send(cmd)

        with patch.object(controller._transport, "send", side_effect=mock_send):
            result = verify_channel(controller, ch)

        assert result.success is False
        assert "NORMAL" in result.message

    def test_fails_on_wrong_imax(self, controller, fake_serial):
        ch = self._make_ch()

        responses = iter(
            [
                "#3\n\r",  # mode OK
                "#800 0\n\r",  # Imax=800 (wrong!)
                "#1200 9999\n\r",  # profile OK
            ]
        )

        original_send = controller._transport.send

        def mock_send(cmd):
            if cmd.startswith("?"):
                return next(responses).strip()
            return original_send(cmd)

        with patch.object(controller._transport, "send", side_effect=mock_send):
            result = verify_channel(controller, ch)

        assert result.success is False
        assert "800" in result.message


class TestVerifyAll:
    def test_all_pass(self, controller, fake_serial):
        config = TriggerConfig(
            port="/dev/fake",
            store=True,
            channels=[
                ChannelConfig(1, "LED1", 850, "NIR-I", 1200, 1200, TriggerPolarity.RISING),
                ChannelConfig(2, "LED2", 940, "NIR-I", 1000, 1000, TriggerPolarity.RISING),
            ],
        )

        # Build responses for both channels (3 queries each)
        all_responses = iter(
            [
                "#3\n\r",
                "#1200 0\n\r",
                "#1200 9999\n\r",  # CH1
                "#3\n\r",
                "#1000 0\n\r",
                "#1000 9999\n\r",  # CH2
            ]
        )

        original_send = controller._transport.send

        def mock_send(cmd):
            if cmd.startswith("?"):
                return next(all_responses).strip()
            return original_send(cmd)

        with patch.object(controller._transport, "send", side_effect=mock_send):
            report = verify_all(controller, config)

        assert report.all_ok
        assert report.summary == "2/2 channels OK"


# ══════════════════════════════════════════════════════════════════════════
#  Report
# ══════════════════════════════════════════════════════════════════════════


class TestProgramReport:
    def test_all_ok_true(self):
        from mightex_slc.trigger_programmer import ChannelResult, ProgramReport

        ch = ChannelConfig(1, "LED", 850, "NIR", 100, 200, TriggerPolarity.RISING)
        report = ProgramReport(
            results=[
                ChannelResult(ch, success=True, message="ok"),
                ChannelResult(ch, success=True, message="ok"),
            ]
        )
        assert report.all_ok is True

    def test_all_ok_false_on_any_failure(self):
        from mightex_slc.trigger_programmer import ChannelResult, ProgramReport

        ch = ChannelConfig(1, "LED", 850, "NIR", 100, 200, TriggerPolarity.RISING)
        report = ProgramReport(
            results=[
                ChannelResult(ch, success=True, message="ok"),
                ChannelResult(ch, success=False, message="fail"),
            ]
        )
        assert report.all_ok is False

    def test_summary_format(self):
        from mightex_slc.trigger_programmer import ChannelResult, ProgramReport

        ch = ChannelConfig(1, "LED", 850, "NIR", 100, 200, TriggerPolarity.RISING)
        report = ProgramReport(
            results=[
                ChannelResult(ch, success=True, message="ok"),
                ChannelResult(ch, success=False, message="fail"),
            ]
        )
        assert report.summary == "1/2 channels FAILED"

    def test_empty_report_is_ok(self):
        from mightex_slc.trigger_programmer import ProgramReport

        report = ProgramReport()
        assert report.all_ok is True
        assert report.summary == "0/0 channels OK"
