"""
Hardware integration tests — require a real SLC controller on
``/dev/ttyUSB0``. Skipped by default; opt in with ``pytest -m hardware``.
"""

from __future__ import annotations

import time
from contextlib import suppress

import pytest

from mightex_slc import MightexSLC, Mode

HARDWARE_PORT = "/dev/ttyUSB0"
SAFE_CURRENT = 10  # mA — low enough to be safe for any LED


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
        self.led.enable_channel(1, SAFE_CURRENT)
        assert self.led.get_mode(1) == Mode.NORMAL
        self.led.disable_channel(1)
        assert self.led.get_mode(1) == Mode.DISABLE

    def test_all_channels_respond(self):
        for ch in range(1, 5):
            self.led.disable_channel(ch)
            assert self.led.get_mode(ch) == Mode.DISABLE
