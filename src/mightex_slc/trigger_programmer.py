"""
Trigger programmer — reusable logic for programming SLC channels into
trigger-follower mode from a YAML configuration file.

This module provides the building blocks that both the CLI script and
future system-integration code can import directly::

    from mightex_slc.trigger_programmer import load_config, program_all, verify_all

    config = load_config("config/trigger_config.yaml")
    with get_controller(config.port) as led:
        report = program_all(led, config)
        report = verify_all(led, config)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .constants import MAX_CHANNEL, MAX_CURRENT_PULSED_MA, MIN_CHANNEL
from .controller import MightexSLC
from .exceptions import MightexError, ValidationError
from .protocol import Mode, TriggerPolarity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration data model
# ---------------------------------------------------------------------------

_VALID_POLARITIES = {"rising": TriggerPolarity.RISING, "falling": TriggerPolarity.FALLING}


@dataclass(frozen=True)
class ChannelConfig:
    """Validated configuration for a single SLC channel."""

    channel: int
    name: str
    wavelength_nm: int
    band: str
    current_ma: int
    max_current_ma: int
    polarity: TriggerPolarity

    @property
    def label(self) -> str:
        """Human-readable label, e.g. ``CH1 M850L3 (850 nm)``."""
        return f"CH{self.channel} {self.name} ({self.wavelength_nm} nm)"


@dataclass(frozen=True)
class TriggerConfig:
    """Top-level configuration loaded from a YAML file."""

    port: str
    store: bool
    channels: list[ChannelConfig] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Config loading & validation
# ---------------------------------------------------------------------------


def load_config(path: str | Path) -> TriggerConfig:
    """Load and validate a trigger configuration from a YAML file.

    Args:
        path: Path to the YAML config file.

    Returns:
        A validated :class:`TriggerConfig`.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValidationError: If the config is malformed or contains invalid values.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValidationError(f"Config file must be a YAML mapping, got {type(raw).__name__}")

    # -- Top-level fields ---------------------------------------------------
    port = raw.get("port")
    if not isinstance(port, str) or not port:
        raise ValidationError("Config must specify a non-empty 'port' string")

    store = raw.get("store", True)
    if not isinstance(store, bool):
        raise ValidationError(f"'store' must be a boolean, got {type(store).__name__}")

    # -- Channels -----------------------------------------------------------
    raw_channels = raw.get("channels")
    if not isinstance(raw_channels, dict) or not raw_channels:
        raise ValidationError("Config must contain a non-empty 'channels' mapping")

    channels: list[ChannelConfig] = []
    for ch_key, ch_data in raw_channels.items():
        channels.append(_parse_channel(ch_key, ch_data))

    channels.sort(key=lambda c: c.channel)

    return TriggerConfig(port=port, store=store, channels=channels)


def _parse_channel(ch_key: int | str, data: dict) -> ChannelConfig:
    """Parse and validate a single channel entry from the config."""
    try:
        channel = int(ch_key)
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"Channel key must be an integer, got {ch_key!r}") from exc

    if not (MIN_CHANNEL <= channel <= MAX_CHANNEL):
        raise ValidationError(f"Channel must be {MIN_CHANNEL}-{MAX_CHANNEL}, got {channel}")

    if not isinstance(data, dict):
        raise ValidationError(f"Channel {channel} config must be a mapping")

    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise ValidationError(f"Channel {channel}: 'name' must be a non-empty string")

    band = data.get("band", "")
    if not isinstance(band, str):
        raise ValidationError(f"Channel {channel}: 'band' must be a string")

    wavelength_nm = _require_positive_int(data, "wavelength_nm", channel)
    current_ma = _require_non_negative_int(data, "current_ma", channel)
    max_current_ma = _require_non_negative_int(data, "max_current_ma", channel)

    if current_ma > max_current_ma:
        raise ValidationError(
            f"Channel {channel}: current_ma ({current_ma}) exceeds "
            f"max_current_ma ({max_current_ma})"
        )
    if max_current_ma > MAX_CURRENT_PULSED_MA:
        raise ValidationError(
            f"Channel {channel}: max_current_ma ({max_current_ma}) exceeds "
            f"pulsed-mode limit ({MAX_CURRENT_PULSED_MA} mA)"
        )

    polarity_str = data.get("polarity", "rising")
    if polarity_str not in _VALID_POLARITIES:
        raise ValidationError(
            f"Channel {channel}: polarity must be one of "
            f"{list(_VALID_POLARITIES)}, got {polarity_str!r}"
        )
    polarity = _VALID_POLARITIES[polarity_str]

    return ChannelConfig(
        channel=channel,
        name=name,
        wavelength_nm=wavelength_nm,
        band=band,
        current_ma=current_ma,
        max_current_ma=max_current_ma,
        polarity=polarity,
    )


def _require_positive_int(data: dict, key: str, channel: int) -> int:
    val = data.get(key)
    if not isinstance(val, int) or val <= 0:
        raise ValidationError(f"Channel {channel}: '{key}' must be a positive integer, got {val!r}")
    return val


def _require_non_negative_int(data: dict, key: str, channel: int) -> int:
    val = data.get(key)
    if not isinstance(val, int) or val < 0:
        raise ValidationError(
            f"Channel {channel}: '{key}' must be a non-negative integer, got {val!r}"
        )
    return val


# ---------------------------------------------------------------------------
# Programming
# ---------------------------------------------------------------------------


@dataclass
class ChannelResult:
    """Outcome of a program or verify operation on a single channel."""

    channel_config: ChannelConfig
    success: bool
    message: str


@dataclass
class ProgramReport:
    """Aggregate outcome of a program_all or verify_all operation."""

    results: list[ChannelResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(r.success for r in self.results)

    @property
    def summary(self) -> str:
        passed = sum(1 for r in self.results if r.success)
        total = len(self.results)
        return f"{passed}/{total} channels {'OK' if self.all_ok else 'FAILED'}"


def program_channel(controller: MightexSLC, ch: ChannelConfig) -> ChannelResult:
    """Program a single channel into trigger-follower mode.

    Uses :meth:`MightexSLC.set_trigger_follower` which executes the full
    5-command safe programming sequence.

    Args:
        controller: A connected MightexSLC instance.
        ch: Channel configuration to program.

    Returns:
        A :class:`ChannelResult` indicating success or failure.
    """
    try:
        controller.set_trigger_follower(
            channel=ch.channel,
            current_ma=ch.current_ma,
            max_current_ma=ch.max_current_ma,
            polarity=ch.polarity,
        )
        msg = f"{ch.label} → TRIGGER follower, {ch.current_ma} mA"
        logger.info("Programmed %s", msg)
        return ChannelResult(ch, success=True, message=msg)

    except MightexError as exc:
        msg = f"{ch.label} → FAILED: {exc}"
        logger.error("Programming failed: %s", msg)
        return ChannelResult(ch, success=False, message=msg)


def verify_channel(controller: MightexSLC, ch: ChannelConfig) -> ChannelResult:
    """Verify that a channel is programmed as expected.

    Queries the channel's mode and trigger parameters, comparing against
    the expected configuration.

    Args:
        controller: A connected MightexSLC instance.
        ch: Expected channel configuration.

    Returns:
        A :class:`ChannelResult` indicating whether verification passed.
    """
    errors: list[str] = []

    try:
        mode = controller.get_mode(ch.channel)
        if mode != Mode.TRIGGER:
            errors.append(f"mode is {mode.name}, expected TRIGGER")

        # Check trigger parameters (Imax, polarity) via raw protocol query
        proto = controller._p  # noqa: SLF001 — internal access for verification
        response = proto._cmd(f"?TRIGGER {ch.channel}")  # noqa: SLF001
        # Response format: #<Imax> <polarity>
        parts = response.replace("#", "").split()
        if len(parts) >= 2:
            actual_imax = int(parts[0])
            actual_polarity = int(parts[1])
            if actual_imax != ch.max_current_ma:
                errors.append(f"Imax is {actual_imax} mA, expected {ch.max_current_ma} mA")
            if actual_polarity != int(ch.polarity):
                errors.append(
                    f"polarity is {actual_polarity}, expected {int(ch.polarity)} "
                    f"({'rising' if ch.polarity == TriggerPolarity.RISING else 'falling'})"
                )
        else:
            errors.append(f"could not parse ?TRIGGER response: {response!r}")

        # Check trigger profile via raw protocol query
        profile_response = proto._cmd(f"?TRIGP {ch.channel}")  # noqa: SLF001
        # We check for the presence of the expected current value
        # The exact response format varies, but should contain the programmed current
        profile_clean = profile_response.replace("#", "").strip()
        if str(ch.current_ma) not in profile_clean:
            errors.append(
                f"trigger profile does not contain expected current "
                f"({ch.current_ma} mA): {profile_response!r}"
            )

    except MightexError as exc:
        errors.append(f"query failed: {exc}")

    if errors:
        detail = "; ".join(errors)
        msg = f"{ch.label} → VERIFY FAILED: {detail}"
        logger.warning(msg)
        return ChannelResult(ch, success=False, message=msg)

    msg = f"{ch.label} → verified OK"
    logger.info(msg)
    return ChannelResult(ch, success=True, message=msg)


def program_all(controller: MightexSLC, config: TriggerConfig) -> ProgramReport:
    """Program all channels from config into trigger-follower mode.

    Args:
        controller: A connected MightexSLC instance.
        config: Full trigger configuration.

    Returns:
        A :class:`ProgramReport` with per-channel results.
    """
    report = ProgramReport()
    for ch in config.channels:
        result = program_channel(controller, ch)
        report.results.append(result)
    return report


def verify_all(controller: MightexSLC, config: TriggerConfig) -> ProgramReport:
    """Verify all channels match their expected configuration.

    Args:
        controller: A connected MightexSLC instance.
        config: Expected trigger configuration.

    Returns:
        A :class:`ProgramReport` with per-channel verification results.
    """
    report = ProgramReport()
    for ch in config.channels:
        result = verify_channel(controller, ch)
        report.results.append(result)
    return report
