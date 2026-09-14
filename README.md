# Bosch Solution 2000 Mode 2 Monitoring CLI (`bosch-mode2-cli`)

A lightweight, dedicated Command-Line Interface (CLI) monitoring tool for **Bosch Solution 2000 / 3000 Intrusion Alarm Panels** communicating via the **Bosch Mode 2 Automation Protocol** over TCP (port 7700) using B426 / B426-M IP modules.

---

## 🎯 Features

- ⚡ **Live Real-time Monitoring:** Interactive terminal dashboard (Rich TUI) displaying connection state, area arming status, point loop states, and real-time transaction event log.
- 📜 **Transaction & History Explorer:** Query panel event history with categorization (Alarm, Restore, Arm/Disarm, Trouble, System), full-text search, and multi-format export (`table`, `json`, `csv`).
- 🔍 **Instant Status Snapshot:** One-shot diagnostic readout of panel model, firmware version, serial, zone states, area statuses, and panel faults.
- 🧪 **Built-in Mock Simulator:** Integrated Solution 2000 Mode 2 TCP server (`0x20`) for testing, development, and bench verification without requiring physical B426 hardware.
- 🔒 **Plain TCP & TLS Adaptable:** Designed specifically for Solution 2000 IP modules which frequently operate plain TCP over port 7700, avoiding SSL handshake mismatch errors.

---

## ⚙️ Solution 2000 Technical Specifics & Protocol Rules

| Parameter | Specification & Field Rules |
| :--- | :--- |
| **Model Code** | `0x20` (Solution 2000) / `0x21` (Solution 3000) |
| **Default Port** | TCP `7700` (Automation Port configured in B426/A-Link Plus) |
| **Authentication** | **User PIN Code** (numeric, 4–8 digits, e.g. `1234`). Authenticates as `USER_TYPE.REMOTE_USER`. (Note: Sol2000 does not use the 10-character Automation Passcode required by B/G Series panels). |
| **History Authority** | In **Bosch A-Link Plus**, the user account assigned to the PIN **MUST** have the `"Master Code Functions"` authority enabled to retrieve historical event logs. |
| **Disarmed Requirement** | By Bosch firmware design, historical event records can only be retrieved when **all areas are in Disarmed state**. When armed, event query is skipped by safety guards. |
| **Concurrency** | **Single in-flight command**. The B426 serial bus on Solution panels does not support command pipelining; all commands are executed sequentially with a semaphore guard. |

---

## 🚀 Installation

### 1. Requirements
- Python 3.11 or 3.12
- Linux (Ubuntu/Debian) or Windows 10/11 (PowerShell/CMD)

### 2. Setup Virtual Environment
```bash
# Clone or enter project directory
cd bosch-mode2-cli

# Create virtual environment
python3 -m venv .venv

# Activate venv
# Linux:
source .venv/bin/activate
# Windows (PowerShell):
# .\.venv\Scripts\Activate.ps1

# Install dependencies and CLI
pip install --upgrade pip
pip install -e .
```

---

## 📖 Usage Guide

### 1. Live Interactive Dashboard (TUI)
```bash
# Connect using CLI arguments
bosch-mode2 monitor --host 192.168.1.50 --pin 1234

# Or using config.yaml
bosch-mode2 monitor -c config.yaml

# Plain-text streaming mode (ideal for loggers / pipe / headless)
bosch-mode2 monitor --host 192.168.1.50 --pin 1234 --plain
```

### 2. History & Transaction Explorer
```bash
# View last 20 events as a formatted table
bosch-mode2 history --host 192.168.1.50 --pin 1234 --limit 20

# Filter by event category (alarm, restore, arm_disarm, trouble, system)
bosch-mode2 history --host 192.168.1.50 --pin 1234 --category alarm

# Search specific zone or user in history
bosch-mode2 history --host 192.168.1.50 --pin 1234 --search "Front Door"

# Export transactions to JSON or CSV
bosch-mode2 history --host 192.168.1.50 --pin 1234 --format json > events.json
bosch-mode2 history --host 192.168.1.50 --pin 1234 --format csv > events.csv
```

### 3. One-Shot Status Snapshot
```bash
bosch-mode2 status --host 192.168.1.50 --pin 1234
```

### 4. Raw Protocol Inspector & Sniffer (`raw`)
Inspect raw Mode 2 hex frames, diagnostic requests, and response packets:
```bash
# Full diagnostic dump of all panel endpoints with raw request/response frames
bosch-mode2 raw --host 192.168.1.50 --pin 1234

# View full hex dump with offset and ASCII breakdown
bosch-mode2 raw --host 192.168.1.50 --pin 1234 --format hexdump

# Export all raw exchanges as JSON
bosch-mode2 raw --host 192.168.1.50 --pin 1234 --format json --save raw_dump.json

# Live raw packet sniffer (passively listens and displays incoming raw frames)
bosch-mode2 raw --host 192.168.1.50 --pin 1234 --mode sniff
```

### 5. Running the Local Panel Simulator
You can simulate a Solution 2000 panel on `127.0.0.1:7700` without any physical panel:
```bash
# Start simulator on port 7700 with periodic zone activity
bosch-mode2 simulate --port 7700 --pin 1234 --auto-events --auto-interval 4.0

# In another terminal window, monitor the simulated panel:
bosch-mode2 monitor --host 127.0.0.1 --port 7700 --pin 1234
```

---

## 📂 Project Structure

```
bosch-mode2-cli/
├── config.example.yaml         # Example configuration file
├── pyproject.toml              # Packaging & dependencies
├── requirements.txt            # Dependency specification
├── sync-to-laptop.sh           # One-click sync script to Danas's laptop
├── src/
│   └── bosch_mode2_cli/
│       ├── __init__.py
│       ├── cli.py              # CLI entrypoint & subcommands
│       ├── client.py           # Async Sol2000 client & observer engine
│       ├── history.py          # Transaction decoding & export
│       ├── models.py           # Typed entities (Snapshot, Point, Area, Event)
│       ├── simulator.py        # Mode 2 Solution 2000 mock TCP server
│       └── ui.py               # Rich TUI dashboard components
└── tests/
    ├── test_cli.py             # CLI parser and command tests
    ├── test_history.py         # History parsing and formatting tests
    ├── test_integration.py     # End-to-end client <-> simulator tests
    ├── test_models.py          # Data models & category classification tests
    └── test_simulator.py       # Mode 2 mock server tests
```

---

## 🧪 Running Tests

```bash
pytest -v
```
All 12 unit and integration tests validate:
- Protocol encoding/decoding for Solution 2000 8-byte history frames
- Command dispatching (`WHAT_ARE_YOU`, `LOGIN_REMOTE_USER`, `AREA_STATUS`, `POINT_STATUS`, `REQUEST_RAW_HISTORY_EVENTS`)
- Client lifecycle and snapshot state extraction
- CLI subcommands and JSON output formatting
