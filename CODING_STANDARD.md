# Lowcost Radiosonde Research Project - Coding Standard

**Revision:** 1.0
**Applies to:** All firmware (C/Pico SDK , MicroPython) and ground-station tooling.

## Table of Contents

1. [General Principles](#1-general-principles)
2. [Repository Structure](#2-repository-structure)
3. [C - Pico SDK Firmware](#3-c--pico-sdk-firmware)
    - 3.1 [Naming Conventions](#31-naming-conventions)
    - 3.2 [Formatting & Braces](#32-formatting-braces)
    - 3.3 [Comments & Documentation](#33-comments--documentation)
    - 3.4 [Header Files](#34-header-files)
    - 3.5 [Error Handling](#35-error-handling)
    - 3.6 [Types & Fixed Width Integers](#36-types--fixed-width-integers)
    - 3.7 [Memory & Pointer](#37-memory--pointers)
    - 3.8 [Interrupt & DMA Safety](#38-interrupt--dma-safety)
4. [MicroPython](#4-micropython)
    - 4.1 [Naming Conventions](#41-naming-conventions)
    - 4.2 [Formatting](#42-formatting)
    - 4.3 [Comments & Docstrings](#43-comments--docustrings)
    - 4.4 [Error Handling](#44-error-handling)
5. [Version Control Practices](#5-version-control-practices)
6. [Build System](#6-build-system)

---

## 1. General Principles
- **Clarity over cleverness** You are not the only one reading your code. Please favor explicit, readable constructs even when a terse alternative exists.

- **One concern per module** Each file `.c`/`.h` or `.py` file should address a single problem. It should contain a single logical subsystem e.g. : GPS parsing, sensor acquisition, telemetry framing, etc..
- **Fail loudly in development not in flight** Use assertions and diagnostic output debug builds; ensure flight builds degrade safely without halting.
- **Document the *why* and not the *what*** The code itself shows what is happening; comments should explain non-obvious design decisions and hardware-specific constraints.

---

## 2. Repository Structure

coming soon / not needed for this file

---

## 3. C - Pico SDK Firmware

### 3.1 Naming Conventions
| Construct | Convention | Example |
|---|---|---|
|Functions| `module_verb_noun()` snake_case |`gps_parse_frame()` |
|Variables (local) | snake_case | `byte_count`|
|Variables (global) | `g_` prefix + snake_case | `g_fix_valid` |
|Constraints / `#define` | SCREAMING_SNAKE_CASE | `MAX_PACKET_LENGTH` |
| Macros | SCREAMING_SNAKE_CASE | `SWAP_BYTES(x)` |
| Typedefs (structs) | PascalCase + `_t` suffix | `GpsFrame_t` |
| Enums | PascalCase + `_t` suffix , members prefixed | `TxState_t`, `TX_IDLE` |
| File names | snake_case | `telemetry_encoder.c` |

### 3.2 Formatting & Braces

**Allman style is mandatory** for all control flow constructs. Opening braces should go on their own line.

```c
/* Correct - Allman style */
if (fix_valid)
{
    gps_parse_frame(&frame);
}
else
{
    log_warn("No GPS fix");
}

/* Incorrect */
if (fix_valid){
    gps_parse_frame(&frame);
}
```
Additional rules:

- **Indent with 4 spaces**
- **Line length:** Keep lines at or under 100 chars
- **One statement per line** Never write `if(x) do_thing();` on a single line.
- **Always brace single-statement bodies.** Omitting braces for one-liner `if`/`for` bodies is not permitted.
- **Blank lines:** Use a single blank line to separate logical sections within a function; two blank lines between top-level definitions in a file.
- **Pointer declarations:** Right attach '*' ie attach to the variable name, not type.

```c
uint8_t *buf;  /*correct*/
uint8_t* buf; /*incorrect */
```
### 3.3 Comments & Documentation

Use Doxygen-style block comments on all public functions and type definitions in headers:

```c
/**
 * @brief Parse a raw NMEA sentence into a GpsFrame_t.
 *
 * @param sentence Null-terminated NMEA string (e.g. "$GPGGA,....").
 * @param out      Pointer to a caller-allocated GpsFrame_t to populate.
 * @return true on successful parse, false if the sentence is malformed or the checksum fails
 */
 bool gps_parse_sentence(const char *sentence, GpsFrame_t *out);
```
Inline comments use '/* */' and are placed **above** the line they describe, not at the end of the line, unless the comment is very short:
```c
/* Correct */
/* Shift left by 4 to align the SI4063 register format. */
reg_val = raw_freq << 4;
/* Acceptable for short notes. */
uint32_t timeout_ms = 500; /* POR stabilisation time per datasheet */
```
Do not leave commented-out code in committed files. Use version control to recover old implementations.

### 3.4 Header Files

- Use `#pragma once` at the top of every header.
- Headers expose **Only what the consumers need**. Keep internal helpers in the `.c` file or in a separate `_internal.h` that is not installed.
- Always include all headers that your header directly depends on - do not rely on transitive inclusion.
- Group includes in the following order, separated by a blank line:
    1. Standard C headers (`<stdint.h>`, `<stdbool.h>`, etc.)
    2. Pico SDK headers (`"pico/stdlib.h"`, `"hardware/uart.h"`, etc.)
    3. Project headers (`"gps.h"`, `"telemetry.h"`, etc.)

```c
#pragma once

#include <stdint.h>
#include <stdbool.h>

#include "pico/stdlib.h"
#include "hardware/spi.h"

#include "telemetry.h"
```

### 3.5 Error Handling

- Functions that can fail **must** return a status. Prefer `bool` for simple pass/fail, or a project-defined `SondeStatus_t` enum for multi-error subsystem.
-Never silently discard a return value from a function that can fail. If the result is intentionally unused, cast to `(void)`;
- In debug builds, use `assert()` to catch programming errors. In flight builds, assert should compile out (`NDEBUG`).
- Do not use `while(1)` panic loops in flight code - always attempt graceful recovery or safe-state entry.

### 3.6 Types & Fixed-Width Integers

- Prefer fixed-width types from `<stdint.h>` for all hardware-interfacing protocol code: `uint8_t`, `uint16_t`, `uint32_t`, etc..
- Use `size_t` for buffer lengths and loop indices over arrays.
- Use `bool` (from `<stdbool.h>`) for boolean states. Never use `int` as a boolean.
- Avoid `float` in ISR context. Use fixed-point (`int32_t` with a documented scale factor) or defer float math to the main loop.

### 3.7 Memory & Pointers

- No dynamic memory allocation (`malloc`/`free`) in flight firmware. All buffers are statically allocated.
- Clearly document buffer ownership: who allocates, who frees (if ever), and who may write.
- Mark pointers to read-only data as `const`.
- Mark output-only pointer parameters clearly in the Doxygen `@param` docs.

### 3.8 Interrupt & DMA Safety

- Variables shared between ISR and main-loop context **must** be declared `volatile`.
- Accesses to multi-byte shared variables must be protected (disable IRQ + restore, or use the Pico SDK's `__dmb()` / critical section APIs).
- Keep ISR bodies minimal - set a flag or write a ring buffer; do all heavy processing in the main loop.
- DMA buffer pointers must be 4-byte aligned. Use `__attribute__((aligned(4)))`.

---

## 4. MicroPython

### 4.1 Naming Conventions

| Construct | Convention | Example |
|---|---|---|
| Functions | snake_case | `decode_frame` |
|Variables | snake_case | `packet_count`|
|Constants | SCREAMING_SNAKE_CASE | `BAUD_RATE` |
| Classes | PascalCase | `SondeDecoder` |
| Private members | leading underscore | `_checksum_` |
| Modules/files | snake_case | `telemetry_decoder.py` |

### 4.2 Formatting

- Follow **PEP 8** as the baseline style guide.
- **Indent with 4 spaces**
- **Line length:** 100 character maximum (to stay consistent with the C standard above).
- Two blank lines between top-level function and class definitions; one blank line between methods within a class.
- Imports are grouped in PEP 8 order (stdlib -> third-party -> local), each grouped separated by a blank line.

```python
import struct
import sys

import serial

from sonde.telemetry import SondeDecoder
```

### 4.3 Comments and Docstrings

All public functions, classes, and methods get a docstring. Use Google-style docstrings:

```python
def decode_frame(raw: bytes) -> dict:
    """Decode a raw telemetry frame into a dictionary of sensor values.

    Args:
        raw: Raw byte payload from the radio receiver, including the
             2-byte sync word and trailing CRC.
    
    Returns:
        A dict with keys 'lat', 'lon', 'alt_m', 'temp_c', 'rh_pct',
        'pressure_hpa'. Missing or invalid fields are None.

    Raises:
        ValueError: If the sync word is absent or the CRC fails.
    """
```

Inline comment us `#` with a single space, placed above the relevant line:

```python
# Convert raw ADC count to temperature using datasheet equation
temp_c = (raw_adc * 0.0625) - 40.0
```

### 4.4 Error Handling

- Use specific exception types, never bare `except:`.
- Log errors with enough context to reconstruct what went wrong (packet binary dump, timestamp, etc.).
- Ground-station tools should never crash silently -  at a minimum, print a human readable error and continue or exit cleanly

```python
try:
    frame = decode_frame(raw_bytes)
except ValueError as e:
    print(f"[WARN] Bad frame at t = {timestamp}: {e} | raw = {raw_bytes.binary()}")
    continue
```

---

## 5. Version Control Practice (Git)

- **Branch naming:** `feature/<short-description>`, `fix/<short-description>`, `chore/<short-description>`.
- **Commit messages** Use the imperative mood and keep the subject line under 72 characters.
    - Good: `Added GPS checksum validation to parser`
    - Bad: `fixed stuff` / `WIP`
- Every commit on `main` must build cleanly with zero warning s at the project's standard warning level (`-Wall -Wextra` for C).
- Do not commit generated build artifacts, `.uf2` binaries, or IDE-specific files. Use `.gitignore`.

---

## 6. Build Systems

- The firmware uses **CMake** via the Pico SDK's standard project structure.
- Enable warnings-as-errors in CI: ass `--Werror` to `CMAKE_C_FLAGS` in the CI build configuration (not in the development default, to avoid friction during active development).
- The recommended compiler flag set for development builds:

```cmake
target_compile_options(sonde_firmware PRIVATE
    -Wall
    -Wextra
    -Wshadow
    -Wdouble-promotion
    -Wformat=2
    -fno-common
)
```

- Python tooling dependencies are pinned in `tools/requirements.txt` with exact versions.

---
*This document is a living standard. Propose changes via pull request with a brief rational in the PR description.*