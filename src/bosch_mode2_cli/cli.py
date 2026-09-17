from __future__ import annotations

import argparse
import asyncio
import logging
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import yaml
from rich.console import Console
from rich.live import Live

from bosch_mode2_cli import __version__
from bosch_mode2_cli.client import BoschSol2000Client

from bosch_mode2_cli.history import (
    create_transactions_table,
    export_transactions_csv,
    export_transactions_json,
    filter_transactions,
)
from bosch_mode2_cli.models import EventCategory
from bosch_mode2_cli.raw_protocol import RawMode2Client
from bosch_mode2_cli.simulator import BoschSol2000Simulator
from bosch_mode2_cli.telegram_notifier import (
    AlarmRestoreNotifier,
    TelegramBotController,
    TelegramNotifier,
    TelegramControlPoller,
    ZoneSettings,
)
from bosch_mode2_cli.ui import (
    build_dashboard_layout,
    format_plain_transaction,
    format_raw_frame_line,
    render_areas_table,
    render_header,
    render_points_table,
    render_raw_exchange_table,
)

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

console = Console(legacy_windows=False)


def build_telegram_notifier(
    telegram_cfg: Dict[str, Any], panel_name: str, config: Optional[Dict[str, Any]] = None,
    on_change: Optional[Callable[[], None]] = None,
) -> Optional[AlarmRestoreNotifier]:
    """Build the optional Telegram notifier from local environment values."""
    if not telegram_cfg.get("enabled", False):
        return None
    token = os.getenv(telegram_cfg.get("bot_token_env", "TELEGRAM_BOT_TOKEN"), "")
    chat_id = os.getenv(telegram_cfg.get("chat_id_env", "TELEGRAM_CHAT_ID"), "")
    if not token or not chat_id:
        console.print(
            "[yellow]Telegram notifications disabled: environment values are missing.[/]"
        )
        return None
    telegram = TelegramNotifier(token=token, chat_id=chat_id)
    zones_cfg = (config or {}).get("zones", {})
    settings = ZoneSettings(zones_cfg, on_change=on_change)
    notifier = AlarmRestoreNotifier(panel_name, telegram.send, settings=settings)
    allowed = {int(value) for value in telegram_cfg.get("allowed_chat_ids", [chat_id])}
    notifier.telegram_api = telegram
    notifier.telegram_controller = TelegramBotController(settings, allowed, telegram.send_chat)
    return notifier


def default_config_path() -> Path:
    """Return a per-user config path, outside the repository."""
    if sys.platform == "win32":
        root = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / "bosch-mode2-cli" / "config.yaml"
    root = os.getenv("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(root) / "bosch-mode2-cli" / "config.yaml"


def save_panel_config(path: Path, host: str, port: int, user_code: str) -> None:
    """Persist the user-approved B426 connection settings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {}
    if path.is_file():
        try:
            existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            existing = {}
    panel = existing.setdefault("panel", {})
    panel.pop("user_pin", None)
    panel["host"] = host
    panel["port"] = port
    panel["user_code"] = str(user_code)
    path.write_text(
        yaml.safe_dump(existing, sort_keys=False),
        encoding="utf-8",
    )


def save_runtime_config(path: Path, cfg: Dict[str, Any]) -> None:
    """Persist non-secret runtime settings, excluding the internal path marker."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {key: value for key, value in cfg.items() if not key.startswith("__")}
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def resolve_panel_settings(
    host_override: Optional[str],
    port_override: Optional[int],
    code_override: Optional[str],
    cfg: Dict[str, Any],
    *,
    config_path: Optional[Path] = None,
 ) -> tuple[str, int, str]:
    """Prompt for IP, port, and visible code, using saved values as defaults."""
    panel_cfg = cfg.setdefault("panel", {})
    saved_host = panel_cfg.get("host")
    saved_port = panel_cfg.get("port")
    saved_code = panel_cfg.get("user_code") or panel_cfg.get("user_pin")
    host = host_override or saved_host
    port = port_override or saved_port
    user_code = code_override or saved_code

    if sys.stdin.isatty():
        console.print("[bold cyan]B426 connection setup[/]")
        host_prompt = saved_host or "192.168.20.151"
        port_prompt = saved_port or 7700
        code_prompt = saved_code or ""
        if host_override is None:
            host = input(f"B426 IP address [{host_prompt}]: ").strip() or host_prompt
        if port_override is None:
            raw_port = input(f"Port [{port_prompt}]: ").strip() or str(port_prompt)
            try:
                port = int(raw_port)
            except ValueError as exc:
                raise ValueError("Port must be a number") from exc
        if code_override is None:
            user_code = input(f"Code [{code_prompt}]: ").strip() or code_prompt

    if host is None or port is None or not user_code:
        raise ValueError("IP address, port, and code are required; run this command in a local terminal")

    if not str(host).strip():
        raise ValueError("IP address/hostname cannot be empty")
    try:
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError("Port must be a number") from exc
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")

    user_code = str(user_code).strip()
    if not user_code.isnumeric() or not 1 <= len(user_code) <= 8:
        raise ValueError("Code must contain 1 to 8 numeric digits")
    changed = (
        panel_cfg.get("host") != str(host).strip()
        or panel_cfg.get("port") != port
        or panel_cfg.get("user_code") != user_code
    )
    panel_cfg["host"] = str(host).strip()
    panel_cfg["port"] = port
    panel_cfg["user_code"] = user_code
    if changed and config_path is not None:
        save_panel_config(config_path, panel_cfg["host"], port, user_code)
        console.print(f"[green]Connection saved:[/] {panel_cfg['host']}:{port}")
    return panel_cfg["host"], port, user_code


def _use_tls(args: argparse.Namespace, panel_cfg: Dict[str, Any]) -> bool:
    """Use TLS by default for physical B426 modules; allow explicit plain TCP."""
    if getattr(args, "no_tls", False):
        return False
    return bool(panel_cfg.get("use_tls", True))


def _resolve_panel_for_command(args: argparse.Namespace, cfg: Dict[str, Any]) -> tuple[str, int, str]:
    config_path = cfg.get("__config_path")
    return resolve_panel_settings(
        getattr(args, "host", None),
        getattr(args, "port", None),
        getattr(args, "pin", None),
        cfg,
        config_path=Path(config_path) if config_path else None,
    )

def _add_transport_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-tls",
        action="store_true",
        help="Use plain TCP (local simulator or B426 Legacy TCP mode only)",
    )


def load_config(config_path: Optional[str]) -> Dict[str, Any]:
    """Load configuration from YAML file if available."""
    target_path = Path(config_path) if config_path else default_config_path()
    p = Path(target_path)
    if p.is_file():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                data["__config_path"] = str(p)
                return data
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read config file {p}: {e}[/]")
    return {"__config_path": str(p)}


async def cmd_monitor(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    """Run real-time Mode 2 monitor."""
    panel_cfg = cfg.get("panel", {})
    monitor_cfg = cfg.get("monitor", {})

    host, port, user_code = _resolve_panel_for_command(args, cfg)
    user_pin = user_code
    plain_mode = args.plain or monitor_cfg.get("mode") == "plain"
    poll_interval = args.interval or monitor_cfg.get("poll_interval", 1.0)
    load_history = not args.no_history

    client = BoschSol2000Client(
        host=host,
        port=port,
        user_pin=user_pin,
        use_ssl=_use_tls(args, panel_cfg),
    )

    notifications_cfg = cfg.get("notifications", {}).get("telegram", {})
    telegram_notifier = build_telegram_notifier(notifications_cfg, "Bosch Solution panel", cfg)
    notifications_ready = False
    poll_stop = threading.Event()
    poll_thread = None
    if telegram_notifier and telegram_notifier.telegram_api and telegram_notifier.telegram_controller:
        config_path = Path(cfg["__config_path"])
        settings = telegram_notifier.telegram_controller.settings
        settings._on_change = lambda: (
            cfg.__setitem__("zones", settings.as_dict()),
            save_runtime_config(config_path, cfg),
        )[-1]
        poller = TelegramControlPoller(
            telegram_notifier.telegram_api,
            telegram_notifier.telegram_controller,
            poll_stop,
        )
        poll_thread = threading.Thread(target=poller.run, name="telegram-control", daemon=True)
        poll_thread.start()

    def on_transaction(rec):
        nonlocal notifications_ready
        if plain_mode:
            console.print(format_plain_transaction(rec))
        if telegram_notifier and notifications_ready:
            try:
                telegram_notifier.process(rec)
            except Exception as exc:
                logging.getLogger(__name__).warning("Telegram notification failed: %s", exc)

    client.on_transaction = on_transaction

    if plain_mode:
        console.print(
            f"[bold blue]Starting plain-text Mode 2 stream for Bosch Sol2000 at {host}:{port}...[/]"
        )

        def on_point(pt):
            console.print(
                f"[dim]{pt.last_updated.strftime('%H:%M:%S')}[/] [cyan]Point {pt.id} ({pt.name}):[/] {pt.status_text}"
            )

        def on_area(ar):
            console.print(
                f"[dim]{ar.last_updated.strftime('%H:%M:%S')}[/] [magenta]Area {ar.id} ({ar.name}):[/] {ar.status_text}"
            )

        client.on_transaction = on_transaction
        client.on_point_update = on_point
        client.on_area_update = on_area

        try:
            await client.connect(load_history=load_history)
            if telegram_notifier:
                telegram_notifier.prime(client.transactions)
                telegram_notifier.panel_name = client.get_snapshot().model_name
                notifications_ready = True
            while True:
                await asyncio.sleep(poll_interval)
        except PermissionError:
            console.print(
                "[bold red]Authentication rejected by the panel.[/] "
                "The network/TLS/identity layers succeeded, but the User PIN was not accepted."
            )
            return 2
        except (KeyboardInterrupt, asyncio.CancelledError):
            console.print("\n[yellow]Stopping monitor...[/]")
        except Exception as exc:
            console.print(f"[bold red]Monitor connection failed:[/] {exc}")
            return 1
        finally:
            poll_stop.set()
            await client.disconnect()
        return 0

    # Interactive Rich Live Dashboard
    console.print(f"[bold cyan]Connecting to Bosch Solution 2000 at {host}:{port}...[/]")
    try:
        await client.connect(load_history=load_history)
    except Exception as e:
        console.print(f"[bold red]Connection failed:[/] {e}")
        return 1

    snapshot = client.get_snapshot()
    if telegram_notifier:
        telegram_notifier.prime(client.transactions)
        telegram_notifier.panel_name = snapshot.model_name
        notifications_ready = True

    with Live(
        build_dashboard_layout(snapshot, client.transactions),
        refresh_per_second=4,
        screen=True,
    ) as live:
        try:
            while True:
                await asyncio.sleep(poll_interval)
                cur_snapshot = client.get_snapshot()
                live.update(
                    build_dashboard_layout(cur_snapshot, client.transactions)
                )
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            poll_stop.set()
            await client.disconnect()

    return 0


async def cmd_history(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    """Fetch history / transaction log."""
    panel_cfg = cfg.get("panel", {})
    host, port, user_code = _resolve_panel_for_command(args, cfg)
    user_pin = user_code

    client = BoschSol2000Client(
        host=host,
        port=port,
        user_pin=user_pin,
        use_ssl=_use_tls(args, panel_cfg),
    )
    console.print(f"[bold cyan]Querying history from {host}:{port}...[/]")

    try:
        await client.connect(load_history=True)
    except Exception as e:
        console.print(f"[bold red]Failed to connect or fetch history:[/] {e}")
        return 1
    finally:
        await client.disconnect()

    txs = client.transactions

    # Category filter
    category_filter = None
    if args.category:
        try:
            category_filter = EventCategory(args.category.upper())
        except ValueError:
            console.print(f"[red]Unknown category filter:[/] {args.category}")
            return 1

    filtered = filter_transactions(
        txs, category=category_filter, search=args.search, limit=args.limit
    )

    if args.format == "json":
        print(export_transactions_json(filtered))
    elif args.format == "csv":
        print(export_transactions_csv(filtered))
    else:
        table = create_transactions_table(
            filtered,
            title=f"Bosch Solution 2000 History Transactions ({len(filtered)} events)",
        )
        console.print(table)

    return 0


async def cmd_status(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    """One-shot query of panel snapshot."""
    panel_cfg = cfg.get("panel", {})
    host, port, user_code = _resolve_panel_for_command(args, cfg)
    user_pin = user_code

    client = BoschSol2000Client(
        host=host,
        port=port,
        user_pin=user_pin,
        use_ssl=_use_tls(args, panel_cfg),
    )
    console.print(f"[bold cyan]Connecting to {host}:{port}...[/]")

    try:
        await client.connect(load_history=False)
        snapshot = client.get_snapshot()
    except Exception as e:
        console.print(f"[bold red]Connection error:[/] {e}")
        return 1
    finally:
        await client.disconnect()

    console.print(render_header(snapshot))
    console.print(render_areas_table(snapshot.areas))
    console.print(render_points_table(snapshot.points))

    if snapshot.faults:
        console.print(f"[bold red]Active Faults:[/] {', '.join(snapshot.faults)}")
    else:
        console.print("[green]Panel Faults:[/] [dim]None reported[/]")

    return 0


async def cmd_raw(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    """Read and display raw Mode 2 protocol frames and packets."""
    panel_cfg = cfg.get("panel", {})
    host, port, user_code = _resolve_panel_for_command(args, cfg)
    user_pin = user_code

    raw_client = RawMode2Client(host=host, port=port)
    console.print(f"[bold cyan]Connecting raw socket to {host}:{port}...[/]")
    try:
        await raw_client.connect()
    except Exception as e:
        console.print(f"[bold red]Failed to connect raw socket:[/] {e}")
        return 1

    try:
        if args.mode == "sniff":
            console.print(
                f"[bold green][+] Sniffing live raw Mode 2 frames on {host}:{port}...[/]"
            )
            console.print("[dim]Press Ctrl+C to stop listening.[/]\n")
            raw_client.on_frame = lambda f: console.print(format_raw_frame_line(f))
            await raw_client.sniff_loop(timeout=args.timeout)
        else:
            # Mode: dump
            console.print(
                f"[bold green][+] Executing full raw Mode 2 diagnostic sequence against {host}:{port}...[/]\n"
            )
            pairs = await raw_client.execute_full_diagnostic_dump(user_pin=user_pin)

            if args.format == "json":
                all_records = []
                for tx, rx in pairs:
                    all_records.append({
                        "request": tx.to_dict(),
                        "response": rx.to_dict(),
                    })
                print(json.dumps(all_records, indent=2))
            elif args.format == "hexdump":
                for i, (tx, rx) in enumerate(pairs, 1):
                    console.print(f"[bold cyan]=== Exchange #{i}: {tx.code_name} ===[/]")
                    console.print(f"[bold yellow]TX Frame ({len(tx.raw_bytes)} bytes):[/]")
                    console.print(tx.hexdump)
                    console.print(f"[bold green]RX Frame ({len(rx.raw_bytes)} bytes) - {rx.code_name}:[/]")
                    console.print(rx.hexdump)
                    console.print(f"[dim]Interpretation:[/] {rx.decoded_info}\n")
            else:
                # Table format
                table = render_raw_exchange_table(pairs)
                console.print(table)

            if args.save:
                out_path = Path(args.save)
                with open(out_path, "w", encoding="utf-8") as f:
                    data = [{"request": tx.to_dict(), "response": rx.to_dict()} for tx, rx in pairs]
                    json.dump(data, f, indent=2)
                console.print(f"\n[green]Saved raw capture to:[/] {out_path}")

    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n[yellow]Raw session terminated.[/]")
    finally:
        await raw_client.close()

    return 0


async def cmd_simulate(args: argparse.Namespace) -> int:
    """Run built-in Solution 2000 Mode 2 mock server."""
    port = args.port
    user_pin = args.pin
    host = args.bind

    sim = BoschSol2000Simulator(host=host, port=port, user_pin=user_pin)
    await sim.start()

    console.print(
        f"[bold green][+] Bosch Solution 2000 Simulator is running on {host}:{port}[/]"
    )
    console.print(f"[cyan]Accepted User PIN:[/] [bold]{user_pin}[/]")
    console.print(
        "[dim]Press Ctrl+C to stop. In another terminal, run: bosch-mode2 monitor --port {port}[/]"
    )

    async def auto_event_loop():
        """Trigger realistic, diverse periodic simulated events across all 8 zones and categories."""
        scenarios = [
            # 1. Front Door intrusion (Zone 1)
            {"action": "point", "pid": 1, "open": True, "desc": "Zone 1 (Front Door) OPENED -> Alarm"},
            {"action": "point", "pid": 1, "open": False, "desc": "Zone 1 (Front Door) CLOSED -> Normal Restore"},
            # 2. Living PIR detection (Zone 2)
            {"action": "point", "pid": 2, "open": True, "desc": "Zone 2 (Living PIR) MOTION -> Alarm"},
            {"action": "point", "pid": 2, "open": False, "desc": "Zone 2 (Living PIR) RESTORED -> Normal"},
            # 3. Master Bedroom PIR (Zone 3)
            {"action": "point", "pid": 3, "open": True, "desc": "Zone 3 (Master Bedroom) MOTION -> Alarm"},
            {"action": "point", "pid": 3, "open": False, "desc": "Zone 3 (Master Bedroom) RESTORED -> Normal"},
            # 4. Kitchen Window Trouble / Tamper (Zone 4)
            {"action": "trouble", "pid": 4, "trouble": True, "desc": "Zone 4 (Kitchen Window) LOOP TROUBLE / FAULT"},
            {"action": "trouble", "pid": 4, "trouble": False, "desc": "Zone 4 (Kitchen Window) TROUBLE RESTORED"},
            # 5. Back Door Bypass (Zone 5)
            {"action": "bypass", "pid": 5, "bypass": True, "desc": "Zone 5 (Back Door) BYPASSED by User 1"},
            {"action": "bypass", "pid": 5, "bypass": False, "desc": "Zone 5 (Back Door) UNBYPASS (Active)"},
            # 6. Garage PIR detection (Zone 6)
            {"action": "point", "pid": 6, "open": True, "desc": "Zone 6 (Garage PIR) MOTION -> Alarm"},
            {"action": "point", "pid": 6, "open": False, "desc": "Zone 6 (Garage PIR) RESTORED -> Normal"},
            # 7. Smoke Detector 24Hr Fire Alarm (Zone 7)
            {"action": "point", "pid": 7, "open": True, "desc": "Zone 7 (Smoke Detector) 24Hr FIRE ALARM TRIGGERED!"},
            {"action": "point", "pid": 7, "open": False, "desc": "Zone 7 (Smoke Detector) 24Hr FIRE ALARM RESTORED"},
            # 8. Emergency Panic Button Alarm (Zone 8)
            {"action": "point", "pid": 8, "open": True, "desc": "Zone 8 (Emergency Panic) 24Hr PANIC ALARM TRIGGERED!"},
            {"action": "point", "pid": 8, "open": False, "desc": "Zone 8 (Emergency Panic) 24Hr PANIC RESTORED"},
            # 9. Arming & Disarming Sequence
            {"action": "area", "status": 0x01, "desc": "Area 1 ARMED AWAY by User 1"},
            {"action": "point", "pid": 1, "open": True, "desc": "Zone 1 (Front Door) OPENED while Armed!"},
            {"action": "point", "pid": 1, "open": False, "desc": "Zone 1 (Front Door) CLOSED"},
            {"action": "area", "status": 0x04, "desc": "Area 1 DISARMED by User 1"},
            # 10. AC Power & System Events
            {"action": "ac_power", "fail": True, "desc": "AC Mains Power Failure (PLN Outage)"},
            {"action": "battery", "low": True, "desc": "System Battery Voltage Low"},
            {"action": "ac_power", "fail": False, "desc": "AC Mains Power Restored"},
            {"action": "battery", "low": False, "desc": "System Battery Restored"},
            # 11. Tamper & Auto Test
            {"action": "tamper", "tamper": True, "desc": "Panel Enclosure Tamper Switch Triggered"},
            {"action": "tamper", "tamper": False, "desc": "Panel Tamper Restored"},
            {"action": "event", "code": 118, "desc": "Comm Auto Test Report Sent"},
        ]

        idx = 0
        while True:
            await asyncio.sleep(args.auto_interval)
            step = scenarios[idx]
            act = step["action"]
            if act == "point":
                sim.trigger_point(step["pid"], step["open"])
            elif act == "trouble":
                sim.trigger_trouble(step["pid"], step["trouble"])
            elif act == "bypass":
                sim.trigger_bypass(step["pid"], step["bypass"])
            elif act == "area":
                sim.trigger_area(1, step["status"])
            elif act == "ac_power":
                sim.trigger_ac_power(step["fail"])
            elif act == "battery":
                sim.trigger_battery(step["low"])
            elif act == "tamper":
                sim.trigger_tamper(step["tamper"])
            elif act == "event":
                sim.add_history_event(code=step["code"])

            console.print(
                f"[dim][Sim Event #{sim._next_event_id - 1}][/] [bold yellow]{step['desc']}[/]"
            )
            idx = (idx + 1) % len(scenarios)

    auto_task = None
    if args.auto_events:
        console.print(
            f"[yellow]Auto event generator ACTIVE (interval: {args.auto_interval}s)[/]"
        )
        auto_task = asyncio.create_task(auto_event_loop())

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n[yellow]Stopping simulator...[/]")
    finally:
        if auto_task:
            auto_task.cancel()
        await sim.stop()

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bosch-mode2",
        description="CLI monitoring tool for Bosch Solution 2000/3000 intrusion alarms via Mode 2 Protocol",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "-c", "--config", help="Path to config YAML file (default: config.yaml)"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command: monitor
    p_mon = subparsers.add_parser("monitor", help="Live monitor dashboard and event stream")
    p_mon.add_argument("--host", help="Panel IP address / hostname")
    p_mon.add_argument("-p", "--port", type=int, help="Panel Mode 2 port (default: 7700)")
    p_mon.add_argument("--pin", help="User code override; normally entered in the setup prompt")
    p_mon.add_argument("--plain", action="store_true", help="Plain text stream instead of TUI")
    p_mon.add_argument("--interval", type=float, help="Polling interval in seconds")
    p_mon.add_argument(
        "--no-history", action="store_true", help="Do not load history log on initial connect"
    )
    _add_transport_option(p_mon)

    # Command: history
    p_hist = subparsers.add_parser("history", help="Fetch panel history transactions")
    p_hist.add_argument("--host", help="Panel IP address / hostname")
    p_hist.add_argument("-p", "--port", type=int, help="Panel Mode 2 port")
    p_hist.add_argument("--pin", help="User PIN code")
    p_hist.add_argument("--limit", type=int, default=50, help="Max records to show (default: 50)")
    p_hist.add_argument(
        "--format", choices=["table", "json", "csv"], default="table", help="Output format"
    )
    p_hist.add_argument(
        "--category",
        choices=["alarm", "restore", "arm_disarm", "trouble", "system"],
        help="Filter by category",
    )
    p_hist.add_argument("--search", help="Filter by substring")
    _add_transport_option(p_hist)

    # Command: status
    p_stat = subparsers.add_parser("status", help="Get snapshot of panel status")
    p_stat.add_argument("--host", help="Panel IP address / hostname")
    p_stat.add_argument("-p", "--port", type=int, help="Panel Mode 2 port")
    p_stat.add_argument("--pin", help="User PIN code")
    _add_transport_option(p_stat)

    # Command: raw
    p_raw = subparsers.add_parser("raw", help="Inspect and display raw Mode 2 protocol packets")
    p_raw.add_argument("--host", help="Panel IP address / hostname")
    p_raw.add_argument("-p", "--port", type=int, help="Panel Mode 2 port")
    p_raw.add_argument("--pin", help="User PIN code")
    p_raw.add_argument(
        "--mode", choices=["dump", "sniff"], default="dump", help="dump all endpoints or sniff live (default: dump)"
    )
    p_raw.add_argument(
        "--format", choices=["table", "hexdump", "json"], default="table", help="Output format"
    )
    p_raw.add_argument("--save", help="Path to save raw capture as JSON")
    p_raw.add_argument("--timeout", type=float, help="Sniffing timeout in seconds")

    # Command: simulate
    p_sim = subparsers.add_parser("simulate", help="Start local Solution 2000 mock server")
    p_sim.add_argument("--bind", default="127.0.0.1", help="Bind IP address (default: 127.0.0.1)")
    p_sim.add_argument("-p", "--port", type=int, default=7700, help="Port to listen (default: 7700)")
    p_sim.add_argument("--pin", default="1234", help="Accepted user PIN (default: 1234)")
    p_sim.add_argument(
        "--auto-events", action="store_true", help="Generate periodic test events"
    )
    p_sim.add_argument(
        "--auto-interval", type=float, default=3.0, help="Auto event interval in seconds"
    )

    return parser


async def main_async(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    if args.command == "monitor":
        return await cmd_monitor(args, cfg)
    elif args.command == "history":
        return await cmd_history(args, cfg)
    elif args.command == "status":
        return await cmd_status(args, cfg)
    elif args.command == "raw":
        return await cmd_raw(args, cfg)
    elif args.command == "simulate":
        return await cmd_simulate(args)
    else:
        return 1


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "WARNING"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = build_parser()
    args = parser.parse_args()
    cfg = load_config(args.config)

    try:
        code = asyncio.run(main_async(args, cfg))
        sys.exit(code)
    except ValueError as exc:
        console.print(f"[bold red]Input error:[/] {exc}")
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
