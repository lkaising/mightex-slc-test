#!/usr/bin/env python3
"""
Comprehensive test suite for Mightex SLC LED Controller

Run with: python tests/test_controller.py
"""

import sys

from mightex_slc import DeviceInfo, MightexSLC

PORT = "/dev/ttyUSB0"
SAFE_TEST_CURRENT = 10


def test_connection():
    """Test 1: Serial connection and ECHOOFF"""
    print("\n" + "=" * 60)
    print("Test 1: Serial Connection")
    print("=" * 60)

    with MightexSLC(PORT) as _led:
        print("✓ Serial port opened successfully")
        print("✓ ECHOOFF command sent")
        print("✓ Connection established")

    print("✓ Connection closed cleanly")
    return True


def test_device_info():
    """Test 2: Device information retrieval"""
    print("\n" + "=" * 60)
    print("Test 2: Device Information")
    print("=" * 60)

    with MightexSLC(PORT) as led:
        raw_response = led._send_command("DEVICEINFO")
        print(f"Raw DEVICEINFO response: {repr(raw_response)}")
        info = led.get_device_info()

        print(f"Firmware Version: {info.firmware_version}")
        print(f"Module Number:    {info.module_number}")
        print(f"Serial Number:    {info.serial_number}")

        # Validate
        assert "SLC" in info.module_number, f"Invalid module number: {info.module_number}"
        assert len(info.serial_number) > 0, "Missing serial number"
        assert len(info.firmware_version) > 0, "Missing firmware version"

        print("✓ Device info retrieved and validated")

    return True


def test_mode_query_and_control():
    """Test 3: Mode querying and control"""
    print("\n" + "=" * 60)
    print("Test 3: Mode Query and Control")
    print("=" * 60)

    with MightexSLC(PORT) as led:
        # Test channel 1
        channel = 1

        # Query current mode
        current_mode = led.get_mode(channel)
        mode_names = {0: "DISABLE", 1: "NORMAL", 2: "STROBE", 3: "TRIGGER"}
        print(f"Current mode for channel {channel}: {mode_names[current_mode]}")

        # Set to DISABLE
        assert led.set_mode(channel, MightexSLC.MODE_DISABLE), "Failed to set DISABLE mode"
        mode = led.get_mode(channel)
        assert mode == MightexSLC.MODE_DISABLE, "Mode not set to DISABLE"
        print(f"✓ Set channel {channel} to DISABLE mode")

        # Set to NORMAL
        assert led.set_mode(channel, MightexSLC.MODE_NORMAL), "Failed to set NORMAL mode"
        mode = led.get_mode(channel)
        assert mode == MightexSLC.MODE_NORMAL, "Mode not set to NORMAL"
        print(f"✓ Set channel {channel} to NORMAL mode")

        # Return to DISABLE
        led.set_mode(channel, MightexSLC.MODE_DISABLE)
        print(f"✓ Returned channel {channel} to DISABLE mode")

    return True


def test_normal_mode_parameters():
    """Test 4: Normal mode parameter setting"""
    print("\n" + "=" * 60)
    print("Test 4: Normal Mode Parameters")
    print("=" * 60)

    import time

    with MightexSLC(PORT) as led:
        channel = 1
        test_max = 100  # mA
        test_set = SAFE_TEST_CURRENT  # mA

        # Set normal mode parameters
        assert led.set_normal_mode(channel, test_max, test_set), "Failed to set normal mode params"
        print(f"✓ Set channel {channel}: Imax={test_max}mA, Iset={test_set}mA")

        # Give device time to apply settings
        time.sleep(0.3)

        # Query and verify
        max_current, set_current = led.get_normal_params(channel)
        print(f"  Read back: Imax={max_current}mA, Iset={set_current}mA")

        assert max_current == test_max, f"Max current mismatch: {max_current} != {test_max}"
        assert set_current == test_set, f"Set current mismatch: {set_current} != {test_set}"
        print("✓ Parameters verified")

    return True


def test_current_control():
    """Test 5: Current setting in NORMAL mode"""
    print("\n" + "=" * 60)
    print("Test 5: Current Control")
    print("=" * 60)

    import time

    with MightexSLC(PORT) as led:
        channel = 1

        # Setup: Set to normal mode
        led.set_normal_mode(channel, 100, SAFE_TEST_CURRENT)
        led.set_mode(channel, MightexSLC.MODE_NORMAL)
        print(f"✓ Channel {channel} in NORMAL mode at {SAFE_TEST_CURRENT}mA")

        # Change current
        new_current = 20  # mA
        assert led.set_current(channel, new_current), "Failed to set current"

        # Give device time to apply
        time.sleep(0.3)

        # Verify
        _, set_current = led.get_normal_params(channel)
        assert set_current == new_current, f"Current not updated: {set_current} != {new_current}"
        print(f"✓ Current changed to {new_current}mA and verified")

        # Cleanup: disable channel
        led.disable_channel(channel)
        print(f"✓ Channel {channel} disabled")

    return True


def test_enable_disable_convenience():
    """Test 6: Enable/disable convenience methods"""
    print("\n" + "=" * 60)
    print("Test 6: Enable/Disable Convenience Methods")
    print("=" * 60)

    with MightexSLC(PORT) as led:
        channel = 1

        # Enable with convenience method
        assert led.enable_channel(channel, SAFE_TEST_CURRENT), "Failed to enable channel"
        mode = led.get_mode(channel)
        assert mode == MightexSLC.MODE_NORMAL, "Channel not in NORMAL mode"
        print(f"✓ Channel {channel} enabled at {SAFE_TEST_CURRENT}mA")

        # Disable with convenience method
        assert led.disable_channel(channel), "Failed to disable channel"
        mode = led.get_mode(channel)
        assert mode == MightexSLC.MODE_DISABLE, "Channel not disabled"
        print(f"✓ Channel {channel} disabled")

    return True


def test_all_channels():
    """Test 7: Test all 4 channels"""
    print("\n" + "=" * 60)
    print("Test 7: All Channels Test")
    print("=" * 60)

    with MightexSLC(PORT) as led:
        # Test each channel
        for channel in range(1, 5):  # Channels 1-4
            # Set to disable
            assert led.disable_channel(channel), f"Failed to disable channel {channel}"
            mode = led.get_mode(channel)
            assert mode == MightexSLC.MODE_DISABLE, f"Channel {channel} not disabled"
            print(f"✓ Channel {channel}: DISABLE mode verified")

            # Set parameters
            assert led.set_normal_mode(channel, 100, SAFE_TEST_CURRENT), (
                f"Failed to set params for channel {channel}"
            )
            print(f"✓ Channel {channel}: Normal mode parameters set")

        print("✓ All 4 channels tested successfully")

    return True


def test_device_info_parsing():
    """Test 8: DeviceInfo parsing"""
    print("\n" + "=" * 60)
    print("Test 8: DeviceInfo Parsing")
    print("=" * 60)

    # Test with actual device response format
    test_response = (
        "Mightex LED Driver:3.1.8 Device Module No.:SLC-SA04-U/S Device Serial No.:04-251013-011"
    )
    info = DeviceInfo.from_response(test_response)

    print(f"Parsed firmware: {info.firmware_version}")
    print(f"Parsed module: {info.module_number}")
    print(f"Parsed serial: {info.serial_number}")

    assert info.firmware_version == "3.1.8", (
        f"Firmware version parsing failed: got '{info.firmware_version}'"
    )
    assert info.module_number == "SLC-SA04-U/S", (
        f"Module number parsing failed: got '{info.module_number}'"
    )
    assert info.serial_number == "04-251013-011", (
        f"Serial number parsing failed: got '{info.serial_number}'"
    )

    print("✓ DeviceInfo parsing validated")
    return True


def run_all_tests():
    """Run all tests in sequence"""
    print("\n" + "=" * 60)
    print("MIGHTEX SLC LED CONTROLLER - TEST SUITE")
    print("=" * 60)
    print(f"Testing on port: {PORT}")
    print(f"Safe test current: {SAFE_TEST_CURRENT}mA")

    tests = [
        ("Connection", test_connection),
        ("Device Info", test_device_info),
        ("Mode Control", test_mode_query_and_control),
        ("Normal Parameters", test_normal_mode_parameters),
        ("Current Control", test_current_control),
        ("Enable/Disable", test_enable_disable_convenience),
        ("All Channels", test_all_channels),
        ("DeviceInfo Parsing", test_device_info_parsing),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"\n✗ TEST FAILED: {name}")
            print(f"  Error: {e}")
            failed += 1
        except Exception as e:
            print(f"\n✗ TEST ERROR: {name}")
            print(f"  Exception: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")

    if failed == 0:
        print("\n✓ ALL TESTS PASSED!")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    try:
        exit_code = run_all_tests()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
