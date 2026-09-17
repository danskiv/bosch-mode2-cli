from datetime import datetime
from urllib.parse import parse_qs
import json

from bosch_mode2_cli.models import EventCategory, TransactionRecord
from bosch_mode2_cli.telegram_notifier import (
    AlarmRestoreNotifier,
    TelegramNotifier,
    TelegramBotController,
    TelegramControlPoller,
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


def test_menu_command_returns_main_inline_keyboard():
    replies = []
    control = TelegramBotController(
        settings=ZoneSettings({"3": {"enabled": True, "name": "Kamar Utama"}}),
        allowed_chat_ids={1},
        send=lambda chat_id, text, markup=None: replies.append((chat_id, text, markup)),
    )

    assert control.handle_command(1, "/menu") is True
    assert replies[0][1] == "Menu pengaturan notifikasi:"
    assert replies[0][2]["inline_keyboard"]
    assert replies[0][2]["inline_keyboard"][0][0]["callback_data"] == "zones"


def test_zone_callback_can_toggle_and_request_rename():
    replies = []
    callbacks = []
    settings = ZoneSettings({"3": {"enabled": True, "name": "Kamar Utama"}})
    control = TelegramBotController(
        settings=settings,
        allowed_chat_ids={1},
        send=lambda chat_id, text, markup=None: replies.append((chat_id, text, markup)),
        answer_callback=lambda callback_id: callbacks.append(callback_id),
    )

    assert control.handle_callback(1, "cb-1", "zone_off:3") is True
    assert settings.is_enabled(3) is False
    assert control.handle_callback(1, "cb-2", "zone_rename:3") is True
    assert control.handle_text(1, "Kamar Baru") is True
    assert settings.name_for(3) == "Kamar Baru"
    assert callbacks == ["cb-1", "cb-2"]
    assert any("Kamar Baru" in text for _, text, _ in replies)


def test_unauthorized_callback_and_text_do_not_change_settings():
    replies = []
    control = TelegramBotController(
        settings=ZoneSettings({"3": {"enabled": True, "name": "Old"}}),
        allowed_chat_ids={1},
        send=lambda chat_id, text, markup=None: replies.append((chat_id, text, markup)),
    )

    assert control.handle_callback(999, "cb", "zone_off:3") is False
    assert control.handle_text(999, "New") is False
    assert control.settings.is_enabled(3) is True


def test_group_chat_requires_allowlisted_user_id():
    settings = ZoneSettings({"3": {"enabled": True}})
    replies = []
    control = TelegramBotController(
        settings, {100}, lambda *args: replies.append(args), allowed_user_ids={200}
    )

    assert control.handle_callback(100, "cb", "zone_off:3", user_id=201, chat_type="group") is False
    assert control.handle_callback(100, "cb", "zone_off:3", user_id=200, chat_type="group") is True
    assert settings.is_enabled(3) is False


def test_group_rename_is_bound_to_the_user_who_started_it():
    settings = ZoneSettings({"3": {"name": "Old"}})
    control = TelegramBotController(settings, {100}, lambda *_args: None, allowed_user_ids={200, 201})

    assert control.handle_callback(100, "cb", "zone_rename:3", user_id=200, chat_type="group") is True
    assert control.handle_text(100, "Wrong User", user_id=201, chat_type="group") is False
    assert control.handle_text(100, "Correct User", user_id=200, chat_type="group") is True
    assert settings.name_for(3) == "Correct User"


def test_negative_chat_id_requires_user_allowlist_even_without_chat_type():
    settings = ZoneSettings({"3": {"enabled": True}})
    control = TelegramBotController(settings, {-100}, lambda *_args: None, allowed_user_ids={200})

    assert control.handle_callback(-100, "cb", "zone_off:3", user_id=None, chat_type=None) is False
    assert settings.is_enabled(3) is True


def test_zone_ids_reject_zero_negative_and_oversized_values():
    settings = ZoneSettings()

    for zone_id in (0, -1, 1000):
        try:
            settings.set_enabled(zone_id, False)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid zone ID was accepted")
    assert settings.as_dict() == {}


def test_panel_zone_catalog_accepts_zone_nine_without_crashing():
    settings = ZoneSettings()
    settings.register_zone_ids([1, 9, 1000, "not-a-zone"])

    assert settings.name_for(9) == ""
    assert "9" in settings.as_dict()
    assert "1000" not in settings.as_dict()


def test_unknown_zone_label_has_no_empty_separator():
    text = format_telegram_message(
        "Solution 2000", event(9, "Alarm, Area: 1, Point: 1000", EventCategory.ALARM), ZoneSettings()
    )

    assert "Zona: Zone 1000" in text
    assert "Zone 1000 —" not in text


def test_notification_for_zone_nine_uses_safe_default():
    sent = []
    notifier = AlarmRestoreNotifier("Solution 2000", sent.append, settings=ZoneSettings())

    assert notifier.process(event(9, "Alarm, Area: 1, Point: 9", EventCategory.ALARM)) is True
    assert "Zone 9" in sent[0]


def test_notification_for_unknown_zone_does_not_crash_or_drop_event():
    sent = []
    notifier = AlarmRestoreNotifier("Solution 2000", sent.append, settings=ZoneSettings())

    assert notifier.process(event(1000, "Alarm, Area: 1, Point: 1000", EventCategory.ALARM)) is True
    assert "Zone 1000" in sent[0]


def test_invalid_zone_config_is_filtered_from_catalog():
    settings = ZoneSettings({"0": {"name": "Invalid"}, "3": {"name": "Valid"}, "1000": {"name": "Invalid"}})

    assert settings.as_dict() == {"3": {"enabled": True, "name": "Valid"}}


def test_pending_rename_is_cancelled_by_commands_navigation_and_cancel():
    replies = []
    settings = ZoneSettings({"3": {"name": "Old"}})
    control = TelegramBotController(settings, {1}, lambda *args: replies.append(args))

    control.handle_callback(1, "cb", "zone_rename:3")
    control.handle_command(1, "/zones")
    assert control.handle_text(1, "Must Not Apply") is False
    control.handle_callback(1, "cb2", "zone_rename:3")
    assert control.handle_command(1, "/cancel") is True
    assert control.handle_text(1, "Must Not Apply") is False
    assert settings.name_for(3) == "Old"


def test_invalid_zone_command_reports_validation_error_not_persistence_failure():
    replies = []
    control = TelegramBotController(ZoneSettings(), {1}, lambda *args: replies.append(args))

    assert control.handle_command(1, "/zone_on 1000") is True
    assert "between" in replies[-1][1]
    assert "gagal disimpan" not in replies[-1][1].lower()


def test_settings_callback_shows_summary_and_leading_space_command_works():
    replies = []
    control = TelegramBotController(ZoneSettings({"3": {"enabled": True}}), {1}, lambda *args: replies.append(args))

    control.handle_callback(1, "cb", "settings")
    control.handle_command(1, "   /menu")

    assert "aktif" in replies[0][1]
    assert replies[1][1] == "Menu pengaturan notifikasi:"


def test_malformed_zone_callback_is_rejected_without_state_change():
    answers = []
    settings = ZoneSettings({"3": {"enabled": True}})
    control = TelegramBotController(settings, {1}, lambda *args: None, lambda callback_id: answers.append(callback_id))

    assert control.handle_callback(1, "cb", "zone_off:-1") is False
    assert control.handle_callback(1, "cb2", "zone_off:not-a-number") is False
    assert settings.as_dict() == {"3": {"enabled": True, "name": ""}}
    assert answers == ["cb", "cb2"]


def test_callback_ack_failure_does_not_abort_zone_toggle():
    settings = ZoneSettings({"3": {"enabled": True}})
    control = TelegramBotController(
        settings, {1}, lambda *_args: None,
        lambda _callback_id: (_ for _ in ()).throw(OSError("network")),
    )

    assert control.handle_callback(1, "cb", "zone_off:3") is True
    assert settings.is_enabled(3) is False


def test_persistence_failure_rolls_back_and_replies():
    replies = []
    settings = ZoneSettings(
        {"3": {"enabled": True}},
        on_change=lambda: (_ for _ in ()).throw(OSError("disk full")),
    )
    control = TelegramBotController(settings, {1}, lambda *args: replies.append(args))

    assert control.handle_command(1, "/zone_off 3") is True
    assert settings.is_enabled(3) is True
    assert "gagal disimpan" in replies[-1][1].lower()


def test_telegram_api_registers_menu_and_limits_update_types():
    requests = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return b'{"ok":true,"result":[]}'

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return Response()

    notifier = TelegramNotifier("test-token", "12345", urlopen=fake_urlopen)
    notifier.set_my_commands()
    notifier.get_updates(timeout=1)

    menu_body = parse_qs(requests[0][0].data.decode())
    update_body = requests[1][0].full_url
    assert json.loads(menu_body["commands"][0])[0]["command"] == "menu"
    assert "allowed_updates=%5B%22message%22%2C+%22callback_query%22%5D" in update_body


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
    assert requests[0][0].endswith("/sendMessage")
    assert "offset=7" in requests[1][0]


def test_zone_settings_change_callback_is_called():
    changes = []
    settings = ZoneSettings({}, on_change=lambda: changes.append(settings.as_dict()))

    settings.set_enabled(3, False)
    settings.set_name(3, "Kamar Utama")

    assert len(changes) == 2
    assert changes[-1]["3"]["name"] == "Kamar Utama"


def test_zone_name_rejects_oversized_input():
    settings = ZoneSettings()

    try:
        settings.set_name(3, "x" * 65)
    except ValueError as exc:
        assert "64" in str(exc)
    else:
        raise AssertionError("oversized zone name was accepted")


def test_existing_oversized_zone_name_is_bounded_when_loaded():
    settings = ZoneSettings({"3": {"name": "x" * 80}})

    assert len(settings.name_for(3)) == 64


def test_control_poller_advances_offset_and_honors_stop_event():
    class StopEvent:
        def __init__(self):
            self.stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, _seconds):
            self.stopped = True

        def set(self):
            self.stopped = True

    class Api:
        def __init__(self, stop_event):
            self.calls = []
            self.stop_event = stop_event

        def get_updates(self, offset, timeout):
            self.calls.append((offset, timeout))
            self.stop_event.set()
            return [{"update_id": 7, "message": {"chat": {"id": 1}, "text": "/help"}}]

    replies = []
    stop_event = StopEvent()
    api = Api(stop_event)
    controller = TelegramBotController(ZoneSettings(), {1}, lambda _chat, text: replies.append(text))
    poller = TelegramControlPoller(api, controller, stop_event)

    poller.run()

    assert api.calls == [(0, 5)]
    assert poller.offset == 8
    assert replies and "/zone_on" in replies[0]


def test_control_poller_dispatches_callback_query():
    class StopEvent:
        def __init__(self): self.stopped = False
        def is_set(self): return self.stopped
        def set(self): self.stopped = True
        def wait(self, _seconds): self.stopped = True

    class Api:
        def __init__(self, stop_event): self.stop_event = stop_event
        def get_updates(self, offset, timeout):
            self.stop_event.set()
            return [{"update_id": 8, "callback_query": {
                "id": "cb-8", "data": "zone_off:3",
                "message": {"chat": {"id": 1}},
            }}]

    answers = []
    settings = ZoneSettings({"3": {"enabled": True}})
    controller = TelegramBotController(
        settings, {1}, lambda *_args: None, lambda callback_id: answers.append(callback_id)
    )
    stop_event = StopEvent()
    TelegramControlPoller(Api(stop_event), controller, stop_event).run()

    assert settings.is_enabled(3) is False
    assert answers == ["cb-8"]


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
