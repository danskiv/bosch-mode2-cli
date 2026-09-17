# Bosch Solution 2000/3000 Mode 2 Monitoring CLI

A read-oriented command-line monitor for Bosch Solution 2000 and Solution 3000 intrusion panels connected through a B426/B426-M IP module.

The project currently has two different evidence levels: Solution 2000 is the validated development target; Solution 3000 is a theoretical compatibility target based on the shared Mode 2 implementation and model code `0x21`. A Solution 3000 installation still requires hardware validation for its panel firmware, network module, transport mode, authentication, history access, and event delivery.

The application can display panel identity, areas, points/zones, faults, event history, and live status/event updates through a Rich dashboard or plain-text stream. It is intended for controlled engineering and monitoring workflows; it does not replace the panel, B426, A-Link Plus, monitoring center, or siren path.

## Capabilities

- Read panel identity, metadata, areas, points, status, faults, and history.
- Display live point/area/event updates in a terminal.
- Export history as table, JSON, or CSV.
- Inspect raw Mode 2 frames through the `raw` command.
- Run a local Solution 2000 simulator for development and tests. The simulator is not a Solution 3000 validation tool.
- Use TLS by default for the observed B426 field transport, with explicit plain-TCP override where appropriate.
- Configure B426 IP, port, and visible user code through a local wizard.
- Optionally send live `ALARM` and `RESTORE` notifications to Telegram.

## Important Boundaries

- The normal monitor path is read-oriented.
- The CLI does not generate siren sounds or act as a monitoring-center alarm path. Optional Telegram messages are a convenience notification only.
- The application does not silently scan for another IP. If B426 receives a new address, enter it at the next wizard prompt.
- Close A-Link Plus, the B426 web UI, and other competing clients before a direct Mode 2 session.
- Do not use factory reset, `Save and Execute`, or `Download to Control Panel` as troubleshooting shortcuts.
- Never commit production credentials, raw sensitive captures, or a populated per-user configuration file.

## Requirements

- Python 3.11 or newer for source execution.
- Windows 10/11 or Linux.
- A routed connection from the laptop to the B426.
- An authorized maintenance/testing window for physical-panel work.

## Compatibility Status

| Panel | Evidence level | What this means |
|---|---|---|
| Solution 2000 | Validated development target | The project simulator and current field investigation use the Solution 2000 path. This does not certify every B426 firmware combination. |
| Solution 3000 | Theoretical compatibility | The upstream Mode 2 model map identifies `0x21` as Solution 3000 and places it in the Solution family. A physical Solution 3000 test is still required before production use. |

The shared protocol path is a reason to test Solution 3000, not proof that every command behaves identically on every firmware. Keep Solution 2000, Solution 3000, B426, and B426-M evidence separate.

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

## Optional Telegram Notifications

Enable the simple Telegram MVP in the local configuration file:

```yaml
notifications:
  telegram:
    enabled: true
    bot_token_env: TELEGRAM_BOT_TOKEN
    chat_id_env: TELEGRAM_CHAT_ID
```

Set the environment values locally before starting the monitor:

```powershell
$env:TELEGRAM_BOT_TOKEN = '<bot-token>'
$env:TELEGRAM_CHAT_ID = '<chat-id>'
```

Only live `ALARM` and `RESTORE` events are sent. Each message contains the panel name, zone when available, and panel event time. Initial history is not sent. Telegram is disabled by default, uses in-memory deduplication, and is only a convenience notification—not a replacement for the panel siren or monitoring center. Do not commit the token or chat ID.

## Telegram Zone Settings

The bot can change **Telegram notification policy only**. The CLI and dashboard continue to show every panel zone. The bot cannot arm/disarm the panel, operate outputs, or change B426 settings.

Allowed commands:

```text
/zones
/zone_on <number>
/zone_off <number>
/zone_name <number> <name>
/settings
/status
/test_notification
/help
```

The bot also registers a Telegram menu with `/menu`, `/zones`, `/settings`, `/status`, `/test_notification`, and `/help`. `/menu` opens inline buttons; selecting a zone shows ON, OFF, and Rename buttons. Rename asks for the next text message. This menu configures Telegram notifications only and is available for processing only while the monitor laptop is online.

Only chat IDs listed in `notifications.telegram.allowed_chat_ids` may use these commands. Changes apply to the next event and are saved in the local YAML configuration. Configure the allowlist explicitly:

```yaml
notifications:
  telegram:
    allowed_chat_ids:
      - 1065735978
    # Required for authorized members when using a group chat.
    allowed_user_ids: []

zones:
  "1":
    enabled: true
    name: "Pintu Depan"
  "3":
    enabled: false
    name: "Kamar Utama"
```

Do not place the bot token in this YAML file. The token remains in the local environment/secret file used by the launcher.

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
- Solution 3000 model code: `0x21`.
- Default Mode 2 port: `7700`.
- Solution user authentication uses the numeric code entered through the wizard or explicit CLI override.
- Event delivery is hybrid: subscription callbacks where supported plus periodic status refresh; “realtime” must not be interpreted as guaranteed push for every entity.
- History retrieval may require the configured user to have `Master Code Functions` authority and may be skipped while areas are armed.

See the protocol specification and sourced research report for evidence, caveats, and unresolved model/firmware differences. Do not read the model list as a production certification.
