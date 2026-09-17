from datetime import datetime
from urllib.parse import parse_qs

from bosch_mode2_cli.models import EventCategory, TransactionRecord
from bosch_mode2_cli.telegram_notifier import (
    AlarmRestoreNotifier,
    TelegramNotifier,
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
