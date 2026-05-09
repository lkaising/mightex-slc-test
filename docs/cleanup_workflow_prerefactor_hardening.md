# Cleanup Workflow — Pre-Refactor Hardening

**Context.** Before splitting `mightex_slc` into smaller modules, harden the public API surface and the test harness so the refactor lands on a clean floor. This document defines four sequential agent phases.

**Hard rule.** Phases run **strictly in order**, each on a clean working tree, each with its own commit. An agent must not start a phase against an uncommitted previous phase.

**Out of scope for all four phases.** No source-module restructure, no behavioral changes to public methods (other than the bug fixes explicitly listed in Phase 3a), no new features.

---

## Phase 1 — Public API rename

**Agent count.** 1.
**Hardware required.** No.
**Type of change.** Breaking. Mechanical.

**Goal.** Eliminate redundant API and stop shadowing Python builtins.

**In scope.**
1. Delete `get_controller()` from [controller.py:265](src/mightex_slc/controller.py:265).
2. Rename exceptions:
   - `mightex_slc.exceptions.ConnectionError` → `MightexConnectionError`
   - `mightex_slc.exceptions.TimeoutError` → `MightexTimeoutError`
3. Drop both `# noqa: A001` markers from [exceptions.py](src/mightex_slc/exceptions.py).
4. Propagate the renames and removal everywhere they are referenced.

**Files touched (verified).**
- [src/mightex_slc/exceptions.py](src/mightex_slc/exceptions.py)
- [src/mightex_slc/__init__.py](src/mightex_slc/__init__.py) — exports + `__all__`
- [src/mightex_slc/controller.py](src/mightex_slc/controller.py) — line 10 docstring, line 97 lazy import, line 265 definition
- [src/mightex_slc/transport.py](src/mightex_slc/transport.py) — line 21 import, lines 77/138 raise sites, lines 61/114/115 docstring `Raises:` blocks, line 129
- [src/mightex_slc/trigger_programmer.py](src/mightex_slc/trigger_programmer.py) — module docstring example at line 11
- [scripts/example_usage.py](scripts/example_usage.py)
- [tests/test_controller.py](tests/test_controller.py) — imports + `pytest.raises` matchers
- [README.md](README.md) — examples and error table at lines 106, 159, 164, 166, 235, 236

**Out of scope.** No deprecation shim. No `_LegacyConnectionError = MightexConnectionError` re-export. Clean break.

**Acceptance criteria.**
- `pytest` green.
- `ruff check` green.
- `grep -rn "get_controller\|^class ConnectionError\|^class TimeoutError" src tests scripts` returns nothing meaningful.
- `from mightex_slc import ConnectionError` fails with `ImportError`.
- `PKG-INFO` is auto-generated; ignore.

---

## Phase 2 — Test reorganization

**Agent count.** 1.
**Hardware required.** No.
**Depends on.** Phase 1 committed.
**Type of change.** Test-only. No production code touched.

**Goal.** Tests describe behavior by source layer and stop patching private internals.

**In scope.**
1. Add a multi-response staging mechanism to `FakeSerial` (e.g. `queue_responses([...])` consumed one per `write`).
2. Delete `_stub_queries` from [tests/test_trigger_programmer.py:435](tests/test_trigger_programmer.py:435) and rewrite verification tests to use the queueing fake.
3. Split tests into 5 files:
   ```
   tests/
     conftest.py
     test_transport.py
     test_protocol.py            ← validation + ack + parsing + commands
     test_controller.py
     test_trigger_programmer.py  ← config + workflow
     test_hardware.py            ← @pytest.mark.hardware only
   ```
4. Rename vague tests to behavior-focused names (the folded-in 3c). Examples:
   - `test_success` → `test_program_channel_sends_full_follower_sequence`
   - `test_passes_when_correct` → `test_verify_channel_passes_when_mode_imax_and_step_match`

**Out of scope.**
- Do not move `FakeSerial` into a separate `fakes.py`. Keep in `conftest.py`.
- Do not introduce a separate `FakeTransport` abstraction.
- Do not add new test cases for new behavior — that's Phase 3a.
- Do not delete tests that currently exist; only rename and relocate.

**Acceptance criteria.**
- `pytest` green.
- Same behavioral coverage; no intentional deletions. Test count is a useful guardrail — significant drops should be justified in the commit message (e.g. legitimate parametrization collapsing N tests into one).
- `grep -rn "_transport\.\|protocol\._cmd\|patch.object.*_transport" tests` returns nothing.
- Each test file's name matches the source module under test.

---

## Phase 3a — Latent bug fixes (no hardware needed)

**Agent count.** 1.
**Hardware required.** No.
**Depends on.** Phase 2 committed.
**Type of change.** Production fixes + new tests.

**Goal.** Fix two correctness bugs surfaced during review.

**In scope.**

**Bug A — `connect()` does not roll back on partial failure.** [controller.py:65-74](src/mightex_slc/controller.py:65). If `echo_off()` raises, the serial port is left open and `_proto` is set. Wrap the post-`open()` work so any exception triggers `self._transport.close()` and `self._proto = None`, then re-raise.

**Bug B — `set_trigger_params` does not validate polarity.** [protocol.py:333-346](src/mightex_slc/protocol.py:333). An invalid integer polarity passes straight to the wire. Add a `_validate_polarity` helper (mirrors `_validate_mode`) and call it before sending.

**Tests to add.**
- `connect()` rollback: simulate `echo_off` failure via the queueing fake; assert port is closed and a fresh `connect()` attempt works.
- Polarity validation: `set_trigger_params(1, 100, polarity=99)` raises `ValidationError`; valid `TriggerPolarity` values still pass.

**Out of scope.**
- ECHOOFF investigation. That is Phase 3b.
- Any other validation gap.

**Acceptance criteria.**
- `pytest` green with new tests.
- Both fixes have at least one failing-without-fix test demonstrating the bug.

---

## Phase 3b — ECHOOFF behavior (hardware required)

**Agent count.** 1.
**Hardware required.** **Yes.** Real SLC controller on `/dev/ttyUSB0` (or platform equivalent).
**Depends on.** Phase 3a committed.
**Status.** **Held until hardware access.**

**Goal.** Resolve the inconsistency between [protocol.py:392](src/mightex_slc/protocol.py:392) ("the controller does not ack ECHOOFF") and [transport.py:128-129](src/mightex_slc/transport.py:128) (raises `TimeoutError` on empty response).

**Investigation step (must run first, on hardware).**
- Send `ECHOOFF` via a one-off script with logging at DEBUG.
- Capture the raw bytes returned, if any.
- Determine the actual device behavior: silent, `##` ack, command echo, or other.

**Possible outcomes and their fixes.**
- *Device returns nothing.* Add a no-response code path on the transport (`send_no_response(cmd)` or a `expect_response: bool` parameter). Update `echo_off` to use it.
- *Device echoes the command.* Existing code is fine; update the comment to say "device echoes the command, no ack".
- *Device returns `##`.* Switch `echo_off` to `_cmd_ack` and delete the special-case comment.

**Tests to add.**
- A unit test exercising whichever path is chosen, using the queueing fake.
- An optional `@pytest.mark.hardware` test that verifies real-device behavior.

**Acceptance criteria.**
- `pytest` green.
- `pytest -m hardware` green on the connected device.
- The comment at [protocol.py:392](src/mightex_slc/protocol.py:392) accurately describes the device's behavior.

---

## Sequencing summary

| # | Phase | Hardware | Depends on | Run when |
|---|-------|----------|------------|----------|
| 1 | API rename | No | — | Now |
| 2 | Test reorg + queueing fake + renames | No | Phase 1 | Now, after Phase 1 commits |
| 3a | `connect()` rollback + polarity validation | No | Phase 2 | Now, after Phase 2 commits |
| 3b | ECHOOFF investigation + fix | **Yes** | Phase 3a | When hardware is available |

After all four land, the codebase is ready for the larger module-restructure refactor.

---

### Prompt 1 — Phase 1: API rename

~~~text
Phase 1 — Remove `get_controller` and rename exceptions

Context. You are working in the `mightex-slc-test` repo, a Python package for controlling Mightex SLC LED drivers via RS232. The package source is at `src/mightex_slc/`. This is preparatory cleanup before a larger module restructure — keep changes mechanical, do not refactor anything else.

Pre-check. Run `git status`. The working tree must be clean before you start. If it is not, stop and report.

Goal. Two breaking API changes.

1. Remove the redundant `get_controller()` factory. Callers should use `MightexSLC(...)` directly.

2. Rename two exception classes to stop shadowing Python builtins:
   - `mightex_slc.exceptions.ConnectionError` → `MightexConnectionError`
   - `mightex_slc.exceptions.TimeoutError` → `MightexTimeoutError`
   Both currently carry `# noqa: A001` markers; remove the markers after renaming.

Why. `get_controller` is a one-line wrapper around `MightexSLC(port)` — two ways to do the same thing. The exception names shadow builtins inside `transport.py`, which imports them via `from .exceptions import ConnectionError, TimeoutError`. Inside that module `except ConnectionError:` catches only Mightex errors and silently misses `OSError` subclasses — a real footgun.

Files to update (verified by prior grep). Paths relative to repo root:
- src/mightex_slc/exceptions.py — rename two classes, drop both `# noqa: A001`
- src/mightex_slc/__init__.py — exports + `__all__`
- src/mightex_slc/controller.py — module docstring example near line 10, lazy import near line 97, delete `get_controller` definition near line 265
- src/mightex_slc/transport.py — import statement, `raise` sites, docstring `Raises:` blocks
- src/mightex_slc/trigger_programmer.py — module docstring example mentions `get_controller`
- scripts/example_usage.py — uses `get_controller`
- tests/test_controller.py — imports + `pytest.raises(ConnectionError, ...)` matchers
- README.md — code examples and the error table (rows for `ConnectionError` / `TimeoutError`)

Ignore `src/mightex_slc_test.egg-info/PKG-INFO` — it is auto-generated.

Out of scope. No deprecation shim, no re-export aliases, no other refactoring. Clean break.

Acceptance criteria (must all hold).
- `pytest` is green.
- `ruff check` is green.
- `grep -rn "get_controller" src tests scripts README.md` returns no matches.
- `grep -rn "^class ConnectionError\|^class TimeoutError" src` returns no matches.
- `python -c "from mightex_slc import ConnectionError"` raises ImportError.
- `python -c "from mightex_slc import MightexConnectionError, MightexTimeoutError"` succeeds.

When done. Single commit on the current branch with a message that flags the breaking change. Do NOT push. Report what you changed and the test/ruff output.
~~~

---

### Prompt 2 — Phase 2: Test reorganization

~~~text
Phase 2 — Reorganize tests, add queueing fake, rename vague tests

Pre-condition. Phase 1 (API rename) is complete and committed. Run `git status` first; if the working tree is not clean, stop and report. Run `git log -1 --oneline` and confirm the most recent commit is the Phase 1 rename — if not, stop.

Context. The repo is `mightex-slc-test`. Tests live in `tests/` and use a `FakeSerial` class defined in `tests/conftest.py`. Package source is `src/mightex_slc/`. Do NOT change production code in this phase.

Goal. Test-only improvements, in this order:

1. Add a multi-response queue to FakeSerial.
   `FakeSerial.set_response()` currently stages exactly ONE response, after which the fake returns to its `##\n\r` default. This is why `tests/test_trigger_programmer.py` defines `_stub_queries()` near line 435 — a helper that monkey-patches `controller._transport.send` to selectively intercept queries. That pattern pokes at private attributes and is fragile.
   Add a queueing API such as `fake_serial.queue_responses(["#3\n\r", "#1200 0\n\r", "#1200 9999 0 0\n\r"])` that consumes one entry per `write()`. The existing `set_response()` may stay (it is used widely) or you may unify them — your call. Document the new method with a short docstring.

2. Delete `_stub_queries` and rewrite affected tests.
   The verify-channel and verify-all tests in `tests/test_trigger_programmer.py` use it to stage three responses for the three `?MODE / ?TRIGGER / ?TRIGP` queries. Rewrite them with the new queueing fake.

3. Split tests into 5 files mirroring source layers.
   The existing `tests/test_controller.py` is already organized into Layer 1 (Transport), Layer 2 (Protocol), Layer 3 (Controller), and Hardware sections — those map almost 1:1 to the new files. Target layout:

       tests/
         conftest.py
         test_transport.py            (Layer 1)
         test_protocol.py             (Layer 2 — validation + ack + parsing + commands kept together)
         test_controller.py           (Layer 3 — user-facing API + set_trigger_follower)
         test_trigger_programmer.py   (config loading + program/verify workflow)
         test_hardware.py             (@pytest.mark.hardware only)

4. Rename vague tests to behavior-focused names. Examples:
   - `TestProgramChannel.test_success` → `test_program_channel_sends_full_follower_sequence`
   - `TestVerifyChannel.test_passes_when_correct` → `test_verify_channel_passes_when_mode_imax_and_step_match`
   Apply the same principle wherever a test name does not describe behavior.

Out of scope.
- Do NOT change anything in `src/`.
- Do NOT move `FakeSerial` into a separate `tests/fakes.py` — keep it in `conftest.py`.
- Do NOT introduce a `FakeTransport` abstraction.
- Do NOT add new test cases for new behavior — that is a later phase.
- Do NOT delete existing tests; only rename, relocate, or rewrite their setup.

Acceptance criteria.
- `pytest` is green.
- Same behavioral coverage; no intentional deletions. Test count is a useful guardrail — if a count drop is unavoidable (e.g. legitimate parametrization collapsing similar tests into one), justify it in the commit message.
- `grep -rn "_transport\.\|protocol\._cmd\|patch.object.*_transport" tests/` returns nothing.
- File names match the source modules they exercise.
- `ruff check` is green.

When done. Single commit on the current branch. Do NOT push. Report what moved where, the new fake API, and pytest output.
~~~

---

### Prompt 3 — Phase 3a: Bug fixes (no hardware)

~~~text
Phase 3a — Fix connect() rollback and add polarity validation

Pre-condition. Phase 2 (test reorganization) is complete and committed. Run `git status`; the working tree must be clean. The queueing FakeSerial helper from Phase 2 should exist in `tests/conftest.py`.

Context. Two latent bugs surfaced during a code review of `src/mightex_slc/`. Both are small, targeted fixes with new tests. For each bug, write the test FIRST, confirm it fails on the current code, then apply the fix and confirm it turns green.

Bug A — connect() does not roll back on partial failure.
Located at src/mightex_slc/controller.py:65-74:

    def connect(self) -> None:
        if self.is_connected:
            return
        self._transport.open()
        self._proto = SLCProtocol(self._transport)
        self._proto.echo_off()   # if this raises, port stays open & _proto leaks

If `echo_off()` raises, the caller sees an exception but the serial port is left open and `_proto` is set. A subsequent `connect()` short-circuits via `is_connected` and never re-runs initialization.

Fix. Wrap the post-open block in try/except. On failure: call `self._transport.close()`, set `self._proto = None`, then re-raise.

Test. Use the queueing FakeSerial to force `echo_off` to raise (e.g. by staging a response that triggers a CommandError, since the transport raises on empty responses). Assert: `connect()` raises; `is_connected` is False afterward; a follow-up `connect()` with healthy responses succeeds.

Bug B — set_trigger_params does not validate polarity.
Located at src/mightex_slc/protocol.py:333-346. The function validates channel and current but passes `polarity` straight to the wire as `int(polarity)`. Calling with `polarity=99` produces `TRIGGER 1 100 99` — invalid but unchecked.

Fix. Add a `_validate_polarity(polarity)` helper alongside `_validate_mode` in protocol.py, using the same pattern: try `TriggerPolarity(polarity)` and raise `ValidationError` on `ValueError`. Call it from `set_trigger_params` before sending.

Tests.
- `set_trigger_params(1, 100, polarity=99)` raises `ValidationError`.
- `set_trigger_params(1, 100, polarity=TriggerPolarity.RISING)` still succeeds.
- `set_trigger_params(1, 100, polarity=TriggerPolarity.FALLING)` still succeeds.

Out of scope.
- Do not investigate ECHOOFF protocol behavior — that's a separate phase that needs hardware.
- Do not add any other validation gap fixes; only polarity.
- Do not refactor `connect()` beyond the rollback fix.

Acceptance criteria.
- `pytest` green.
- Each fix has a corresponding test that demonstrably failed before the fix. Confirm by temporarily reverting each fix in turn and rerunning the new test.
- `ruff check` green.

When done. Single commit on the current branch. Do NOT push. Report the bugs fixed, the tests added, and explicit confirmation that each new test fails without its fix.
~~~

---

### Prompt 4 — Phase 3b: ECHOOFF (hardware required, hold until then)

~~~text
Phase 3b — Investigate and fix ECHOOFF behavior

Pre-condition. Phase 3a is complete and committed. A real Mightex SLC controller is connected (default `/dev/ttyUSB0` on Linux). Run `git status`; the working tree must be clean.

Context. There is a contradiction in the codebase that requires hardware to resolve.

- src/mightex_slc/protocol.py:390-393:

      def echo_off(self) -> None:
          """Disable command echo (recommended for programmatic use)."""
          # Intentionally bypasses _cmd_ack — the controller does not ack ECHOOFF
          self._tx.send("ECHOOFF")

- src/mightex_slc/transport.py:128-129 raises `TimeoutError` if `send()` gets an empty response.

If the device truly returns nothing, every `connect()` would raise `TimeoutError` against real hardware. Either the comment is wrong (device returns SOMETHING — most likely an echoed command, since echo is on initially), or this is a real bug. We need to find out.

Step 1 — Investigate (must run on hardware).
Write a small probe script at `scripts/probe_echooff.py`. Do NOT commit it. The script should:
1. Open the serial port directly with `serial.Serial(port, baudrate=9600, timeout=1.0)`.
2. Write `b"ECHOOFF\n\r"`.
3. Read bytes for ~1 second with verbose logging.
4. Print raw bytes captured (use `repr()` so non-printables are visible).

Run it against the device and capture the output. Report the exact bytes returned.

Step 2 — Fix based on findings. Pick the matching branch:

A) Device returns nothing.
   Add a no-response code path on `SerialTransport`, e.g. `send_no_response(cmd)` that writes and flushes but does not call `_read_response`. Switch `echo_off` to use it. Update the comment to describe actual behavior.

B) Device echoes the command (most likely — echo is initially on).
   Existing transport behavior already works: `_tx.send("ECHOOFF")` reads and discards the echo. Update the comment to read approximately: "ECHOOFF returns a command echo (since echo is initially on); we read and discard it. From this call onward the device runs in echo-off mode."

C) Device returns `##`.
   Switch `echo_off` to `_cmd_ack`. Delete the bypass comment.

Step 3 — Tests.
- Add a unit test using the queueing FakeSerial that exercises whichever path you took.
- If `tests/test_hardware.py` does not already cover `connect()` against a real device, add a `@pytest.mark.hardware` test that calls `connect()` and asserts no exception. If existing hardware coverage is sufficient, leave a brief comment in the test file noting that.

Out of scope.
- Do not refactor anything else in `transport.py` or `protocol.py`.
- Do not commit the probe script.

Acceptance criteria.
- `pytest` green.
- `pytest -m hardware` green on the connected device.
- The comment at protocol.py near line 392 accurately describes the actual device behavior, supported by the probe output captured in Step 1.
- `ruff check` green.

When done. Single commit on the current branch. Do NOT push. Report:
- The exact bytes the device returned to ECHOOFF.
- Which branch (A / B / C) you took and why.
- The test additions.
~~~
