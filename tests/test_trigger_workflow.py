"""
Trigger programmer — programming and verification workflows.

Cover :func:`program_channel`, :func:`program_all`, :func:`verify_channel`,
:func:`verify_all`, and the :class:`ProgramReport` aggregation. These run
against the fake serial controller via the ``controller`` fixture.
"""

from __future__ import annotations

from unittest.mock import patch

from mightex_slc.protocol import TriggerPolarity
from mightex_slc.trigger_programmer import (
    ChannelConfig,
    TriggerConfig,
    program_all,
    program_channel,
    verify_all,
    verify_channel,
)

# ══════════════════════════════════════════════════════════════════════════
#  Programming
# ══════════════════════════════════════════════════════════════════════════


class TestProgramChannel:
    """Tests for program_channel using mock serial."""

    def test_program_channel_sends_full_follower_sequence(self, controller, fake_serial):
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

    def test_verify_channel_passes_when_mode_imax_and_step_match(self, controller, fake_serial):
        ch = self._make_ch()
        fake_serial.queue_responses(
            [
                "#3\n\r",  # ?MODE 1 → TRIGGER (3)
                "#1200 0\n\r",  # ?TRIGGER 1 → Imax=1200, polarity=0
                "#1200 9999 0 0\n\r",  # ?TRIGP 1 → step 0 + terminator
            ]
        )
        result = verify_channel(controller, ch)

        assert result.success is True
        assert "verified OK" in result.message

    def test_fails_on_wrong_mode(self, controller, fake_serial):
        ch = self._make_ch()
        fake_serial.queue_responses(
            [
                "#1\n\r",  # ?MODE 1 → NORMAL (wrong!)
                "#1200 0\n\r",
                "#1200 9999 0 0\n\r",
            ]
        )
        result = verify_channel(controller, ch)

        assert result.success is False
        assert "NORMAL" in result.message

    def test_fails_on_wrong_imax(self, controller, fake_serial):
        ch = self._make_ch()
        fake_serial.queue_responses(
            [
                "#3\n\r",
                "#800 0\n\r",  # Imax=800 (wrong!)
                "#1200 9999 0 0\n\r",
            ]
        )
        result = verify_channel(controller, ch)

        assert result.success is False
        assert "800" in result.message

    def test_fails_on_wrong_polarity(self, controller, fake_serial):
        ch = self._make_ch()
        fake_serial.queue_responses(
            [
                "#3\n\r",
                "#1200 1\n\r",  # falling, expected rising
                "#1200 9999 0 0\n\r",
            ]
        )
        result = verify_channel(controller, ch)

        assert result.success is False
        assert "polarity" in result.message

    def test_fails_on_wrong_step_current(self, controller, fake_serial):
        """Regression: substring matching used to pass when step current
        merely *contained* the expected value (e.g. expected 1200, profile
        reports 12000). Exact comparison now catches this."""
        ch = self._make_ch(current_ma=1200)
        fake_serial.queue_responses(
            [
                "#3\n\r",
                "#1200 0\n\r",
                "#12000 9999 0 0\n\r",  # 12000, not 1200
            ]
        )
        result = verify_channel(controller, ch)

        assert result.success is False
        assert "12000" in result.message
        assert "1200" in result.message

    def test_fails_on_empty_profile(self, controller, fake_serial):
        ch = self._make_ch()
        fake_serial.queue_responses(
            [
                "#3\n\r",
                "#1200 0\n\r",
                "#\n\r",  # empty profile
            ]
        )
        result = verify_channel(controller, ch)

        assert result.success is False
        assert "empty" in result.message


class TestVerifyAll:
    def test_verify_all_passes_when_every_channel_matches(self, controller, fake_serial):
        config = TriggerConfig(
            port="/dev/fake",
            store=True,
            channels=[
                ChannelConfig(1, "LED1", 850, "NIR-I", 1200, 1200, TriggerPolarity.RISING),
                ChannelConfig(2, "LED2", 940, "NIR-I", 1000, 1000, TriggerPolarity.RISING),
            ],
        )

        fake_serial.queue_responses(
            [
                "#3\n\r",
                "#1200 0\n\r",
                "#1200 9999 0 0\n\r",  # CH1
                "#3\n\r",
                "#1000 0\n\r",
                "#1000 9999 0 0\n\r",  # CH2
            ]
        )
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
