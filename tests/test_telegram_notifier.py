from datetime import datetime
from urllib.parse import parse_qs

from bosch_mode2_cli.models import EventCategory, TransactionRecord
from bosch_mode2_cli.telegram_notifier import (
    AlarmRestoreNotifier,
    TelegramNotifier,
    TelegramBotController,
    ZoneSettings,
    format_telegram_message,
)


def event(event_id: int, message: str, category: EventCategory) -> TransactionRecord:
    return TransactionRecord(
        id=event_id,
        timestamp=datetime(2026, 9, 16, 14, 32, 8),
        message=message,
        category=category,
    )


def test_alarm_message_contains_zone_and_event_time():
    record = event(1, "Zone 3 (Front Door) BURGLARY ALARM", EventCategory.ALARM)

    text = format_telegram_message("Solution 2000", record)

    assert "ALARM" in text
    assert "Zone 3 — Front Door" in text
    assert "2026-09-16 14:32:08" in text


def test_restore_message_contains_zone_and_event_time():
    record = event(2, "Zone 3 (Front Door) BURGLARY RESTORED", EventCategory.RESTORE)

    text = format_telegram_message("Solution 2000", record)

    assert "RESTORE" in text
    assert "Zone 3 — Front Door" in text
    assert "2026-09-16 14:32:08" in text


def test_upstream_alarm_message_extracts_point_as_zone():
    record = event(3, "Alarm, Area: 1, Point: 3", EventCategory.ALARM)

    text = format_telegram_message("Solution 2000", record)

    assert "Zona: Zone 3" in text


def test_upstream_restoral_message_is_classified_as_restore():
    record = event(4, "Restoral, Area: 1, Point: 3", EventCategory.UNKNOWN)

    assert record.category == EventCategory.RESTORE


def test_processor_ignores_other_categories_and_deduplicates():
    sent = []
    notifier = AlarmRestoreNotifier("Solution 2000", sent.append)
    alarm = event(1, "Zone 3 (Front Door) ALARM", EventCategory.ALARM)
    trouble = event(2, "Zone 3 Trouble", EventCategory.TROUBLE)

    assert notifier.process(trouble) is False
    assert notifier.process(alarm) is True
    assert notifier.process(alarm) is False
    assert len(sent) == 1


def test_processor_can_prime_initial_history_without_sending():
    sent = []
    notifier = AlarmRestoreNotifier("Solution 2000", sent.append)
    old_alarm = event(1, "Zone 3 (Front Door) ALARM", EventCategory.ALARM)

    notifier.prime([old_alarm])

    assert notifier.process(old_alarm) is False
    assert sent == []


def test_disabled_zone_is_not_sent_and_custom_name_is_used():
    sent = []
    settings = ZoneSettings({"3": {"enabled": False, "name": "Kamar Utama"}})
    notifier = AlarmRestoreNotifier("Solution 2000", sent.append, settings=settings)
    alarm = event(3, "Alarm, Area: 1, Point: 3", EventCategory.ALARM)

    assert notifier.process(alarm) is False
    settings.set_enabled(3, True)
    assert notifier.process(alarm) is True
    assert "Zona: Zone 3 — Kamar Utama" in sent[0]


def test_telegram_control_commands_update_zone_settings():
    replies = []
    settings = ZoneSettings({"3": {"enabled": True, "name": "Old Name"}})
    control = TelegramBotController(
        settings=settings,
        allowed_chat_ids={1065735978},
        send=lambda chat_id, text: replies.append((chat_id, text)),
    )

    assert control.handle_command(1065735978, "/zone_off 3") is True
    assert settings.is_enabled(3) is False
    assert control.handle_command(1065735978, "/zone_name 3 Kamar Utama") is True
    assert settings.name_for(3) == "Kamar Utama"
    assert control.handle_command(999, "/zone_on 3") is False
    assert settings.is_enabled(3) is False
    assert any("dinonaktifkan" in text for _, text in replies)


def test_telegram_control_help_and_unknown_command():
    replies = []
    control = TelegramBotController(
        settings=ZoneSettings({}),
        allowed_chat_ids={1},
        send=lambda chat_id, text: replies.append(text),
    )

    assert control.handle_command(1, "/help") is True
    assert control.handle_command(1, "/unknown") is True
    assert any("/zone_on" in text for text in replies)
    assert any("Tidak dikenal" in text for text in replies)


def test_telegram_api_can_send_to_command_chat_and_read_updates():
    requests = []

    class Response:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self.body

    def fake_urlopen(request, timeout):
        requests.append((request.full_url, timeout))
        if "getUpdates?" in request.full_url:
            return Response(b'{"ok":true,"result":[{"update_id":7,"message":{"chat":{"id":1},"text":"/help"}}]}')
        return Response(b'{"ok":true}')

    notifier = TelegramNotifier("test-token", "12345", urlopen=fake_urlopen)
    notifier.send_chat(1, "reply")
    updates = notifier.get_updates(offset=7, timeout=1)

    assert updates[0]["update_id"] == 7
    assert requests[0][0].endswith("sendMessage")
    assert "offset=7" in requests[1][0]


def test_zone_settings_change_callback_is_called():
    changes = []
    settings = ZoneSettings({}, on_change=lambda: changes.append(settings.as_dict()))

    settings.set_enabled(3, False)
    settings.set_name(3, "Kamar Utama")

    assert len(changes) == 2
    assert changes[-1]["3"]["name"] == "Kamar Utama"


def test_telegram_notifier_posts_form_encoded_message_without_real_network():
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok":true}'

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return Response()

    notifier = TelegramNotifier(
        token="test-token",
        chat_id="12345",
        urlopen=fake_urlopen,
    )
    notifier.send("hello from test")

    assert len(requests) == 1
    request, timeout = requests[0]
    assert request.full_url.endswith("/bottest-token/sendMessage")
    assert timeout == 10
    body = parse_qs(request.data.decode("utf-8"))
    assert body == {"chat_id": ["12345"], "text": ["hello from test"]}
