import json
from datetime import datetime
from bosch_alarm_mode2.history import HistoryEvent
from bosch_mode2_cli.history import (
    export_transactions_csv,
    export_transactions_json,
    filter_transactions,
    parse_history_tuple,
)
from bosch_mode2_cli.models import EventCategory, TransactionRecord


def test_parse_history_tuple():
    raw_event = HistoryEvent(id=55, date=datetime(2026, 9, 14, 11, 0, 0), message="Zone 1 Alarm")
    rec = parse_history_tuple(raw_event)
    assert rec.id == 55
    assert rec.message == "Zone 1 Alarm"
    assert rec.category == EventCategory.ALARM


def test_filter_transactions():
    t1 = TransactionRecord(id=1, timestamp=datetime.now(), message="Zone 1 Alarm")
    t2 = TransactionRecord(id=2, timestamp=datetime.now(), message="Area 1 Armed Away by User 1")
    t3 = TransactionRecord(id=3, timestamp=datetime.now(), message="Zone 1 Alarm Restore")

    records = [t1, t2, t3]

    alarms = filter_transactions(records, category=EventCategory.ALARM)
    assert len(alarms) == 1
    assert alarms[0].id == 1

    searched = filter_transactions(records, search="User 1")
    assert len(searched) == 1
    assert searched[0].id == 2


def test_export_transactions():
    t1 = TransactionRecord(id=10, timestamp=datetime(2026, 9, 14, 12, 0, 0), message="Zone 1 Alarm")
    json_out = export_transactions_json([t1])
    parsed = json.loads(json_out)
    assert len(parsed) == 1
    assert parsed[0]["id"] == 10

    csv_out = export_transactions_csv([t1])
    assert "Zone 1 Alarm" in csv_out
    assert "id,timestamp,category,message" in csv_out
