from __future__ import annotations

from typing import Any, Dict, List, Tuple

from rich.align import Align
from rich.box import ROUNDED
from rich.console import RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from bosch_mode2_cli.history import create_transactions_table
from bosch_mode2_cli.models import (
    AreaRecord,
    PanelSnapshot,
    PointRecord,
    TransactionRecord,
)


def render_header(snapshot: PanelSnapshot) -> Panel:
    """Render the top header banner."""
    status_text = (
        "[bold green]ONLINE[/]"
        if snapshot.connected
        else "[bold red]DISCONNECTED[/]"
    )
    title_text = (
        f"[bold white]BOSCH INTRUSION ALARM — MODE 2 MONITOR[/] | {status_text}"
    )

    info_text = (
        f"[cyan]Model:[/] {snapshot.model_name} ({snapshot.family})  |  "
        f"[cyan]Protocol:[/] {snapshot.protocol_version}  |  "
        f"[cyan]Firmware:[/] {snapshot.firmware_version or 'N/A'}  |  "
        f"[cyan]Faults:[/] {len(snapshot.faults)}"
    )

    content = Align.center(f"{title_text}\n{info_text}")
    return Panel(content, box=ROUNDED, style="blue")


def render_areas_table(areas: Dict[int, AreaRecord]) -> Table:
    """Render summary table of panel areas."""
    table = Table(
        title="[bold cyan]Areas / Partitions[/]",
        box=ROUNDED,
        show_header=True,
        header_style="bold blue",
        expand=True,
    )
    table.add_column("Area", justify="center", width=6)
    table.add_column("Name", style="bold")
    table.add_column("Arming Status", justify="center")
    table.add_column("Alarm", justify="center", width=8)

    if not areas:
        table.add_row("-", "No configured areas", "-", "-")
        return table

    for aid, area in sorted(areas.items()):
        if area.is_alarm:
            status_badge = "[bold white on red] ALARM [/]"
        elif area.is_armed:
            status_badge = "[bold blue] ARMED [/]"
        else:
            status_badge = "[bold green] DISARMED [/]"

        alarm_badge = "[bold red]YES[/]" if area.is_alarm else "[dim green]NO[/]"
        table.add_row(str(aid), area.name, status_badge, alarm_badge)

    return table


def render_points_table(points: Dict[int, PointRecord]) -> Table:
    """Render points (zones) grid table."""
    table = Table(
        title="[bold cyan]Zones / Points Status[/]",
        box=ROUNDED,
        show_header=True,
        header_style="bold blue",
        expand=True,
    )
    table.add_column("ID", justify="center", width=4)
    table.add_column("Zone Name", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Loop", justify="center", width=8)

    if not points:
        table.add_row("-", "No configured points", "-", "-")
        return table

    for pid, point in sorted(points.items()):
        if point.is_open:
            status_badge = "[bold yellow] OPEN [/]"
            loop_badge = "[bold yellow]OPEN[/]"
        elif point.is_normal:
            status_badge = "[bold green] NORMAL [/]"
            loop_badge = "[green]SEALED[/]"
        else:
            status_badge = f"[magenta]{point.status_text}[/]"
            loop_badge = "[dim]UNKNOWN[/]"

        table.add_row(str(pid), point.name, status_badge, loop_badge)

    return table


def build_dashboard_layout(
    snapshot: PanelSnapshot,
    transactions: List[TransactionRecord],
    max_history_rows: int = 12,
) -> Layout:
    """Assemble complete Rich dashboard layout."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="status_row", size=10),
        Layout(name="events_table"),
    )

    layout["header"].update(render_header(snapshot))

    layout["status_row"].split_row(
        Layout(name="areas", ratio=1),
        Layout(name="points", ratio=2),
    )
    layout["status_row"]["areas"].update(render_areas_table(snapshot.areas))
    layout["status_row"]["points"].update(render_points_table(snapshot.points))

    recent_events = transactions[-max_history_rows:]
    recent_events.reverse()  # Newest first
    layout["events_table"].update(
        create_transactions_table(
            recent_events,
            title=f"[bold cyan]Live Mode 2 Transactions ({len(transactions)} total captured)[/]",
        )
    )

    return layout


def format_plain_transaction(record: TransactionRecord) -> str:
    """Format single transaction for plain text stream."""
    return f"[{record.formatted_time}] #{record.id} [{record.category.value:^10}] {record.message}"


def format_raw_frame_line(frame: Any) -> str:
    """Single-line formatted string for live raw packet sniffing."""
    dir_badge = (
        "[bold cyan]TX >>[/]"
        if frame.direction == "TX"
        else "[bold magenta]<< RX[/]"
    )
    code_str = f"[{frame.code_name:^18}]"
    hex_preview = frame.hex_str
    if len(hex_preview) > 48:
        hex_preview = hex_preview[:45] + "..."

    return (
        f"[dim]{frame.formatted_time}[/] {dir_badge} {code_str} "
        f"P:{frame.protocol} L:{frame.length:02d} | [yellow]{hex_preview}[/] | [dim]{frame.decoded_info}[/]"
    )


def render_raw_exchange_table(
    pairs: List[Tuple[Any, Any]], title: str = "Mode 2 Raw Protocol Full Diagnostic Dump"
) -> Table:
    """Render comprehensive table of request-response raw frame exchanges."""
    table = Table(
        title=f"[bold cyan]{title}[/]",
        box=ROUNDED,
        show_header=True,
        header_style="bold magenta",
        expand=True,
    )
    table.add_column("#", justify="center", width=3, style="dim")
    table.add_column("Command / Endpoint", style="bold cyan", width=24)
    table.add_column("TX Hex Frame", style="yellow", width=22)
    table.add_column("RX Status", justify="center", width=12)
    table.add_column("RX Hex (Payload Sample)", style="green")
    table.add_column("Interpretation", style="white")

    for i, (tx, rx) in enumerate(pairs, 1):
        # Status styling
        if rx.code == 0xFC:
            status_style = "[bold green]ACK (0xFC)[/]"
        elif rx.code == 0xFD:
            status_style = "[bold red]NACK (0xFD)[/]"
        elif rx.code == 0xFE:
            status_style = "[bold blue]RESULT (0xFE)[/]"
        else:
            status_style = f"[magenta]0x{rx.code:02X}[/]" if rx.code else "[dim]PUSH[/]"

        rx_hex = rx.hex_str
        if len(rx_hex) > 36:
            rx_hex = rx_hex[:33] + "..."

        table.add_row(
            str(i),
            tx.code_name,
            tx.hex_str,
            status_style,
            rx_hex,
            rx.decoded_info,
        )

    return table
