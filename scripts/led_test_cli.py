#!/usr/bin/env python3
"""
LED Test CLI — Interactive test harness for Thorlabs NIR LEDs on Mightex SLC.

Channel mapping:
    CH1: M850L3   (850 nm)  — max 1000 mA (datasheet 1200 mA, capped by NORMAL mode)
    CH2: M940L3   (940 nm)  — max 1000 mA
    CH3: M1050L4  (1050 nm) — max  600 mA

Usage:
    python scripts/led_test_cli.py
    python scripts/led_test_cli.py --port /dev/ttyUSB1
"""

from __future__ import annotations

import argparse
import sys
import time
from contextlib import suppress

# Add src to path so we can import without installing
sys.path.insert(0, "src")

from mightex_slc import MightexError, MightexSLC, Mode

# ═══════════════════════════════════════
#  LED / Channel Configuration
# ═══════════════════════════════════════

LEDS = {
    1: {"name": "M850L3", "wavelength": "850 nm", "max_ma": 1000, "band": "NIR-I"},
    2: {"name": "M940L3", "wavelength": "940 nm", "max_ma": 1000, "band": "NIR-I"},
    3: {"name": "M1050L4", "wavelength": "1050 nm", "max_ma": 600, "band": "NIR-II"},
}

SAFE_DEFAULT_MA = 100  # Default current for quick tests
HIGH_CURRENT_WARN_MA = 500  # Confirm before going above this


# ═══════════════════════════════════════
#  Terminal helpers
# ═══════════════════════════════════════


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


def banner(text: str) -> None:
    print(f"\n{C.BOLD}{'═' * 60}")
    print(f"  {text}")
    print(f"{'═' * 60}{C.RESET}")


def info(text: str) -> None:
    print(f"  {C.GREEN}✓{C.RESET} {text}")


def warn(text: str) -> None:
    print(f"  {C.YELLOW}⚠{C.RESET} {text}")


def error(text: str) -> None:
    print(f"  {C.RED}✗{C.RESET} {text}")


def prompt(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"  {text}{suffix}: ").strip()
    except EOFError:
        return default
    return val if val else default


def prompt_int(text: str, default: int | None = None) -> int | None:
    """Prompt for an integer.  Returns None on empty input with no default."""
    raw = prompt(text, str(default) if default is not None else "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        error(f"Invalid number: {raw}")
        return None


def confirm(text: str) -> bool:
    return prompt(f"{text} (y/n)", "n").lower().startswith("y")


def pick_channel() -> int | None:
    """Let the user choose a channel, showing the LED on each."""
    print()
    for ch, led in LEDS.items():
        print(
            f"    {ch}) {led['name']}  —  {led['wavelength']}  "
            f"({led['band']}, max {led['max_ma']} mA)"
        )
    val = prompt_int("Channel", default=1)
    if val not in LEDS:
        error(f"Invalid channel: {val}")
        return None
    return val


def validate_current(channel: int, current_ma: int) -> bool:
    """Check current against the LED's datasheet limit.  Warn if high."""
    led = LEDS[channel]
    if current_ma < 0:
        error("Current cannot be negative.")
        return False
    if current_ma > led["max_ma"]:
        error(f"{current_ma} mA exceeds {led['name']} maximum of {led['max_ma']} mA!")
        return False
    if current_ma > HIGH_CURRENT_WARN_MA:
        warn(f"{current_ma} mA is above {HIGH_CURRENT_WARN_MA} mA.")
        if not confirm("Continue?"):
            return False
    return True


# ═══════════════════════════════════════
#  Menu actions
# ═══════════════════════════════════════


def do_diagnostics(led: MightexSLC) -> None:
    """Print device info and status of all channels."""
    banner("Diagnostics")

    dev = led.get_device_info()
    print(f"  Model:    {dev.module_number}")
    print(f"  Firmware: {dev.firmware_version}")
    print(f"  Serial:   {dev.serial_number}")
    print()

    for ch, spec in LEDS.items():
        mode = led.get_mode(ch)
        max_ma, set_ma = led.get_normal_params(ch)
        try:
            voltage_mv = led.get_load_voltage(ch)
            voltage_str = f"{voltage_mv} mV"
        except MightexError:
            voltage_str = "N/A"

        if mode != Mode.DISABLE:
            status = f"{C.GREEN}ON {mode.name}{C.RESET}"
        else:
            status = f"{C.DIM}OFF{C.RESET}"

        print(
            f"  CH{ch} {spec['name']:8s} ({spec['wavelength']:>7s}): "
            f"{status:>20s}   Imax={max_ma:4d} mA   Iset={set_ma:4d} mA   "
            f"Vload={voltage_str}"
        )


def do_quick_test(led: MightexSLC) -> None:
    """Turn on one channel briefly at a safe current."""
    banner("Quick Test")

    ch = pick_channel()
    if ch is None:
        return
    spec = LEDS[ch]
    current = min(SAFE_DEFAULT_MA, spec["max_ma"])

    print(f"\n  Will turn on CH{ch} ({spec['name']}) at {current} mA for 3 seconds.")
    if not confirm("Proceed?"):
        return

    try:
        led.enable_channel(ch, current_ma=current, max_current_ma=spec["max_ma"])
        info(f"CH{ch} ON — {current} mA")

        for i in range(3, 0, -1):
            print(f"    {i}...", end=" ", flush=True)
            time.sleep(1)
        print()

        led.disable_channel(ch)
        info(f"CH{ch} OFF")
    except MightexError as exc:
        error(f"Failed: {exc}")


def do_normal_mode(led: MightexSLC) -> None:
    """Set a channel to a constant current, with optional ramp."""
    banner("Normal Mode")

    ch = pick_channel()
    if ch is None:
        return
    spec = LEDS[ch]

    print(f"\n  {spec['name']} — max {spec['max_ma']} mA")

    current = prompt_int("Set current (mA)", default=SAFE_DEFAULT_MA)
    if current is None or not validate_current(ch, current):
        return

    try:
        led.enable_channel(ch, current_ma=current, max_current_ma=spec["max_ma"])
        info(f"CH{ch} ON — {current} mA")
    except MightexError as exc:
        error(f"Failed: {exc}")
        return

    # Offer ramp option
    if confirm("Run a current ramp?"):
        start = prompt_int("Ramp start (mA)", default=10)
        end = prompt_int("Ramp end (mA)", default=min(300, spec["max_ma"]))
        steps = prompt_int("Number of steps", default=5)
        dwell = prompt_int("Dwell per step (seconds)", default=2)

        if start is None or end is None or steps is None or dwell is None:
            error("Invalid ramp parameters.")
        elif steps < 2:
            error("Need at least 2 steps for a ramp.")
        elif not validate_current(ch, end):
            pass
        else:
            step_size = (end - start) / (steps - 1)
            print()
            for i in range(steps):
                ma = int(start + step_size * i)
                ma = max(0, min(ma, spec["max_ma"]))
                try:
                    led.set_current(ch, ma)
                    info(f"Step {i + 1}/{steps}: {ma} mA")
                    time.sleep(dwell)
                except MightexError as exc:
                    error(f"Ramp failed at {ma} mA: {exc}")
                    break

    # Read back
    mode = led.get_mode(ch)
    max_ma, set_ma = led.get_normal_params(ch)
    print(f"\n  Readback — Mode: {mode.name}, Imax: {max_ma} mA, Iset: {set_ma} mA")

    if confirm("Turn off channel?"):
        led.disable_channel(ch)
        info(f"CH{ch} OFF")
    else:
        warn(f"CH{ch} left ON at {set_ma} mA — remember to turn it off!")


def do_strobe_mode(led: MightexSLC) -> None:
    """Configure and run a strobe profile on a channel."""
    banner("Strobe Mode")

    ch = pick_channel()
    if ch is None:
        return
    spec = LEDS[ch]

    print(f"\n  {spec['name']} — max {spec['max_ma']} mA (pulsed max 3500 mA, but LED-limited)")
    print(f"  {C.DIM}Strobe plays a sequence of current/duration steps in a loop.{C.RESET}")

    # Keep strobe current within LED rating even though SLC allows 3500 mA
    max_strobe = spec["max_ma"]

    on_current = prompt_int("ON current (mA)", default=min(200, max_strobe))
    if on_current is None or not validate_current(ch, on_current):
        return

    on_duration = prompt_int("ON duration (µs)", default=50_000)
    off_duration = prompt_int("OFF duration (µs)", default=50_000)
    repeats = prompt_int("Repeat count (0 = infinite)", default=10)

    if on_duration is None or off_duration is None or repeats is None:
        error("Invalid strobe parameters.")
        return

    print(
        f"\n  Profile: {on_current} mA for {on_duration} µs ON, "
        f"0 mA for {off_duration} µs OFF, ×{repeats}"
    )
    if not confirm("Start strobe?"):
        return

    try:
        led.set_strobe_params(ch, max_current_ma=max_strobe, repeat=repeats)
        led.set_strobe_step(ch, step=0, current_ma=on_current, duration_us=on_duration)
        led.set_strobe_step(ch, step=1, current_ma=0, duration_us=off_duration)
        led.set_strobe_step(ch, step=2, current_ma=0, duration_us=0)  # end marker

        led.set_mode(ch, Mode.STROBE)
        info("Strobe running!")

        if repeats == 0:
            print(f"  {C.DIM}Press Enter to stop...{C.RESET}")
            input()
        else:
            total_us = (on_duration + off_duration) * repeats
            total_s = total_us / 1_000_000
            print(f"  {C.DIM}Estimated duration: {total_s:.2f}s — waiting...{C.RESET}")
            time.sleep(total_s + 0.5)

        led.disable_channel(ch)
        info(f"CH{ch} OFF — strobe complete")

    except MightexError as exc:
        error(f"Strobe failed: {exc}")
        with suppress(MightexError):
            led.disable_channel(ch)


def do_multi_channel(led: MightexSLC) -> None:
    """Enable multiple channels simultaneously."""
    banner("Multi-Channel")

    print("\n  Select channels to enable:")
    for ch, spec in LEDS.items():
        print(f"    CH{ch}: {spec['name']} ({spec['wavelength']})")

    raw = prompt("Channels (comma-separated, e.g. 1,3)", default="1,2")
    try:
        channels = [int(x.strip()) for x in raw.split(",")]
    except ValueError:
        error("Invalid channel list.")
        return

    for ch in channels:
        if ch not in LEDS:
            error(f"Invalid channel: {ch}")
            return

    # Get current for each channel
    currents: dict[int, int] = {}
    for ch in channels:
        spec = LEDS[ch]
        ma = prompt_int(f"  CH{ch} ({spec['name']}) current (mA)", default=SAFE_DEFAULT_MA)
        if ma is None or not validate_current(ch, ma):
            return
        currents[ch] = ma

    print()
    for ch, ma in currents.items():
        print(f"    CH{ch} {LEDS[ch]['name']}: {ma} mA")
    if not confirm("Enable all?"):
        return

    # Enable
    try:
        for ch, ma in currents.items():
            spec = LEDS[ch]
            led.enable_channel(ch, current_ma=ma, max_current_ma=spec["max_ma"])
            info(f"CH{ch} ({spec['name']}) ON — {ma} mA")

        print(f"\n  {C.DIM}Press Enter to turn all off...{C.RESET}")
        input()

    except MightexError as exc:
        error(f"Failed: {exc}")
    finally:
        for ch in channels:
            with suppress(MightexError):
                led.disable_channel(ch)
                info(f"CH{ch} OFF")


def do_all_off(led: MightexSLC) -> None:
    """Safety: disable all channels."""
    for ch in LEDS:
        with suppress(MightexError):
            led.disable_channel(ch)
    info("All channels disabled.")


# ═══════════════════════════════════════
#  Main loop
# ═══════════════════════════════════════

MENU = [
    ("1", "Quick Test", "Turn on one LED briefly at a safe current"),
    ("2", "Normal Mode", "Set constant current with optional ramp"),
    ("3", "Strobe Mode", "Run a pulsed on/off profile"),
    ("4", "Multi-Channel", "Enable multiple LEDs simultaneously"),
    ("5", "Diagnostics", "Device info and channel status"),
    ("6", "All Off", "Disable all channels"),
    ("q", "Quit", "Turn off everything and exit"),
]

ACTIONS = {
    "1": do_quick_test,
    "2": do_normal_mode,
    "3": do_strobe_mode,
    "4": do_multi_channel,
    "5": do_diagnostics,
    "6": do_all_off,
}


def main_menu() -> None:
    line = "─" * 50
    print(f"\n{C.BOLD}  LED Test Menu{C.RESET}")
    print(f"  {C.DIM}{line}{C.RESET}")
    for key, label, desc in MENU:
        print(f"    {C.CYAN}{key}{C.RESET})  {label:16s} {C.DIM}— {desc}{C.RESET}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive LED test CLI for Mightex SLC")
    parser.add_argument(
        "--port",
        default="/dev/ttyUSB0",
        help="Serial port (default: /dev/ttyUSB0)",
    )
    args = parser.parse_args()

    banner("NIR LED Test Harness")
    print(f"  Mightex SLC Controller on {args.port}")
    print("  CH1: M850L3  (850 nm)   CH2: M940L3  (940 nm)   CH3: M1050L4 (1050 nm)")

    try:
        controller = MightexSLC(args.port)
        controller.connect()
        info(f"Connected to {args.port}")
    except MightexError as exc:
        error(f"Cannot connect: {exc}")
        sys.exit(1)

    # Show device info on startup
    try:
        dev = controller.get_device_info()
        print(f"  Device:   {dev.module_number} (FW {dev.firmware_version})")
    except MightexError:
        warn("Could not read device info")

    try:
        while True:
            main_menu()
            choice = prompt("Choice", "q").lower()

            if choice == "q":
                break

            action = ACTIONS.get(choice)
            if action:
                action(controller)
            else:
                error(f"Unknown option: {choice}")

    except KeyboardInterrupt:
        print(f"\n\n  {C.YELLOW}Interrupted!{C.RESET}")

    finally:
        # Safety: always turn everything off
        print()
        do_all_off(controller)
        controller.disconnect()
        info("Disconnected. Goodbye!")


if __name__ == "__main__":
    main()
