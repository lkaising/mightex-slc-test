# Mightex SLC LED Controller

Python interface for controlling Mightex Sirius LED drivers via RS232.

Developed for use with NIR imaging systems at Rutgers Biomedical Engineering.

## Overview

This project provides a clean Python API for controlling Mightex SLC series LED controllers. It wraps the RS232 command protocol in an easy-to-use Python class with proper error handling and documentation.

**Tested with:** Mightex SLC-SA04-U/S (4-channel LED controller)

## Features

- ✅ Simple Python API for LED control
- ✅ Context manager support for automatic cleanup
- ✅ All 4 operating modes (DISABLE, NORMAL, STROBE, TRIGGER)
- ✅ Comprehensive test suite
- ✅ Well-documented with examples

## Project Structure

```
mightex-slc-test/
├── src/
│   └── mightex_slc/          # Main controller module
│       ├── __init__.py
│       └── controller.py
├── scripts/
│   └── example_usage.py      # Usage examples
├── tests/
│   └── test_controller.py    # Comprehensive tests
├── docs/
│   └── command_reference.md  # Low-level command reference
├── pyproject.toml            # Project dependencies
└── README.md                 # This file
```

## Installation

### 1. Clone/Setup Project

```bash
cd ~/Research
# (Project should already be at ~/Research/mightex-slc-test)
cd mightex-slc-test
```

### 2. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install pyserial
```

### 4. Setup Serial Port Permissions

Add your user to the `dialout` group for serial port access:

```bash
sudo usermod -aG dialout $USER
```

**Important:** Log out and log back in for this to take effect.

### 5. Verify Connection

Check that your device is connected:

```bash
ls -l /dev/ttyUSB*
```

Should show something like `/dev/ttyUSB0`

## Quick Start

### Using the Python API

```python
from mightex_slc import get_controller

# Connect to controller
with get_controller('/dev/ttyUSB0') as led:
    # Get device info
    info = led.get_device_info()
    print(f"Connected to: {info.module_number}")
    
    # Turn on channel 1 at 50mA
    led.enable_channel(1, current_ma=50)
    
    # Change brightness to 100mA
    led.set_current(1, 100)
    
    # Turn off
    led.disable_channel(1)
```

### Running the Example

```bash
python scripts/example_usage.py
```

### Running Tests

```bash
python tests/test_controller.py
```

All tests should pass if your device is connected properly.

## Usage Examples

### Example 1: Simple On/Off

```python
from mightex_slc import MightexSLC

with MightexSLC('/dev/ttyUSB0') as led:
    # Turn on at 50mA
    led.enable_channel(1, current_ma=50)
    
    # Turn off
    led.disable_channel(1)
```

### Example 2: Query Device Information

```python
from mightex_slc import MightexSLC

with MightexSLC('/dev/ttyUSB0') as led:
    info = led.get_device_info()
    print(f"Model: {info.module_number}")
    print(f"Firmware: {info.firmware_version}")
    print(f"Serial: {info.serial_number}")
```

### Example 3: Manual Mode Control

```python
from mightex_slc import MightexSLC

with MightexSLC('/dev/ttyUSB0') as led:
    # Set normal mode parameters
    led.set_normal_mode(channel=1, max_current_ma=200, set_current_ma=100)
    
    # Enable NORMAL mode
    led.set_mode(1, MightexSLC.MODE_NORMAL)
    
    # Query current mode
    mode = led.get_mode(1)
    print(f"Mode: {mode}")  # 1 = NORMAL
    
    # Disable
    led.set_mode(1, MightexSLC.MODE_DISABLE)
```

### Example 4: Save Settings to Non-Volatile Memory

```python
from mightex_slc import MightexSLC

with MightexSLC('/dev/ttyUSB0') as led:
    # Configure channels
    led.set_normal_mode(1, 200, 100)
    led.set_normal_mode(2, 200, 50)
    
    # Save to non-volatile memory (persists through power cycles)
    led.store_settings()
```

## API Reference

### MightexSLC Class

#### Connection Methods

- `connect()` - Open serial connection
- `disconnect()` - Close serial connection
- Context manager support: `with MightexSLC(port) as led:`

#### Information Methods

- `get_device_info()` → `DeviceInfo` - Get model, firmware, serial number
- `get_mode(channel)` → `int` - Get current operating mode (0-3)
- `get_normal_params(channel)` → `(max_ma, set_ma)` - Get normal mode parameters

#### Control Methods

- `set_mode(channel, mode)` - Set operating mode
- `enable_channel(channel, current_ma, max_current_ma=None)` - Turn on LED
- `disable_channel(channel)` - Turn off LED
- `set_normal_mode(channel, max_current_ma, set_current_ma)` - Set normal mode params
- `set_current(channel, current_ma)` - Change brightness (must be in NORMAL mode)

#### System Methods

- `store_settings()` - Save to non-volatile memory
- `reset()` - Soft reset device

#### Operating Modes

- `MODE_DISABLE = 0` - LED off
- `MODE_NORMAL = 1` - Constant current
- `MODE_STROBE = 2` - Programmed profile
- `MODE_TRIGGER = 3` - External trigger

## Hardware Configuration

**RS232 Settings:**
- Baud rate: 9600
- Data bits: 8
- Parity: None
- Stop bits: 1
- Flow control: None

**DB9 Connector Pinout:**
- Pin 2: TXD
- Pin 3: RXD
- Pin 5: GND

## Troubleshooting

### Permission Denied Error

```bash
# Add user to dialout group
sudo usermod -aG dialout $USER

# Then log out and log back in
```

### Device Not Found

```bash
# Check USB connection
dmesg | grep tty

# List serial devices
ls -l /dev/ttyUSB*
```

### Communication Errors

1. Check baud rate (should be 9600)
2. Verify cable connection
3. Try different USB port
4. Check device power

## Advanced Usage

### Low-Level Command Access

For advanced users who need direct command access:

```python
with MightexSLC('/dev/ttyUSB0') as led:
    # Send raw command (advanced)
    response = led._send_command('DEVICEINFO')
    print(response)
```

See `docs/command_reference.md` for complete command documentation.

## Development

### Running Tests with Pytest

```bash
# Install dev dependencies
pip install pytest

# Run tests
pytest tests/
```

### Code Formatting

```bash
# Install ruff
pip install ruff

# Format code
ruff format src/ tests/ scripts/
```

## References

- Mightex SLC User Manual
- Mightex SDK Documentation v1.1.4
- Command reference: `docs/command_reference.md`

## License

This project is for research use at Rutgers University.

## Author

Logan Hallee  
PhD Student, Biomedical Engineering  
Rutgers University  
Yarmush Lab

## Acknowledgments

- Dr. Martin Yarmush (PI)
- Rutgers Biomedical Engineering Department
- NIH Biotechnology Training Program
