from __future__ import annotations

import argparse
import asyncio
import logging
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

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
from bosch_mode2_cli.ui import (
    build_dashboard_layout,
    format_plain_transaction,
    format_raw_frame_line,
    render_areas_table,
    render_header,
    render_points_table,
    render_raw_exchange_table,
)

console = Console()


def load_config(config_path: Optional[str]) -> Dict[str, Any]:
    """Load configuration from YAML file if available."""
    target_path = config_path or "config.yaml"
    p = Path(target_path)
    if p.is_file():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return data
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read config file {p}: {e}[/]")
    return {}


async def cmd_monitor(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    """Run real-time Mode 2 monitor."""
    panel_cfg = cfg.get("panel", {})
    monitor_cfg = cfg.get("monitor", {})

    host = args.host or panel_cfg.get("host", "127.0.0.1")
    port = args.port or panel_cfg.get("port", 7700)
    user_pin = args.pin or panel_cfg.get("user_pin", "1234")
    plain_mode = args.plain or monitor_cfg.get("mode") == "plain"
    poll_interval = args.interval or monitor_cfg.get("poll_interval", 1.0)
    load_history = not args.no_history

    client = BoschSol2000Client(host=host, port=port, user_pin=user_pin)

    if plain_mode:
        console.print(
            f"[bold blue]Starting plain-text Mode 2 stream for Bosch Sol2000 at {host}:{port}...[/]"
        )

        def on_plain_tx(rec):
            console.print(format_plain_transaction(rec))

        def on_point(pt):
            console.print(
                f"[dim]{pt.last_updated.strftime('%H:%M:%S')}[/] [cyan]Point {pt.id} ({pt.name}):[/] {pt.status_text}"
            )

        def on_area(ar):
            console.print(
                f"[dim]{ar.last_updated.strftime('%H:%M:%S')}[/] [magenta]Area {ar.id} ({ar.name}):[/] {ar.status_text}"
            )

        client.on_transaction = on_plain_tx
        client.on_point_update = on_point
        client.on_area_update = on_area

        try:
            await client.connect(load_history=load_history)
            while True:
                await asyncio.sleep(poll_interval)
        except (KeyboardInterrupt, asyncio.CancelledError):
            console.print("\n[yellow]Stopping monitor...[/]")
        finally:
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
            await client.disconnect()

    return 0


async def cmd_history(args: argparse.Namespace, cfg: Dict[str, Any]) -> int:
    """Fetch history / transaction log."""
    panel_cfg = cfg.get("panel", {})
    host = args.host or panel_cfg.get("host", "127.0.0.1")
    port = args.port or panel_cfg.get("port", 7700)
    user_pin = args.pin or panel_cfg.get("user_pin", "1234")

    client = BoschSol2000Client(host=host, port=port, user_pin=user_pin)
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
    host = args.host or panel_cfg.get("host", "127.0.0.1")
    port = args.port or panel_cfg.get("port", 7700)
    user_pin = args.pin or panel_cfg.get("user_pin", "1234")

    client = BoschSol2000Client(host=host, port=port, user_pin=user_pin)
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
    host = args.host or panel_cfg.get("host", "127.0.0.1")
    port = args.port or panel_cfg.get("port", 7700)
    user_pin = args.pin or panel_cfg.get("user_pin", "1234")

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
                f"[bold green]✓ Sniffing live raw Mode 2 frames on {host}:{port}...[/]"
            )
            console.print("[dim]Press Ctrl+C to stop listening.[/]\n")
            raw_client.on_frame = lambda f: console.print(format_raw_frame_line(f))
            await raw_client.sniff_loop(timeout=args.timeout)
        else:
            # Mode: dump
            console.print(
                f"[bold green]✓ Executing full raw Mode 2 diagnostic sequence against {host}:{port}...[/]\n"
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
        f"[bold green]✓ Bosch Solution 2000 Simulator is running on {host}:{port}[/]"
    )
    console.print(f"[cyan]Accepted User PIN:[/] [bold]{user_pin}[/]")
    console.print(
        "[dim]Press Ctrl+C to stop. In another terminal, run: bosch-mode2 monitor --port {port}[/]"
    )

    async def auto_event_loop():
        """Optionally trigger periodic simulated events."""
        point_id = 1
        is_open = True
        while True:
            await asyncio.sleep(args.auto_interval)
            sim.trigger_point(point_id, is_open)
            state_str = "OPEN / ALARM" if is_open else "RESTORED / NORMAL"
            console.print(
                f"[dim][Sim Event][/] Zone {point_id} changed to {state_str}"
            )
            is_open = not is_open
            if not is_open:
                point_id = (point_id % 4) + 1

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
        description="CLI monitoring tool for Bosch Solution 2000 Intrusion Alarm via Mode 2 Protocol",
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
    p_mon.add_argument("--pin", help="User PIN code (e.g. 1234)")
    p_mon.add_argument("--plain", action="store_true", help="Plain text stream instead of TUI")
    p_mon.add_argument("--interval", type=float, help="Polling interval in seconds")
    p_mon.add_argument(
        "--no-history", action="store_true", help="Do not load history log on initial connect"
    )

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

    # Command: status
    p_stat = subparsers.add_parser("status", help="Get snapshot of panel status")
    p_stat.add_argument("--host", help="Panel IP address / hostname")
    p_stat.add_argument("-p", "--port", type=int, help="Panel Mode 2 port")
    p_stat.add_argument("--pin", help="User PIN code")

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


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "WARNING"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = build_parser()
    args = parser.parse_args()
    cfg = load_config(args.config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        if args.command == "monitor":
            code = loop.run_until_complete(cmd_monitor(args, cfg))
        elif args.command == "history":
            code = loop.run_until_complete(cmd_history(args, cfg))
        elif args.command == "status":
            code = loop.run_until_complete(cmd_status(args, cfg))
        elif args.command == "raw":
            code = loop.run_until_complete(cmd_raw(args, cfg))
        elif args.command == "simulate":
            code = loop.run_until_complete(cmd_simulate(args))
        else:
            parser.print_help()
            code = 1
        sys.exit(code)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
