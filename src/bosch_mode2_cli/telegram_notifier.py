from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bosch_mode2_cli.models import EventCategory, TransactionRecord

_ZONE_PATTERN = re.compile(r"\b(?:ZONE|POINT)\s+(\d+)(?:\s*\(([^)]+)\))?", re.IGNORECASE)
_POINT_PATTERN = re.compile(r"\bPOINT\s*:\s*(\d+)", re.IGNORECASE)
_MAX_ZONE_NAME_LENGTH = 64


def _zone_id(message: str) -> int | None:
    match = _ZONE_PATTERN.search(message) or _POINT_PATTERN.search(message)
    return int(match.group(1)) if match else None


def _zone_label(message: str, settings: "ZoneSettings | None" = None) -> str:
    match = _ZONE_PATTERN.search(message)
    if not match:
        point = _POINT_PATTERN.search(message)
        if not point:
            return "Unknown"
        number = int(point.group(1))
        return f"Zone {number} — {settings.name_for(number)}" if settings else f"Zone {number}"
    number, name = match.groups()
    zone_id = int(number)
    custom = settings.name_for(zone_id) if settings else None
    return f"Zone {number} — {custom or name.strip()}" if (custom or name) else f"Zone {number}"


def format_telegram_message(panel_name: str, record: TransactionRecord, settings: "ZoneSettings | None" = None) -> str:
    """Create the small operational message used by the Telegram MVP."""
    title = "🚨 ALARM" if record.category == EventCategory.ALARM else "✅ RESTORE"
    return "\n".join(
        [
            title,
            "",
            f"Panel: {panel_name}",
            f"Zona: {_zone_label(record.message, settings)}",
            f"Waktu: {record.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
    )




class ZoneSettings:
    """Mutable Telegram-only zone notification settings."""

    def __init__(self, zones: dict[str, Any] | None = None, on_change: Callable[[], None] | None = None) -> None:
        self._zones: dict[int, dict[str, Any]] = {}
        self._on_change = on_change
        for raw_id, raw_value in (zones or {}).items():
            zone_id = int(raw_id)
            value = raw_value if isinstance(raw_value, dict) else {}
            self._zones[zone_id] = {
                "enabled": bool(value.get("enabled", True)),
                "name": str(value.get("name") or ""),
            }

    def _entry(self, zone_id: int) -> dict[str, Any]:
        return self._zones.setdefault(zone_id, {"enabled": True, "name": ""})

    def is_enabled(self, zone_id: int) -> bool:
        return bool(self._entry(zone_id)["enabled"])

    def set_enabled(self, zone_id: int, enabled: bool) -> None:
        self._entry(zone_id)["enabled"] = enabled
        if self._on_change:
            self._on_change()

    def name_for(self, zone_id: int) -> str:
        return str(self._entry(zone_id)["name"])

    def set_name(self, zone_id: int, name: str) -> None:
        clean = name.strip()
        if not clean:
            raise ValueError("Zone name cannot be empty")
        if len(clean) > _MAX_ZONE_NAME_LENGTH:
            raise ValueError(f"Zone name cannot exceed {_MAX_ZONE_NAME_LENGTH} characters")
        self._entry(zone_id)["name"] = clean
        if self._on_change:
            self._on_change()

    def rows(self) -> list[tuple[int, bool, str]]:
        return [(zone_id, bool(value["enabled"]), str(value["name"])) for zone_id, value in sorted(self._zones.items())]

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {str(zone_id): dict(value) for zone_id, value in sorted(self._zones.items())}


class TelegramBotController:
    """Handle allowlisted, Telegram-only configuration commands."""

    HELP = "\n".join([
        "/zones — daftar zona dan status notifikasi",
        "/zone_on <nomor> — aktifkan notifikasi zona",
        "/zone_off <nomor> — nonaktifkan notifikasi zona",
        "/zone_name <nomor> <nama> — ubah nama zona",
        "/settings — lihat pengaturan Telegram",
        "/status — lihat status filter zona",
        "/test_notification — kirim pesan uji",
        "/help — bantuan",
    ])

    def __init__(self, settings: ZoneSettings, allowed_chat_ids: set[int], send: Callable[[int, str], None]) -> None:
        self.settings = settings
        self.allowed_chat_ids = allowed_chat_ids
        self._send = send

    def handle_command(self, chat_id: int, text: str) -> bool:
        if chat_id not in self.allowed_chat_ids:
            return False
        parts = text.strip().split(maxsplit=2)
        command = parts[0].split("@", 1)[0].lower() if parts else ""
        try:
            if command == "/help":
                reply = self.HELP
            elif command == "/zones":
                rows = self.settings.rows()
                reply = "\n".join(f"{zone_id}. {name} — {'ON' if enabled else 'OFF'}" for zone_id, enabled, name in rows) or "Belum ada zona terdaftar."
            elif command in ("/settings", "/status"):
                enabled = sum(1 for _, active, _ in self.settings.rows() if active)
                reply = f"Filter zona Telegram: {enabled} aktif"
            elif command == "/test_notification":
                reply = "✅ Test notification berhasil."
            elif command in ("/zone_on", "/zone_off"):
                zone_id = int(parts[1])
                active = command == "/zone_on"
                self.settings.set_enabled(zone_id, active)
                reply = f"Notifikasi Zona {zone_id} {'diaktifkan' if active else 'dinonaktifkan'}."
            elif command == "/zone_name":
                zone_id = int(parts[1])
                self.settings.set_name(zone_id, parts[2])
                reply = f"Nama Zona {zone_id} diubah menjadi: {self.settings.name_for(zone_id)}"
            else:
                reply = "Perintah Tidak dikenal. Gunakan /help."
        except (IndexError, ValueError):
            reply = "Format perintah tidak valid. Gunakan /help."
        self._send(chat_id, reply)
        return True


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
        self.send_chat(self._chat_id, text)

    def send_chat(self, chat_id: int | str, text: str) -> None:
        payload = urlencode({"chat_id": str(chat_id), "text": text}).encode("utf-8")
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
    def get_updates(self, offset: int = 0, timeout: int = 10) -> list[dict[str, Any]]:
        query = urlencode({"offset": offset, "timeout": timeout})
        request = Request(f"{self._url.rsplit('/', 1)[0]}/getUpdates?{query}", method="GET")
        with self._urlopen(request, timeout=timeout + 5) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok", False):
            raise RuntimeError("Telegram rejected getUpdates")
        return list(result.get("result", []))


class TelegramUpdatesAPI(Protocol):
    def get_updates(self, offset: int = 0, timeout: int = 10) -> list[dict[str, Any]]:
        ...


class TelegramControlPoller:
    """Background long-poll loop for Telegram-only configuration commands."""

    def __init__(self, api: TelegramUpdatesAPI, controller: TelegramBotController, stop_event: Any) -> None:
        self.api = api
        self.controller = controller
        self.stop_event = stop_event
        self.offset = 0

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                for update in self.api.get_updates(self.offset, timeout=5):
                    self.offset = int(update.get("update_id", self.offset)) + 1
                    message = update.get("message") or {}
                    chat = message.get("chat") or {}
                    text = message.get("text")
                    if chat.get("id") is not None and text:
                        self.controller.handle_command(int(chat["id"]), str(text))
            except Exception:
                logging.getLogger(__name__).warning("Telegram command polling failed", exc_info=True)
                self.stop_event.wait(5)


class AlarmRestoreNotifier:
    """Filter live alarm/restore records and send each event once per process."""

    def __init__(self, panel_name: str, send: Callable[[str], None], settings: ZoneSettings | None = None) -> None:
        self.panel_name = panel_name
        self._send = send
        self.settings = settings or ZoneSettings()
        self.telegram_api: TelegramNotifier | None = None
        self.telegram_controller: TelegramBotController | None = None
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
        zone_id = _zone_id(record.message)
        if zone_id is not None and not self.settings.is_enabled(zone_id):
            return False

        key = self._key(record)
        if key in self._seen:
            return False
        self._seen.add(key)
        self._send(format_telegram_message(self.panel_name, record, self.settings))
        return True
