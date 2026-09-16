# Windows Runbook

## Prerequisites

- Windows 10/11
- Python 3.11 or newer for source execution
- A direct route from the laptop Ethernet adapter to the B426 network
- A maintenance window and authorization for the panel test
- A-Link Plus and the B426 web interface disconnected before a direct Mode 2 session

The monitor does not configure the B426 or the panel. Confirm the B426 address and port through the approved commissioning process before connecting.

## Source Installation

From PowerShell:

```powershell
cd C:\Users\tech\Documents\GitHub\bosch-mode2-cli
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

If editable installation is unavailable, run from source with:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
```

## Start the Monitor

The project launcher is:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-monitor.ps1
```

The wizard asks, in order:

```text
B426 IP address [saved value]:
Port [saved value]:
Code [saved value]:
```

On first use, enter all three values. On later runs, press Enter to retain a value or type a replacement. If DHCP or commissioning changes the B426 IP, replace the IP at this prompt. The application then uses the selected IP; it does not silently discover or retry another address.

The code is intentionally visible and persisted in the local configuration because this is the approved local Windows workflow. Protect the laptop and configuration file accordingly.

## Useful Commands

```powershell
# Plain text monitor through the project launcher
.\run-monitor.ps1

# One-shot status with explicit overrides
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
.\.venv\Scripts\python.exe -m bosch_mode2_cli.cli status --host <B426_IP> --port 7700 --pin <LOCAL_CODE>

# History query
.\.venv\Scripts\python.exe -m bosch_mode2_cli.cli history --host <B426_IP> --port 7700 --pin <LOCAL_CODE> --limit 20

# Local simulator; this does not contact the alarm panel
.\.venv\Scripts\python.exe -m bosch_mode2_cli.cli simulate --port 17700 --pin LOCAL_TEST_CODE --auto-events
```

Replace angle-bracket placeholders locally. Do not paste production codes into chat or documentation.

## Expected Output

A successful session should progress through:

1. TCP connection to the selected B426 address and port.
2. TLS or plain transport negotiation according to configuration.
3. Mode 2 panel identity.
4. Solution user authentication.
5. Panel metadata and status loading.
6. Plain event/status lines or the Rich dashboard.

A `WinError 121` or similar semaphore timeout is a transport/session failure. It is not proof that the user code was rejected. Stop repeated attempts, verify the cable, route, B426 listener, and competing sessions first.

## Stop and Recovery

Press `Ctrl+C`. The client should cancel polling and close its socket. Verify no monitor process remains before reopening A-Link Plus or starting another client.

Do not press B426 `Save and Execute`, `Download to Control Panel`, or factory reset controls as a troubleshooting shortcut. Configuration recovery requires an approved maintenance plan and backup.

## Portable Build

Release tooling is under `tools/release/`.

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\release\build_portable.ps1
powershell -ExecutionPolicy Bypass -File .\tools\release\smoke_portable.ps1
```

The generated ZIP is placed under `release/windows/` and is intentionally ignored by Git. Keep release packages outside the source tree when possible.
