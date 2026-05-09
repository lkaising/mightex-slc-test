# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Commands

```bash
pytest                                      # run unit tests (mock serial, no hardware)
pytest -m hardware                          # run hardware tests (real SLC on /dev/ttyUSB0)
pytest tests/test_controller.py::TestX::test_y   # single test
ruff check                                  # lint
ruff format                                 # format
```

The `pytest` default `addopts = "-m 'not hardware'"` (in `pyproject.toml`) excludes hardware tests; opt in with `-m hardware`.

Scripts are run directly without installing the package — they prepend `src/` to `sys.path`:

```bash
python scripts/program_trigger.py [--config FILE] [--verify-only] [--no-store] [--interactive]
python scripts/led_test_cli.py [--port /dev/ttyUSB1]
```

## Architecture

Four-layer stack — each layer talks only to the one below it. Validation happens at the highest layer it can: the protocol layer rejects bad arguments before they reach the device.

```
controller.py        MightexSLC — user-facing API, context manager
protocol.py          SLCProtocol — command building, ack checks, response parsing
transport.py         SerialTransport — raw serial I/O, framing, timeouts
exceptions.py        MightexError hierarchy
constants.py         single source of truth for limits & defaults
```

`trigger_programmer.py` sits *beside* the controller (not above it) and provides reusable YAML-config-driven trigger-follower programming. Both `scripts/program_trigger.py` and any future system-integration code import from it. Verification compares against the public API — `MightexSLC.get_mode`, `get_trigger_params`, `get_trigger_profile` — so do not introduce `controller._p` access here.

`scripts/_cli_ui.py` is a small shared module for the interactive scripts (color codes, `ok`/`fail`/`warn`/`info`, `banner`, `prompt`, `confirm`). It's underscore-prefixed because it's internal to `scripts/` — not part of the public package. Both `program_trigger.py` and `led_test_cli.py` import from it; do not redefine these helpers per script.

### Protocol contract (matters for any change to transport or protocol)

- **Outbound framing:** commands are appended with `\n\r` (LF+CR). **Response terminator:** `\r`.
- **Ack codes:** `##` = success, `#data` = success with data, `#!` = device error, `#?` = invalid argument, `"is not defined"` = unknown command. `_check_ack` and `_expect_ack` in `protocol.py` enforce this.
- `ECHOOFF` is the one command that does *not* ack — `SLCProtocol.echo_off()` deliberately bypasses `_cmd_ack`. `MightexSLC.connect()` calls it once on every open.
- `SerialTransport.send()` does `reset_input_buffer → write → read_until(\r) → drain` — the small drain (`_DRAIN_DELAY_S`) catches bytes that arrive just after the terminator.

### Mode-specific current limits (datasheet, enforced in `protocol.py`)

| Mode | Max | Constant |
|---|---|---|
| NORMAL  | 1000 mA | `MAX_CURRENT_NORMAL_MA` |
| STROBE  | 3500 mA | `MAX_CURRENT_PULSED_MA` |
| TRIGGER | 3500 mA | `MAX_CURRENT_PULSED_MA` |

`enable_channel()` defaults `max_current_ma` to 1000 mA. Pass a lower value to match the LED's rating.

### Trigger-follower mode (the primary use case for this project)

`FOLLOWER_DURATION_US = 9999` is a special `Tset` value: the LED output **follows the trigger input level** (ON while HIGH, OFF while LOW) instead of pulsing for a fixed duration. `MightexSLC.set_trigger_follower()` runs the full safe 5-command sequence — disable → `TRIGGER` → `TRIGP` step 0 (with `9999`) → `TRIGP` terminator → arm `MODE 3`. Always use this method instead of issuing the commands individually.

## Testing

`tests/conftest.py` provides a `FakeSerial` that implements the pyserial subset used by `SerialTransport` (`write`, `read`, `read_until`, `in_waiting`, `flush`, `reset_input_buffer`, `close`, `is_open`). By default every command gets `##\n\r`; `fake_serial.set_response("...")` stages a custom response for the **next** command only — multi-command methods like `enable_channel` work without per-command setup. The response buffer refreshes on each `write()` call.

Tests organize by layer: transport I/O, protocol parsing/validation, controller convenience methods, and trigger programmer (YAML loading + `program_all`/`verify_all` flows).

## Notable conventions

- `constants.py` is the canonical source of limits and defaults — import from there, do not redefine.
- Channel numbers are 1-based (1–4).
- Current units are mA for SA/AA/MA/CA/HA/HV modules (this project's hardware is SLC-SA04).
