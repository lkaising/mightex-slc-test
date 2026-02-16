#!/usr/bin/env python3
"""
Program Trigger — Configure SLC channels for trigger-follower mode.

Reads a YAML config file and programs each channel into trigger-follower
mode, where the LED output follows the trigger input level (ON while HIGH,
OFF while LOW).

Usage:
    python scripts/program_trigger.py                           # one-shot, default config
    python scripts/program_trigger.py --config path/to/cfg.yaml # custom config
    python scripts/program_trigger.py --verify-only             # check without programming
    python scripts/program_trigger.py --no-store                # skip NV memory persist
    python scripts/program_trigger.py --interactive             # menu-driven mode
"""

from __future__ import annotations

import argparse
import sys
from contextlib import suppress
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mightex_slc import MightexError, MightexSLC, Mode
from mightex_slc.trigger_programmer import (
    ChannelConfig,
    ProgramReport,
    TriggerConfig,
    load_config,
    program_all,
    program_channel,
    verify_all,
    verify_channel,
)

# ---------------------------------------------------------------------------
# Default config location (relative to this script)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "trigger_config.yaml"

# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------


class C:
    """ANSI color codes (no-op on non-TTY)."""

    if sys.stdout.isatty():
        BOLD = "\033[1m"
        DIM = "\033[2m"
        GREEN = "\033[32m"
        YELLOW = "\033[33m"
        RED = "\033[31m"
        CYAN = "\033[36m"
        RESET = "\033[0m"
    else:
        BOLD = DIM = GREEN = YELLOW = RED = CYAN = RESET = ""


def ok(text: str) -> None:
    print(f"  {C.GREEN}✓{C.RESET} {text}")


def fail(text: str) -> None:
    print(f"  {C.RED}✗{C.RESET} {text}")


def warn(text: str) -> None:
    print(f"  {C.YELLOW}⚠{C.RESET} {text}")


def info(text: str) -> None:
    print(f"  {C.DIM}{text}{C.RESET}")


def banner(text: str) -> None:
    print(f"\n{C.BOLD}{'═' * 60}")
    print(f"  {text}")
    print(f"{'═' * 60}{C.RESET}")


def prompt(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"  {text}{suffix}: ").strip()
    except EOFError:
        return default
    return val if val else default


def prompt_int(text: str, default: int | None = None) -> int | None:
    raw = prompt(text, str(default) if default is not None else "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        fail(f"Invalid number: {raw}")
        return None


def confirm(text: str) -> bool:
    return prompt(f"{text} (y/n)", "n").lower().startswith("y")


# ---------------------------------------------------------------------------
# Report display
# ---------------------------------------------------------------------------


def print_report(report: ProgramReport, heading: str) -> None:
    """Print a formatted report of channel results."""
    banner(heading)
    for r in report.results:
        if r.success:
            ok(r.message)
        else:
            fail(r.message)
    print()
    status = f"{C.GREEN}ALL OK{C.RESET}" if report.all_ok else f"{C.RED}FAILURES DETECTED{C.RESET}"
    print(f"  {report.summary}  —  {status}")


def print_config_summary(config: TriggerConfig) -> None:
    """Print a summary of the loaded config."""
    print(f"  Port:  {config.port}")
    print(f"  Store: {'yes' if config.store else 'no'}")
    print("  Channels:")
    for ch in config.channels:
        polarity_str = "rising" if ch.polarity == 0 else "falling"
        print(
            f"    CH{ch.channel}: {ch.name:8s} ({ch.wavelength_nm:4d} nm, {ch.band:6s}) "
            f"— {ch.current_ma:4d} mA  (Imax={ch.max_current_ma} mA, {polarity_str})"
        )


# ---------------------------------------------------------------------------
# One-shot mode
# ---------------------------------------------------------------------------


def run_oneshot(config: TriggerConfig, verify_only: bool, no_store: bool) -> int:
    """Execute the one-shot programming sequence. Returns exit code."""
    banner("SLC Trigger Follower Programmer")
    print_config_summary(config)

    # Connect
    print()
    try:
        controller = MightexSLC(config.port)
        controller.connect()
        ok(f"Connected to {config.port}")
    except MightexError as exc:
        fail(f"Cannot connect: {exc}")
        return 1

    # Show device info
    try:
        dev = controller.get_device_info()
        info(f"Device: {dev.module_number} (FW {dev.firmware_version}, SN {dev.serial_number})")
    except MightexError:
        warn("Could not read device info")

    exit_code = 0

    try:
        if verify_only:
            # Verify-only mode
            report = verify_all(controller, config)
            print_report(report, "Verification Results")
            if not report.all_ok:
                exit_code = 1
        else:
            # Program
            report = program_all(controller, config)
            print_report(report, "Programming Results")

            if not report.all_ok:
                fail("Programming incomplete — skipping verification and store.")
                exit_code = 1
            else:
                # Verify
                v_report = verify_all(controller, config)
                print_report(v_report, "Verification Results")

                if not v_report.all_ok:
                    fail("Verification failed — settings NOT stored.")
                    exit_code = 1
                elif no_store:
                    warn("--no-store: skipping NV memory persist.")
                elif config.store:
                    # Store to NV memory
                    try:
                        controller.store_settings()
                        ok("Settings stored to non-volatile memory.")
                    except MightexError as exc:
                        fail(f"Store failed: {exc}")
                        exit_code = 1
                else:
                    info("Config has store: false — skipping NV memory persist.")

    finally:
        controller.disconnect()
        info("Disconnected.")

    return exit_code


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

MENU = [
    ("1", "Program All", "Program all channels from config"),
    ("2", "Program One", "Program a single channel"),
    ("3", "Verify All", "Check all channels match config"),
    ("4", "Verify One", "Check a single channel"),
    ("5", "Adjust Current", "Change a channel's drive current"),
    ("6", "Store Settings", "Save to non-volatile memory"),
    ("7", "Device Status", "Query device info and channel modes"),
    ("q", "Quit", "Disconnect and exit"),
]


def pick_channel(config: TriggerConfig) -> ChannelConfig | None:
    """Let the user choose a channel from the config."""
    print()
    for ch in config.channels:
        print(f"    {ch.channel}) {ch.name}  —  {ch.wavelength_nm} nm  ({ch.current_ma} mA)")
    val = prompt_int("Channel")
    if val is None:
        return None
    for ch in config.channels:
        if ch.channel == val:
            return ch
    fail(f"Channel {val} not in config")
    return None


def do_program_all(controller: MightexSLC, config: TriggerConfig) -> None:
    report = program_all(controller, config)
    print_report(report, "Programming Results")


def do_program_one(controller: MightexSLC, config: TriggerConfig) -> None:
    ch = pick_channel(config)
    if ch is None:
        return
    result = program_channel(controller, ch)
    if result.success:
        ok(result.message)
    else:
        fail(result.message)


def do_verify_all(controller: MightexSLC, config: TriggerConfig) -> None:
    report = verify_all(controller, config)
    print_report(report, "Verification Results")


def do_verify_one(controller: MightexSLC, config: TriggerConfig) -> None:
    ch = pick_channel(config)
    if ch is None:
        return
    result = verify_channel(controller, ch)
    if result.success:
        ok(result.message)
    else:
        fail(result.message)


def do_adjust_current(controller: MightexSLC, config: TriggerConfig) -> None:
    banner("Adjust Channel Current")
    ch = pick_channel(config)
    if ch is None:
        return

    new_ma = prompt_int(f"New current for CH{ch.channel} (currently {ch.current_ma} mA)")
    if new_ma is None:
        return
    if new_ma > ch.max_current_ma:
        fail(f"{new_ma} mA exceeds max_current_ma ({ch.max_current_ma} mA)")
        return

    try:
        # Reprogram with new current using the safe sequence
        controller.set_trigger_follower(
            channel=ch.channel,
            current_ma=new_ma,
            max_current_ma=ch.max_current_ma,
            polarity=ch.polarity,
        )
        ok(f"CH{ch.channel} reprogrammed to {new_ma} mA")
        warn("This change is in RAM only. Use 'Store Settings' to persist.")
    except MightexError as exc:
        fail(f"Failed: {exc}")


def do_store(controller: MightexSLC, config: TriggerConfig) -> None:
    try:
        controller.store_settings()
        ok("Settings stored to non-volatile memory.")
    except MightexError as exc:
        fail(f"Store failed: {exc}")


def do_status(controller: MightexSLC, config: TriggerConfig) -> None:
    banner("Device Status")

    try:
        dev = controller.get_device_info()
        print(f"  Model:    {dev.module_number}")
        print(f"  Firmware: {dev.firmware_version}")
        print(f"  Serial:   {dev.serial_number}")
    except MightexError:
        warn("Could not read device info")

    print()
    for ch in config.channels:
        try:
            mode = controller.get_mode(ch.channel)
            mode_str = f"{C.GREEN}{mode.name}{C.RESET}" if mode == Mode.TRIGGER else mode.name
            print(f"  CH{ch.channel} {ch.name:8s} ({ch.wavelength_nm:4d} nm): mode = {mode_str}")
        except MightexError as exc:
            fail(f"CH{ch.channel}: query failed — {exc}")


ACTIONS = {
    "1": do_program_all,
    "2": do_program_one,
    "3": do_verify_all,
    "4": do_verify_one,
    "5": do_adjust_current,
    "6": do_store,
    "7": do_status,
}


def run_interactive(config: TriggerConfig) -> int:
    """Run the interactive menu loop. Returns exit code."""
    banner("SLC Trigger Follower Programmer  (Interactive)")
    print_config_summary(config)

    # Connect
    print()
    try:
        controller = MightexSLC(config.port)
        controller.connect()
        ok(f"Connected to {config.port}")
    except MightexError as exc:
        fail(f"Cannot connect: {exc}")
        return 1

    try:
        while True:
            line = "─" * 50
            print(f"\n{C.BOLD}  Menu{C.RESET}")
            print(f"  {C.DIM}{line}{C.RESET}")
            for key, label, desc in MENU:
                print(f"    {C.CYAN}{key}{C.RESET})  {label:18s} {C.DIM}— {desc}{C.RESET}")
            print()

            choice = prompt("Choice", "q").lower()
            if choice == "q":
                break

            action = ACTIONS.get(choice)
            if action:
                action(controller, config)
            else:
                fail(f"Unknown option: {choice}")

    except KeyboardInterrupt:
        print(f"\n\n  {C.YELLOW}Interrupted!{C.RESET}")

    finally:
        # Safety: disable all channels before exit
        for ch in config.channels:
            with suppress(MightexError):
                controller.disable_channel(ch.channel)
        controller.disconnect()
        info("Disconnected.")

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Program SLC channels into trigger-follower mode from a YAML config.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Path to YAML config file (default: {DEFAULT_CONFIG.name})",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify current programming without making changes",
    )
    parser.add_argument(
        "--no-store",
        action="store_true",
        help="Skip saving to non-volatile memory (useful for experimentation)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive menu mode",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Load config
    try:
        config = load_config(args.config)
    except (FileNotFoundError, Exception) as exc:
        print(f"{C.RED}✗{C.RESET} Config error: {exc}", file=sys.stderr)
        return 1

    # Override store if --no-store
    if args.no_store:
        # Create a new config with store=False
        config = TriggerConfig(port=config.port, store=False, channels=config.channels)

    if args.interactive:
        return run_interactive(config)
    else:
        return run_oneshot(config, verify_only=args.verify_only, no_store=args.no_store)


if __name__ == "__main__":
    sys.exit(main())
