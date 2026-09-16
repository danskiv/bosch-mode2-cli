# Bosch Solution 2000 Mode 2 Monitoring CLI

A read-oriented command-line monitor for Bosch Solution 2000/3000 intrusion panels connected through a B426/B426-M IP module.

The application can display panel identity, areas, points/zones, faults, event history, and live status/event updates through a Rich dashboard or plain-text stream. It is intended for controlled engineering and monitoring workflows; it does not replace the panel, B426, A-Link Plus, monitoring center, or siren path.

## Capabilities

- Read panel identity, metadata, areas, points, status, faults, and history.
- Display live point/area/event updates in a terminal.
- Export history as table, JSON, or CSV.
- Inspect raw Mode 2 frames through the `raw` command.
- Run a local Solution 2000 simulator for development and tests.
- Use TLS by default for the observed B426 field transport, with explicit plain-TCP override where appropriate.
- Configure B426 IP, port, and visible user code through a local wizard.

## Important Boundaries

- The normal monitor path is read-oriented.
- The CLI does not generate siren sounds or Windows/Telegram/WhatsApp notifications.
- The application does not silently scan for another IP. If B426 receives a new address, enter it at the next wizard prompt.
- Close A-Link Plus, the B426 web UI, and other competing clients before a direct Mode 2 session.
- Do not use factory reset, `Save and Execute`, or `Download to Control Panel` as troubleshooting shortcuts.
- Never commit production credentials, raw sensitive captures, or a populated per-user configuration file.

## Requirements

- Python 3.11 or newer for source execution.
- Windows 10/11 or Linux.
- A routed connection from the laptop to the B426.
- An authorized maintenance/testing window for physical-panel work.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## Run on Windows

```powershell
cd C:\Users\tech\Documents\GitHub\bosch-mode2-cli
powershell -ExecutionPolicy Bypass -File .\run-monitor.ps1
```

The wizard asks for:

```text
B426 IP address [saved value]:
Port [saved value]:
Code [saved value]:
```

Press Enter to keep a saved value or type a replacement. The code is intentionally displayed and stored as plaintext for the approved local Windows workflow.

The default settings file is `%APPDATA%\\bosch-mode2-cli\\config.yaml` on Windows and `~/.config/bosch-mode2-cli/config.yaml` on Linux.

## CLI Commands

```bash
# Live Rich dashboard or plain stream
bosch-mode2 monitor
bosch-mode2 monitor --plain

# Read a one-shot status snapshot
bosch-mode2 status --host <B426_IP> --port 7700 --pin <LOCAL_CODE>

# Query and export history
bosch-mode2 history --host <B426_IP> --port 7700 --pin <LOCAL_CODE> --limit 20
bosch-mode2 history --host <B426_IP> --format json --pin <LOCAL_CODE> > events.json

# Raw Mode 2 diagnostic view
bosch-mode2 raw --host <B426_IP> --port 7700 --pin <LOCAL_CODE>

# Local simulator only; never contacts the alarm panel
bosch-mode2 simulate --port 17700 --pin LOCAL_TEST_CODE --auto-events
bosch-mode2 monitor --host 127.0.0.1 --port 17700 --pin LOCAL_TEST_CODE --no-tls --plain
```

Replace placeholders locally. Do not paste production codes into chat, documentation, or shell history.

## Tests

```bash
pytest -q
python -m compileall -q src
git diff --check
```

The simulator-backed tests do not contact a physical alarm panel.

## Repository Guide

- [Documentation index](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Windows runbook](docs/WINDOWS-RUNBOOK.md)
- [Development guide](docs/DEVELOPMENT.md)
- [Versioning and release policy](docs/VERSIONING.md)
- [Project audit and cleanup record](docs/PROJECT-AUDIT.md)
- [Mode 2 protocol specification](docs/BOSCH-MODE2-PROTOCOL-SPEC.md)
- [Integration research report](docs/BOSCH-INTEGRATION-RESEARCH-REPORT.md)

## Current Protocol Notes

- Solution 2000 model code: `0x20`.
- Default Mode 2 port: `7700`.
- Solution user authentication uses the numeric code entered through the wizard or explicit CLI override.
- Event delivery is hybrid: subscription callbacks where supported plus periodic status refresh; “realtime” must not be interpreted as guaranteed push for every entity.
- History retrieval may require the configured user to have `Master Code Functions` authority and may be skipped while areas are armed.

See the protocol specification and sourced research report for detailed evidence, caveats, and unresolved model/firmware differences.
