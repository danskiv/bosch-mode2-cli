# Architecture

## Purpose

`bosch-mode2-cli` is a read-oriented command-line monitor for Bosch Solution 2000 and Solution 3000 panels connected through a B426/B426-M IP module. It uses the Mode 2 protocol over the configured TCP/TLS transport and presents panel state and event history in a terminal.

The compatibility claim is deliberately limited. Solution 2000 is the validated development target. Solution 3000 is a theoretical target because the upstream library maps model code `0x21` to the same Solution family; the repository does not yet contain a physical Solution 3000 validation run.

The project is an engineering companion, not a replacement for the Bosch panel, B426, A-Link Plus, monitoring center, or alarm signaling path.

## Runtime Layers

```text
CLI (`cli.py`)
  ├── configuration wizard: B426 IP, port, visible user code
  ├── monitor/status/history/raw/simulate commands
  └── Rich TUI or plain-text output
        │
        ▼
Application client (`client.py`)
  ├── adapts bosch-alarm-mode2 Panel
  ├── maps panel observers to project records
  ├── maintains transaction de-duplication
  └── cancels background tasks during shutdown
        │
        ▼
Protocol helpers (`raw_protocol.py`)
  ├── Mode 2 frame construction/parsing
  ├── response and NACK decoding
  └── raw diagnostic stream support
        │
        ▼
B426 / Mode 2 transport
        │
        ▼
Solution 2000/3000 panel
```

## Main Modules

| Module | Responsibility |
|---|---|
| `cli.py` | Command-line parser, configuration wizard, command orchestration, output mode selection |
| `client.py` | Async panel adapter, TLS context setup, observers, snapshots, event callbacks, safe shutdown |
| `history.py` | History event conversion, filtering, table/JSON/CSV export |
| `models.py` | Typed records for panel snapshots, areas, points, and transactions |
| `raw_protocol.py` | Mode 2 frame parser, frame builder, raw client, diagnostic exchanges |
| `simulator.py` | Local Solution 2000-compatible test server and event generator; not a Solution 3000 test harness |
| `ui.py` | Rich tables, dashboard layout, and plain event formatting |

## Connection Flow

The normal monitor flow is:

1. Load the per-user YAML configuration.
2. Prompt for B426 IP address, port, and visible user code. Existing values are displayed as defaults; Enter retains them.
3. Save the selected values locally.
4. Open the configured transport to the exact target entered by the operator.
5. Authenticate with the numeric Solution user code.
6. Load panel metadata, areas, points, status, and optionally history.
7. Start observers and the background status refresh loop.
8. Render updates until Ctrl+C or a connection error.
9. Cancel polling and connection-monitor tasks, then close the socket.

The application does not silently scan for another IP or retry a different target. This is intentional: the operator controls which panel is contacted.

## Monitoring Semantics

The monitor is hybrid rather than universally push-realtime:

- the upstream library can process subscription/event callbacks where the panel supports them;
- the client also refreshes panel status approximately every second;
- history retrieval is a query operation and may depend on panel state and user authority;
- the CLI has no siren, audio, toast, Telegram, or WhatsApp notification output;
- the panel remains responsible for alarm signaling.

A displayed event is evidence that the panel/client path delivered that event. It is not proof that the laptop generated or controlled a siren.

## Read-Only Boundary

The normal monitor/status/history path is intended for reads. The raw protocol and upstream library expose action opcodes, so contributors must not add or invoke arm/disarm, output-control, date/time, or configuration commands in monitoring code without an explicit design review and a separate safety gate.

Before a field test, close A-Link Plus and other competing B426 clients. Use one active client at a time.

## Configuration

The default settings file is:

- Windows: `%APPDATA%\\bosch-mode2-cli\\config.yaml`
- Linux: `~/.config/bosch-mode2-cli/config.yaml`

The file stores `panel.host`, `panel.port`, `panel.user_code`, and non-secret transport/monitor preferences. The current local workflow intentionally stores and displays the user code as plaintext. Do not place production credentials into source control, issue reports, screenshots, or shared command transcripts.
