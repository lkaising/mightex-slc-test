#!/usr/bin/env python3
"""
Example usage of the Mightex SLC controller module

This script demonstrates:
- Connecting to the controller
- Getting device information
- Controlling LED channels
- Changing brightness
- Proper cleanup
"""

import sys
import time

# Add src to path so we can import mightex_slc
sys.path.insert(0, "src")

from mightex_slc import get_controller


def main():
    """Run example LED control sequence"""

    print("Mightex SLC LED Controller - Example Usage")
    print("=" * 60)

    # Use context manager for automatic connection/disconnection
    with get_controller("/dev/ttyUSB0") as led:
        # Get device information
        info = led.get_device_info()
        print("\nConnected to Device:")
        print(f"  Model:     {info.module_number}")
        print(f"  Firmware:  {info.firmware_version}")
        print(f"  Serial:    {info.serial_number}")

        # Example 1: Turn on channel 1 at 50mA
        print("\n" + "=" * 60)
        print("Example 1: Enable channel 1 at 50mA")
        led.enable_channel(1, current_ma=50)
        print("✓ Channel 1 ON at 50mA")

        time.sleep(2)

        # Example 2: Change brightness
        print("\n" + "=" * 60)
        print("Example 2: Change brightness to 100mA")
        led.set_current(1, 100)
        print("✓ Channel 1 brightness changed to 100mA")

        time.sleep(2)

        # Example 3: Query current mode and parameters
        print("\n" + "=" * 60)
        print("Example 3: Query channel status")
        mode = led.get_mode(1)
        mode_names = {0: "DISABLE", 1: "NORMAL", 2: "STROBE", 3: "TRIGGER"}
        print(f"  Mode: {mode_names[mode]}")

        max_current, set_current = led.get_normal_params(1)
        print(f"  Max Current: {max_current}mA")
        print(f"  Set Current: {set_current}mA")

        time.sleep(2)

        # Example 4: Turn off
        print("\n" + "=" * 60)
        print("Example 4: Disable channel 1")
        led.disable_channel(1)
        print("✓ Channel 1 OFF")

        print("\n" + "=" * 60)
        print("Example complete!")
        print("\nNote: Settings are in volatile memory.")
        print("Use led.store_settings() to save to non-volatile memory.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
