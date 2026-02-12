# Mightex SLC LED Controller

Python interface for controlling Mightex Sirius LED drivers via RS232.

Developed for use with NIR imaging systems at Rutgers Biomedical Engineering.

## Overview

This project provides a clean Python API for controlling Mightex SLC series LED controllers. It wraps the RS232 command protocol in an easy-to-use Python class with proper error handling, input validation, and logging.

**Tested with:** Mightex SLC-SA04-U/S (4-channel LED controller)

## Features

- ✅ Simple Python API for LED control
- ✅ Context manager support for automatic cleanup
- ✅ All 4 operating modes (DISABLE, NORMAL, STROBE, TRIGGER)
- ✅ Custom exception hierarchy for clear error handling
- ✅ Input validation with descriptive error messages
- ✅ `logging` integration for debugging
- ✅ Comprehensive test suite (runs without hardware via mock serial)

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
│   ├── conftest.py           # Shared fixtures (mock serial)
│   └── test_controller.py    # Unit + integration tests
├── docs/
│   └── command_reference.md  # Low-level RS232 command reference
├── pyproject.toml            # Project config & dependencies
└── README.md
```

## Installation

### 1. Clone / Setup Project

```bash
cd ~/Research/mightex-slc-test
```

### 2. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install pyserial

# For development/testing
pip install pytest ruff
```

### 4. Setup Serial Port Permissions

```bash
sudo usermod -aG dialout $USER
```

Log out and log back in for this to take effect.

### 5. Verify Connection

```bash
ls -l /dev/ttyUSB*
```

## Quick Start

```python
from mightex_slc import get_controller

with get_controller('/dev/ttyUSB0') as led:
    info = led.get_device_info()
    print(f"Connected to: {info.module_number}")

    led.enable_channel(1, current_ma=50)
    led.set_current(1, 100)
    led.disable_channel(1)
```

## Usage Examples

### Simple On/Off

```python
from mightex_slc import MightexSLC

with MightexSLC('/dev/ttyUSB0') as led:
    led.enable_channel(1, current_ma=50)
    led.disable_channel(1)
```

### Query Device Information

```python
from mightex_slc import MightexSLC

with MightexSLC('/dev/ttyUSB0') as led:
    info = led.get_device_info()
    print(f"Model: {info.module_number}")
    print(f"Firmware: {info.firmware_version}")
    print(f"Serial: {info.serial_number}")
```

### Mode Control with Enums

```python
from mightex_slc import MightexSLC, Mode

with MightexSLC('/dev/ttyUSB0') as led:
    led.set_normal_mode(channel=1, max_current_ma=200, set_current_ma=100)
    led.set_mode(1, Mode.NORMAL)

    mode = led.get_mode(1)
    print(f"Mode: {mode.name}")  # "NORMAL"

    led.set_mode(1, Mode.DISABLE)
```

### Error Handling

```python
from mightex_slc import MightexSLC, ConnectionError, ValidationError

try:
    with MightexSLC('/dev/ttyUSB0') as led:
        led.enable_channel(1, current_ma=50)
except ConnectionError as e:
    print(f"Cannot connect: {e}")
except ValidationError as e:
    print(f"Bad parameter: {e}")
```

### Strobe Mode

```python
from mightex_slc import MightexSLC, Mode

with MightexSLC('/dev/ttyUSB0') as led:
    led.set_strobe_params(1, max_current_ma=100, repeat=5)
    led.set_strobe_step(1, step=0, current_ma=50, duration_us=2000)
    led.set_strobe_step(1, step=1, current_ma=10, duration_us=100000)
    led.set_strobe_step(1, step=2, current_ma=0, duration_us=0)  # end marker
    led.set_mode(1, Mode.STROBE)
```

### Enable Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from mightex_slc import MightexSLC

with MightexSLC('/dev/ttyUSB0') as led:
    led.enable_channel(1, current_ma=50)  # TX/RX logged to console
```

## Testing

### Unit Tests (no hardware needed)

```bash
pytest
```

Unit tests use a mock serial port and run anywhere. All parsing, validation, command formatting, and error-handling paths are covered.

### Hardware Integration Tests

```bash
pytest -m hardware
```

These require a real SLC controller on `/dev/ttyUSB0`. They verify actual device communication, mode round-trips, and parameter persistence.

## API Reference

### Exceptions

All exceptions inherit from `MightexError`:

| Exception | When |
|---|---|
| `ConnectionError` | Serial port unavailable or closed |
| `CommandError` | Controller returns `#!`, `#?`, or undefined command |
| `ValidationError` | Invalid channel, current, or mode before sending |

### Mode Enum

```python
Mode.DISABLE  # 0 — LED off
Mode.NORMAL   # 1 — Constant current
Mode.STROBE   # 2 — Programmed profile
Mode.TRIGGER  # 3 — External trigger
```

### MightexSLC Methods

**Connection:** `connect()`, `disconnect()`, `is_connected` (property), context manager

**Information:** `get_device_info()`, `get_mode(channel)`, `get_normal_params(channel)`, `get_load_voltage(channel)`

**Normal mode:** `set_mode(channel, mode)`, `set_normal_mode(channel, max_ma, set_ma)`, `set_current(channel, ma)`

**Convenience:** `enable_channel(channel, current_ma, max_current_ma=None)`, `disable_channel(channel)`

**Strobe:** `set_strobe_params(channel, max_ma, repeat)`, `set_strobe_step(channel, step, ma, us)`

**Trigger:** `set_trigger_params(channel, max_ma, polarity)`, `set_trigger_step(channel, step, ma, us)`

**System:** `store_settings()`, `reset()`, `restore_defaults()`

## Hardware Configuration

**RS232 Settings:** 9600 baud, 8N1, no flow control

**DB9 Connector:** Pin 2 (TXD), Pin 3 (RXD), Pin 5 (GND)

## Troubleshooting

**Permission denied** — `sudo usermod -aG dialout $USER` then log out/in.

**Device not found** — `dmesg | grep tty` and `ls -l /dev/ttyUSB*`.

**Communication errors** — Check baud rate (9600), cable, USB port, and device power.

## References

- Mightex SLC User Manual
- Mightex SDK Documentation v1.1.4
- Command reference: `docs/command_reference.md`

## License

This project is for research use at Rutgers University.

## Author

Logan Kaising — PhD Student, Biomedical Engineering, Rutgers University (Yarmush Lab)

## Acknowledgments

- Dr. Martin Yarmush (PI)
- Rutgers Biomedical Engineering Department
- NIH Biotechnology Training Program
