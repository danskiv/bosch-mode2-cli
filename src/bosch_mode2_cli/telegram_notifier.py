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
_MIN_ZONE_ID = 1
_MAX_ZONE_ID = 999


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
        custom = settings.name_for(number) if settings else ""
        return f"Zone {number} — {custom}" if custom else f"Zone {number}"
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
            if not self.is_valid_zone_id(zone_id):
                continue
            value = raw_value if isinstance(raw_value, dict) else {}
            configured_name = str(value.get("name") or "").strip()
            self._zones[zone_id] = {
                "enabled": bool(value.get("enabled", True)),
                "name": configured_name[:_MAX_ZONE_NAME_LENGTH],
            }

    def _entry(self, zone_id: int) -> dict[str, Any]:
        if not self.is_valid_zone_id(zone_id):
            raise ValueError(f"Zone ID must be between {_MIN_ZONE_ID} and {_MAX_ZONE_ID}")
        return self._zones.setdefault(zone_id, {"enabled": True, "name": ""})

    @staticmethod
    def is_valid_zone_id(zone_id: int) -> bool:
        return _MIN_ZONE_ID <= zone_id <= _MAX_ZONE_ID

    def is_enabled(self, zone_id: int) -> bool:
        if not self.is_valid_zone_id(zone_id):
            return True
        return bool(self._entry(zone_id)["enabled"])

    def set_enabled(self, zone_id: int, enabled: bool) -> bool:
        entry = self._entry(zone_id)
        previous = dict(entry)
        entry["enabled"] = enabled
        try:
            if self._on_change:
                self._on_change()
        except Exception:
            entry.clear()
            entry.update(previous)
            raise
        return True

    def name_for(self, zone_id: int) -> str:
        if not self.is_valid_zone_id(zone_id):
            return ""
        return str(self._entry(zone_id)["name"])

    def set_name(self, zone_id: int, name: str) -> None:
        clean = name.strip()
        if not clean:
            raise ValueError("Zone name cannot be empty")
        if len(clean) > _MAX_ZONE_NAME_LENGTH:
            raise ValueError(f"Zone name cannot exceed {_MAX_ZONE_NAME_LENGTH} characters")
        entry = self._entry(zone_id)
        previous = dict(entry)
        entry["name"] = clean
        try:
            if self._on_change:
                self._on_change()
        except Exception:
            entry.clear()
            entry.update(previous)
            raise

    def rows(self) -> list[tuple[int, bool, str]]:
        return [(zone_id, bool(value["enabled"]), str(value["name"])) for zone_id, value in sorted(self._zones.items())]

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {str(zone_id): dict(value) for zone_id, value in sorted(self._zones.items())}

    def register_zone_ids(self, zone_ids: Any) -> None:
        """Add panel-discovered zone IDs without changing existing settings."""
        for zone_id in zone_ids:
            try:
                normalized = int(zone_id)
            except (TypeError, ValueError):
                continue
            if self.is_valid_zone_id(normalized):
                self._entry(normalized)


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
        "/menu — buka menu tombol",
        "/help — bantuan",
    ])

    def __init__(
        self,
        settings: ZoneSettings,
        allowed_chat_ids: set[int],
        send: Callable[..., None],
        answer_callback: Callable[..., None] | None = None,
        allowed_user_ids: set[int] | None = None,
    ) -> None:
        self.settings = settings
        self.allowed_chat_ids = allowed_chat_ids
        self._send = send
        self._answer_callback = answer_callback or (lambda *_args, **_kwargs: None)
        self.allowed_user_ids = allowed_user_ids or set()
        self._pending_rename: dict[tuple[int, int | None], int] = {}

    def _authorized(
        self, chat_id: int, user_id: int | None = None, chat_type: str | None = None
    ) -> bool:
        if chat_id not in self.allowed_chat_ids:
            return False
        if chat_id < 0 or chat_type in {"group", "supergroup"}:
            return user_id is not None and user_id in self.allowed_user_ids
        return True

    def _pending_key(self, chat_id: int, user_id: int | None) -> tuple[int, int | None]:
        return chat_id, user_id

    def _clear_pending(self, chat_id: int, user_id: int | None) -> None:
        self._pending_rename.pop(self._pending_key(chat_id, user_id), None)

    def _mutation_failed(self, chat_id: int) -> None:
        logging.getLogger(__name__).warning("Telegram configuration persistence failed", exc_info=True)
        self._send(chat_id, "Perubahan gagal disimpan. Pengaturan sebelumnya dipertahankan.")

    def _ack_callback(self, callback_id: str) -> None:
        try:
            self._answer_callback(callback_id)
        except Exception:
            logging.getLogger(__name__).warning("Telegram callback acknowledgement failed", exc_info=True)

    @staticmethod
    def _main_markup() -> dict[str, Any]:
        return {"inline_keyboard": [
            [{"text": "📋 Daftar Zona", "callback_data": "zones"}],
            [{"text": "⚙️ Pengaturan", "callback_data": "settings"}],
            [{"text": "📡 Status Filter", "callback_data": "status"}],
            [{"text": "🧪 Test Notification", "callback_data": "test"}],
        ]}

    def _send_menu(self, chat_id: int) -> None:
        self._send(chat_id, "Menu pengaturan notifikasi:", self._main_markup())

    def _send_zones(self, chat_id: int) -> None:
        rows = self.settings.rows()
        text = "Daftar zona — pilih untuk mengatur notifikasi:" if rows else "Belum ada zona terdaftar dari panel."
        markup = {"inline_keyboard": [
            [{"text": f"{zone_id}. {name or f'Zone {zone_id}'} — {'ON' if enabled else 'OFF'}", "callback_data": f"zone:{zone_id}"}]
            for zone_id, enabled, name in rows
        ] + [[{"text": "◀️ Menu", "callback_data": "menu"}]]}
        self._send(chat_id, text, markup)

    def _send_zone(self, chat_id: int, zone_id: int) -> None:
        enabled = self.settings.is_enabled(zone_id)
        name = self.settings.name_for(zone_id) or f"Zone {zone_id}"
        markup = {"inline_keyboard": [
            [{"text": "✅ Aktifkan", "callback_data": f"zone_on:{zone_id}"}],
            [{"text": "🔕 Nonaktifkan", "callback_data": f"zone_off:{zone_id}"}],
            [{"text": "✏️ Ubah Nama", "callback_data": f"zone_rename:{zone_id}"}],
            [{"text": "◀️ Kembali", "callback_data": "zones"}],
        ]}
        self._send(chat_id, f"Zona {zone_id} — {name}\nStatus notifikasi: {'ON' if enabled else 'OFF'}", markup)

    def handle_command(
        self, chat_id: int, text: str, user_id: int | None = None, chat_type: str | None = None
    ) -> bool:
        if not self._authorized(chat_id, user_id, chat_type):
            return False
        parts = text.strip().split(maxsplit=2)
        self._clear_pending(chat_id, user_id)
        command = parts[0].split("@", 1)[0].lower() if parts else ""
        try:
            if command == "/help":
                reply = self.HELP
            elif command in ("/menu", "/start"):
                self._send_menu(chat_id)
                return True
            elif command == "/cancel":
                self._send(chat_id, "Aksi dibatalkan.")
                return True
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
                try:
                    self.settings.set_enabled(zone_id, active)
                except ValueError as exc:
                    self._send(chat_id, str(exc))
                    return True
                except Exception:
                    self._mutation_failed(chat_id)
                    return True
                reply = f"Notifikasi Zona {zone_id} {'diaktifkan' if active else 'dinonaktifkan'}."
            elif command == "/zone_name":
                zone_id = int(parts[1])
                try:
                    self.settings.set_name(zone_id, parts[2])
                except ValueError as exc:
                    self._send(chat_id, str(exc))
                    return True
                except Exception:
                    self._mutation_failed(chat_id)
                    return True
                reply = f"Nama Zona {zone_id} diubah menjadi: {self.settings.name_for(zone_id)}"
            else:
                reply = "Perintah Tidak dikenal. Gunakan /help."
        except (IndexError, ValueError):
            reply = "Format perintah tidak valid. Gunakan /help."
        self._send(chat_id, reply)
        return True

    def handle_callback(
        self,
        chat_id: int,
        callback_id: str,
        data: str,
        user_id: int | None = None,
        chat_type: str | None = None,
    ) -> bool:
        self._ack_callback(callback_id)
        if not self._authorized(chat_id, user_id, chat_type):
            return False
        try:
            if data.startswith(("zone:", "zone_on:", "zone_off:", "zone_rename:")):
                zone_id = int(data.split(":", 1)[1])
                if not self.settings.is_valid_zone_id(zone_id):
                    return False
            self._clear_pending(chat_id, user_id)
            if data == "menu":
                self._send_menu(chat_id)
            elif data == "zones":
                self._send_zones(chat_id)
            elif data == "settings":
                enabled = sum(1 for _, active, _ in self.settings.rows() if active)
                self._send(chat_id, f"Filter zona Telegram: {enabled} aktif", self._main_markup())
            elif data == "status":
                enabled = sum(1 for _, active, _ in self.settings.rows() if active)
                self._send(chat_id, f"Filter zona Telegram: {enabled} aktif")
            elif data == "test":
                self._send(chat_id, "✅ Test notification berhasil.")
            elif data.startswith("zone:"):
                self._send_zone(chat_id, int(data.split(":", 1)[1]))
            elif data.startswith("zone_on:") or data.startswith("zone_off:"):
                zone_id = int(data.split(":", 1)[1])
                active = data.startswith("zone_on:")
                try:
                    self.settings.set_enabled(zone_id, active)
                except Exception:
                    self._mutation_failed(chat_id)
                    return True
                self._send_zone(chat_id, zone_id)
            elif data.startswith("zone_rename:"):
                zone_id = int(data.split(":", 1)[1])
                self._pending_rename[self._pending_key(chat_id, user_id)] = zone_id
                self._send(chat_id, f"Ketik nama baru untuk Zona {zone_id}:")
            else:
                return False
        except ValueError:
            return False
        except IndexError:
            self._send(chat_id, "Pengaturan zona tidak valid.")
        return True

    def handle_text(
        self, chat_id: int, text: str, user_id: int | None = None, chat_type: str | None = None
    ) -> bool:
        key = self._pending_key(chat_id, user_id)
        if not self._authorized(chat_id, user_id, chat_type) or key not in self._pending_rename:
            return False
        zone_id = self._pending_rename[key]
        try:
            self.settings.set_name(zone_id, text)
        except ValueError as exc:
            self._send(chat_id, str(exc))
            return True
        except Exception:
            self._mutation_failed(chat_id)
            return True
        del self._pending_rename[key]
        self._send_zone(chat_id, zone_id)
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

    def _call(self, method: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = urlencode({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value) for key, value in (values or {}).items()}).encode("utf-8")
        request = Request(
            f"{self._url.rsplit('/', 1)[0]}/{method}",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with self._urlopen(request, timeout=self._timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok", False):
            raise RuntimeError(f"Telegram rejected {method}")
        return result

    def send_chat(self, chat_id: int | str, text: str, reply_markup: dict[str, Any] | None = None) -> None:
        values: dict[str, Any] = {"chat_id": str(chat_id), "text": text}
        if reply_markup is not None:
            values["reply_markup"] = reply_markup
        self._call("sendMessage", values)

    def answer_callback(self, callback_id: str, text: str | None = None) -> None:
        values: dict[str, Any] = {"callback_query_id": callback_id}
        if text:
            values["text"] = text
        self._call("answerCallbackQuery", values)

    def set_my_commands(self) -> None:
        commands = [
            {"command": "menu", "description": "Buka menu tombol"},
            {"command": "zones", "description": "Daftar zona"},
            {"command": "settings", "description": "Pengaturan notifikasi"},
            {"command": "status", "description": "Status filter zona"},
            {"command": "test_notification", "description": "Kirim pesan uji"},
            {"command": "help", "description": "Bantuan"},
        ]
        self._call("setMyCommands", {"commands": commands})

    def get_updates(self, offset: int = 0, timeout: int = 10) -> list[dict[str, Any]]:
        query = urlencode({"offset": offset, "timeout": timeout, "allowed_updates": json.dumps(["message", "callback_query"])})
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
                        chat_id = int(chat["id"])
                        sender = message.get("from") or {}
                        user_id = int(sender["id"]) if sender.get("id") is not None else None
                        chat_type = str(chat.get("type") or "")
                        if str(text).strip().startswith("/"):
                            self.controller.handle_command(chat_id, str(text), user_id, chat_type)
                        else:
                            self.controller.handle_text(chat_id, str(text), user_id, chat_type)
                    callback = update.get("callback_query") or {}
                    callback_message = callback.get("message") or {}
                    callback_chat = callback_message.get("chat") or {}
                    if callback.get("id") and callback_chat.get("id") is not None:
                        sender = callback.get("from") or {}
                        self.controller.handle_callback(
                            int(callback_chat["id"]),
                            str(callback["id"]),
                            str(callback.get("data") or ""),
                            int(sender["id"]) if sender.get("id") is not None else None,
                            str(callback_chat.get("type") or ""),
                        )
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
