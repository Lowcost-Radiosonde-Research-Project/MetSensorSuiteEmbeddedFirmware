# Contributing to the Lowcost Radiosonde Research Project

Thank you for contributing. This document covers how to get your development environment set up and how we manage code changes. Please also read the [Coding Standard](CODING_STANDARD.md) before writing any code.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Development Environment Setup](#2-development-environment-setup)
   - 2.1 [C / Pico SDK Firmware](#21-c--pico-sdk-firmware)
   - 2.2 [MicroPython Firmware](#22-micropython-firmware)
   - 2.3 [Ground Station Tooling](#23-ground-station-tooling)
3. [Branch and PR Workflow](#3-branch-and-pr-workflow)
4. [Commit Message Guidelines](#4-commit-message-guidelines)

---

## 1. Prerequisites

Ensure the following are installed before proceeding:

- [Git for Windows](https://git-scm.com/download/win)
- [VSCode](https://code.visualstudio.com/) with the following extensions:
  - Raspberry Pi Pico (official extension)
  - C/C++ (Microsoft)
  - Python (Microsoft)
- [Python 3.11+](https://www.python.org/downloads/) — ensure it is added to PATH during installation
- [CMake](https://cmake.org/download/) — added to PATH during installation

The Raspberry Pi Pico VSCode extension will handle downloading the Pico SDK and toolchain automatically on first use. You do not need to install the ARM toolchain manually.

---

## 2. Development Environment Setup

### 2.1 C / Pico SDK Firmware

1. Clone the repository and open it in VSCode.
2. When prompted, install the recommended extensions from `.vscode/extensions.json`.
3. The Raspberry Pi Pico extension will prompt you to configure the SDK — accept and let it complete.
4. Select your board as **Raspberry Pi Pico 2** when prompted.
5. Use the Pico extension's **Build** button or `Ctrl+Shift+B` to build the firmware.
6. Flash to the Pico by holding BOOTSEL, connecting USB, then dragging the `.uf2` from `build/` to the mounted drive — or use the extension's **Run** button with a Picoprobe connected.

> **Picoprobe:** Flash the second Pico 2 H with the Picoprobe UF2 and connect its SWD pins to the target board. This enables flashing and full debug support directly from VSCode without manually entering BOOTSEL mode.

### 2.2 MicroPython Firmware

1. Flash the MicroPython UF2 for the Pico 2 onto your board — download from the [Raspberry Pi MicroPython page](https://micropython.org/download/RPI_PICO2/).
2. The Raspberry Pi Pico VSCode extension handles MicroPython file sync and REPL access.
3. Connect to the board REPL via the extension's terminal panel.
4. Sync files from `micropython/` to the board using the extension's upload function.

> **Note:** The `micropython/` directory contains code that runs on the Pico. It does not use a virtual environment — MicroPython has its own isolated runtime on the device.

### 2.3 Ground Station Tooling

Ground station scripts run on the host machine and require a Python virtual environment.

```bash
cd ground_station
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Keep `requirements.txt` up to date if you add new dependencies:

```bash
pip freeze > requirements.txt
```

---

## 3. Branch and PR Workflow

We follow a simple feature branch workflow:

```
main
 └── develop
      ├── feature/gps-parser
      ├── feature/si4032-driver
      └── fix/afsk-timing
```

**Branch naming** follows the convention defined in the coding standard:

| Type | Pattern | Example |
|---|---|---|
| New feature | `feature/<short-description>` | `feature/sd-card-logger` |
| Bug fix | `fix/<short-description>` | `fix/gps-checksum` |
| Chores / housekeeping | `chore/<short-description>` | `chore/update-gitignore` |

**Workflow:**

1. Branch off `develop` — never work directly on `main`
2. Make your changes in small, focused commits
3. Open a pull request into `develop` when your feature is complete and bench tested
4. `main` receives merges from `develop` only at stable milestones — PCB revisions, post-flight

> **Rule:** Every commit on `main` must build cleanly with zero warnings.

---

## 4. Commit Message Guidelines

Use the imperative mood and keep the subject line under 72 characters.

```
Added CRC-16 validation to iMet-4 packet builder
Fix GPS NMEA checksum rejection on cold start
Refactor Si4032 SPI driver into separate module
```

Avoid vague messages:

```
# Bad
fixed stuff
WIP
updates
```

For changes that need more context, add a body after a blank line:

```
Added Steinhart-Hart conversion to temperature sensor

Replaces the linear approximation used during bring-up.
Coefficients are sourced from the thermistor datasheet Table 3.
Valid over -80°C to +60°C operating range.
```

---

*Propose changes to this document via pull request with a brief rationale in the PR description.*