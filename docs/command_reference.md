# Mightex SLC Command Reference

Quick reference for RS232 commands. For Python API, see README.md.

## Connection Settings

- **Port:** `/dev/ttyUSB0` (or `/dev/ttyUSB1`, etc.)
- **Baud Rate:** 9600
- **Parameters:** 8N1 (8 data bits, No parity, 1 stop bit)
- **Termination:** All commands end with `\n\r` (LF+CR, hex: 0A 0D)

## Response Codes

| Response | Meaning |
|----------|---------|
| `##` | Command successful |
| `#!` | Command executed but error occurred |
| `#?` | Invalid argument/parameter |
| `#data` | Command successful with data response |
| `xxxx is not defined` | Invalid command |

## Current Limits (per datasheet)

| Mode | Max Current | Notes |
|------|------------|-------|
| **NORMAL** (constant-current) | 1000 mA | Applies to `NORMAL` Imax/Iset and `CURRENT` Iset |
| **STROBE** (pulsed) | 3500 mA | Applies to `STROBE` Imax and `STRP` step Iset |
| **TRIGGER** (pulsed) | 3500 mA | Applies to `TRIGGER` Imax and `TRIGP` step Iset |

The Python API validates against these limits before sending commands to the device.

## Essential Commands

### Echo Control

```
ECHOOFF          Turn off echo (recommended for scripts)
ECHOON           Turn on echo (useful for manual testing)
```

### Device Information

```
DEVICEINFO       Returns: Model, firmware version, serial number
```

Example response:
```
Mightex LED Driver:3.1.8 Device Module No.:SLC-SA04-U/S Device Serial No.:04-251013-011
```

### Mode Control

```
?MODE CHLno             Query current mode (returns: #mode)
MODE CHLno mode         Set mode
```

**Mode Values:**
- `0` = DISABLE (off)
- `1` = NORMAL (constant current, max 1000 mA)
- `2` = STROBE (programmed profile, max 3500 mA)
- `3` = TRIGGER (external trigger, max 3500 mA)

**Examples:**
```
?MODE 1                 Query mode of channel 1
MODE 1 1                Set channel 1 to NORMAL mode
MODE 1 0                Disable channel 1
```

### Normal Mode (Constant Current)

Max current: **1000 mA**

```
NORMAL CHLno Imax Iset     Set normal mode parameters (mA)
CURRENT CHLno Iset         Quick set current (mA)
?CURRENT CHLno             Query parameters
```

**Examples:**
```
NORMAL 1 100 50         Set channel 1: Imax=100mA, Iset=50mA
CURRENT 1 75            Change channel 1 current to 75mA
?CURRENT 1              Query channel 1 parameters
```

Response format for `?CURRENT`:
```
#Cal1 Cal2 Imax Iset ...
```
(Ignore Cal1 and Cal2, use Imax and Iset values)

### Strobe Mode (Timed Profiles)

Max current: **3500 mA**

```
STROBE CHLno Imax Repeat       Set strobe parameters
STRP CHLno STPno Iset Tset     Set profile step
?STROBE CHLno                  Query strobe parameters
?STRP CHLno                    Query profile
```

**Examples:**
```
STROBE 1 100 5              Imax=100mA, repeat 5 times
STRP 1 0 50 2000            Step 0: 50mA for 2000μs
STRP 1 1 10 100000          Step 1: 10mA for 100000μs
STRP 1 2 0 0                Step 2: End marker
MODE 1 2                    Start strobe on channel 1
```

### Trigger Mode (External Trigger)

Max current: **3500 mA**

```
TRIGGER CHLno Imax Polarity    Set trigger parameters
TRIGP CHLno STPno Iset Tset    Set trigger profile step
?TRIGGER CHLno                 Query trigger parameters
?TRIGP CHLno                   Query trigger profile
```

**Polarity:**
- `0` = Rising edge trigger
- `1` = Falling edge trigger

**Examples:**
```
TRIGGER 1 100 0            Imax=100mA, rising edge
TRIGP 1 0 50 2000          Step 0: 50mA for 2000μs
TRIGP 1 1 0 0              Step 1: End marker
MODE 1 3                   Enable trigger mode
```

### System Commands

```
STORE                Save current settings to non-volatile memory
RESET                Soft reset device
RESTOREDEF           Restore factory defaults
LoadVoltage CHLno    Get load voltage (returns: #CHLno:vvvvv in mV)
```

## Channel Numbering

- Channels are **1-based**: Channel 1 = `1`, Channel 2 = `2`, etc.
- SLC-SA04 has 4 channels (1-4)

## Current Units

- **SA/AA/MA/CA/HA/HV modules:** 1 mA resolution
  - Value `100` = 100 mA
- **FA/FV/XA/XV modules:** 0.1 mA resolution
  - Value `100` = 10.0 mA

## Quick Start Sequence

```bash
ECHOOFF              # Disable echo
DEVICEINFO           # Check device
NORMAL 1 100 50      # Set channel 1 params
MODE 1 1             # Enable channel 1
CURRENT 1 75         # Change brightness
MODE 1 0             # Turn off channel 1
```

## Common Workflows

### Turn on LED at specific brightness

```
NORMAL 1 200 100     Set Imax=200mA, Iset=100mA
MODE 1 1             Enable NORMAL mode
```

### Change brightness (must be in NORMAL mode)

```
CURRENT 1 150        Change to 150mA
```

### Turn off LED

```
MODE 1 0             Set to DISABLE mode
```

### Save settings permanently

```
STORE                Save to non-volatile memory
```
(Settings persist through power cycles)

## For More Information

- Full command documentation: See Mightex SDK manual pages 11-14
- Python API: See `src/mightex_slc/controller.py`
- Examples: See `scripts/example_usage.py`
