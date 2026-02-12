#!/usr/bin/env python3
"""
Example usage of the Mightex SLC controller module.

Demonstrates connecting, querying, and controlling LED channels.
"""

import sys
import time

# Add src to path so we can import without installing
sys.path.insert(0, "src")

from mightex_slc import get_controller


def main() -> None:
    """Run example LED control sequence."""
    print("Mightex SLC LED Controller — Example Usage")
    print("=" * 60)

    with get_controller("/dev/ttyUSB0") as led:
        # ── Device info ───────────────────────────────────────────
        info = led.get_device_info()
        print("\nConnected to:")
        print(f"  Model:     {info.module_number}")
        print(f"  Firmware:  {info.firmware_version}")
        print(f"  Serial:    {info.serial_number}")

        # ── Turn on channel 1 at 50 mA ───────────────────────────
        print(f"\n{'=' * 60}")
        print("1) Enable channel 1 at 50 mA")
        led.enable_channel(1, current_ma=50)
        print("   ✓ ON")
        time.sleep(2)

        # ── Change brightness ─────────────────────────────────────
        print(f"\n{'=' * 60}")
        print("2) Change brightness to 100 mA")
        led.set_current(1, 100)
        print("   ✓ Brightness updated")
        time.sleep(2)

        # ── Query status ──────────────────────────────────────────
        print(f"\n{'=' * 60}")
        print("3) Query channel status")
        mode = led.get_mode(1)
        max_ma, set_ma = led.get_normal_params(1)
        print(f"   Mode:        {mode.name}")
        print(f"   Max current: {max_ma} mA")
        print(f"   Set current: {set_ma} mA")
        time.sleep(2)

        # ── Turn off ──────────────────────────────────────────────
        print(f"\n{'=' * 60}")
        print("4) Disable channel 1")
        led.disable_channel(1)
        print("   ✓ OFF")

        print(f"\n{'=' * 60}")
        print("Done!  Use led.store_settings() to persist to NV memory.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
