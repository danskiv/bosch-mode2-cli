from datetime import datetime
from bosch_mode2_cli.models import (
    AreaRecord,
    EventCategory,
    PointRecord,
    TransactionRecord,
    categorize_event,
)


def test_categorize_event():
    assert categorize_event("Zone 1 Burglary Alarm") == EventCategory.ALARM
    assert categorize_event("Zone 1 Alarm Restore") == EventCategory.RESTORE
    assert categorize_event("Area 1 Armed Away by User 1") == EventCategory.ARM_DISARM
    assert categorize_event("Area 1 Disarmed by User 2") == EventCategory.ARM_DISARM
    assert categorize_event("Zone 3 Trouble") == EventCategory.TROUBLE
    assert categorize_event("AC Fail") == EventCategory.TROUBLE
    assert categorize_event("System Reset") == EventCategory.SYSTEM
    assert categorize_event("Random unknown text") == EventCategory.UNKNOWN


def test_transaction_record_serialization():
    dt = datetime(2026, 9, 14, 10, 30, 0)
    tx = TransactionRecord(id=101, timestamp=dt, message="Zone 2 Alarm")
    assert tx.category == EventCategory.ALARM
    d = tx.to_dict()
    assert d["id"] == 101
    assert d["timestamp"] == "2026-09-14 10:30:00"
    assert d["category"] == "ALARM"
    assert d["message"] == "Zone 2 Alarm"


def test_point_and_area_record():
    p = PointRecord(
        id=1, name="Front Door", status_code=1, status_text="Normal", is_normal=True
    )
    assert p.is_normal is True
    assert p.is_open is False
    assert p.to_dict()["name"] == "Front Door"

    a = AreaRecord(
        id=1,
        name="Main Office",
        status_code=1,
        status_text="Disarmed",
        is_armed=False,
    )
    assert a.is_armed is False
    assert a.to_dict()["name"] == "Main Office"
