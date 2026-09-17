from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bosch_mode2_cli.models import EventCategory, TransactionRecord

_ZONE_PATTERN = re.compile(r"\b(?:ZONE|POINT)\s+(\d+)(?:\s*\(([^)]+)\))?", re.IGNORECASE)
_POINT_PATTERN = re.compile(r"\bPOINT\s*:\s*(\d+)", re.IGNORECASE)


def _zone_label(message: str) -> str:
    match = _ZONE_PATTERN.search(message)
    if not match:
        point = _POINT_PATTERN.search(message)
        return f"Zone {point.group(1)}" if point else "Unknown"
    number, name = match.groups()
    return f"Zone {number} — {name.strip()}" if name else f"Zone {number}"


def format_telegram_message(panel_name: str, record: TransactionRecord) -> str:
    """Create the small operational message used by the Telegram MVP."""
    title = "🚨 ALARM" if record.category == EventCategory.ALARM else "✅ RESTORE"
    return "\n".join(
        [
            title,
            "",
            f"Panel: {panel_name}",
            f"Zona: {_zone_label(record.message)}",
            f"Waktu: {record.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
    )


class TelegramNotifier:
    """Small synchronous Telegram Bot API client for the monitor callback."""

    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        timeout: float = 10,
        urlopen: Callable[..., Any] = urlopen,
    ) -> None:
        if not token or not chat_id:
            raise ValueError("Telegram token and chat ID are required")
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat_id = str(chat_id)
        self._timeout = timeout
        self._urlopen = urlopen

    def send(self, text: str) -> None:
        payload = urlencode({"chat_id": self._chat_id, "text": text}).encode("utf-8")
        request = Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with self._urlopen(request, timeout=self._timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok", False):
            raise RuntimeError("Telegram rejected the notification")


class AlarmRestoreNotifier:
    """Filter live alarm/restore records and send each event once per process."""

    def __init__(self, panel_name: str, send: Callable[[str], None]) -> None:
        self.panel_name = panel_name
        self._send = send
        self._seen: set[object] = set()

    def prime(self, records: list[TransactionRecord]) -> None:
        """Mark initial history as known without sending notifications."""
        for record in records:
            if record.category in (EventCategory.ALARM, EventCategory.RESTORE):
                self._seen.add(self._key(record))

    @staticmethod
    def _key(record: TransactionRecord) -> object:
        return record.id if record.id > 0 else (
            record.category.value,
            record.timestamp,
            record.message,
        )

    def process(self, record: TransactionRecord) -> bool:
        if record.category not in (EventCategory.ALARM, EventCategory.RESTORE):
            return False

        key = self._key(record)
        if key in self._seen:
            return False
        self._seen.add(key)
        self._send(format_telegram_message(self.panel_name, record))
        return True
