"""
Trigger programmer — YAML config loading and validation.

Cover :func:`mightex_slc.trigger_programmer.load_config` parsing of the
YAML format used by ``scripts/program_trigger.py``: required fields,
default values, range checks, and rejection of malformed input.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mightex_slc import ValidationError
from mightex_slc.protocol import TriggerPolarity
from mightex_slc.trigger_programmer import load_config

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
