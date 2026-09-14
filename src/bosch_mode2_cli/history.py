from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any, Iterable, List, Optional

from rich.table import Table

from bosch_mode2_cli.models import EventCategory, TransactionRecord, categorize_event


def parse_history_tuple(event: Any) -> TransactionRecord:
    """Convert bosch_alarm_mode2.history.HistoryEvent to TransactionRecord."""
    # event is NamedTuple: id, date, message
    event_id = getattr(event, "id", 0)
    event_date = getattr(event, "date", datetime.now())
    event_msg = getattr(event, "message", str(event))

    return TransactionRecord(
        id=int(event_id),
        timestamp=event_date if isinstance(event_date, datetime) else datetime.now(),
        message=str(event_msg),
        category=categorize_event(str(event_msg)),
    )


def filter_transactions(
    records: Iterable[TransactionRecord],
    category: Optional[EventCategory] = None,
    search: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[TransactionRecord]:
    """Filter transactions by category or search substring."""
    filtered: List[TransactionRecord] = []
    search_lower = search.lower() if search else None

    for r in records:
        if category and r.category != category:
            continue
        if search_lower and search_lower not in r.message.lower():
            continue
        filtered.append(r)
        if limit and len(filtered) >= limit:
            break

    return filtered


def export_transactions_json(records: Iterable[TransactionRecord]) -> str:
    """Export transactions to JSON string."""
    data = [r.to_dict() for r in records]
    return json.dumps(data, indent=2)


def export_transactions_csv(records: Iterable[TransactionRecord]) -> str:
    """Export transactions to CSV string."""
    output = io.StringIO()
    writer = csv.DictWriter(
        output, fieldnames=["id", "timestamp", "category", "message"]
    )
    writer.writeheader()
    for r in records:
        writer.writerow(r.to_dict())
    return output.getvalue()


def create_transactions_table(
    records: Iterable[TransactionRecord], title: str = "Mode 2 Transactions Log"
) -> Table:
    """Format transactions list into a Rich Table."""
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Event ID", style="dim", width=10, justify="right")
    table.add_column("Timestamp", style="cyan", width=20)
    table.add_column("Category", width=14, justify="center")
    table.add_column("Event Description", style="bold white")

    category_colors = {
        EventCategory.ALARM: "[bold white on red]",
        EventCategory.RESTORE: "[bold green]",
        EventCategory.ARM_DISARM: "[bold blue]",
        EventCategory.TROUBLE: "[bold yellow]",
        EventCategory.SYSTEM: "[dim cyan]",
        EventCategory.UNKNOWN: "[dim]",
    }

    for r in records:
        color = category_colors.get(r.category, "[white]")
        cat_badge = f"{color} {r.category.value} [/]"
        table.add_row(
            str(r.id),
            r.formatted_time,
            cat_badge,
            r.message,
        )

    return table
