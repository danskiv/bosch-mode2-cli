from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class EventCategory(str, Enum):
    ALARM = "ALARM"
    RESTORE = "RESTORE"
    ARM_DISARM = "ARM_DISARM"
    TROUBLE = "TROUBLE"
    SYSTEM = "SYSTEM"
    UNKNOWN = "UNKNOWN"


def categorize_event(message: str) -> EventCategory:
    """Categorize Bosch event message into standard security classifications."""
    msg = message.upper()
    if "RESTORE" in msg:
        return EventCategory.RESTORE
    if any(k in msg for k in ["AWAY ARM", "STAY1 ARM", "STAY2 ARM", "DISARM", "ARMED", "DISARMED"]):
        return EventCategory.ARM_DISARM
    if any(k in msg for k in ["ALARM", "PANIC", "FIRE", "DURESS", "HOLD-UP", "BURGLARY", "MEDICAL"]):
        return EventCategory.ALARM
    if any(
        k in msg
        for k in [
            "TROUBLE",
            "FAULT",
            "TAMPER",
            "FAIL",
            "LOW BATTERY",
            "BATTERY LOW",
            "AC FAIL",
            "AC POWER FAIL",
            "MISSING",
            "JAMMING",
            "LOCKED",
            "OVER CURRENT",
        ]
    ):
        return EventCategory.TROUBLE
    if any(
        k in msg
        for k in [
            "RESET",
            "SYSTEM",
            "TEST",
            "CLOCK",
            "TIME",
            "PROGRAM",
            "SERVICE MODE",
            "WALK TEST",
            "BYPASS",
        ]
    ):
        return EventCategory.SYSTEM
    return EventCategory.UNKNOWN


@dataclass
class TransactionRecord:
    """Represents a transaction / history event from Bosch Mode 2."""
    id: int
    timestamp: datetime
    message: str
    category: EventCategory = EventCategory.UNKNOWN
    raw_params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.category == EventCategory.UNKNOWN:
            self.category = categorize_event(self.message)

    @property
    def formatted_time(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.formatted_time,
            "category": self.category.value,
            "message": self.message,
        }


@dataclass
class PointRecord:
    """Represents an intrusion point (zone) on the panel."""
    id: int
    name: str
    status_code: int
    status_text: str
    is_open: bool = False
    is_normal: bool = True
    last_updated: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status_code": self.status_code,
            "status": self.status_text,
            "is_open": self.is_open,
            "is_normal": self.is_normal,
            "last_updated": self.last_updated.strftime("%Y-%m-%d %H:%M:%S") if self.last_updated else None,
        }


@dataclass
class AreaRecord:
    """Represents an area / partition on the panel."""
    id: int
    name: str
    status_code: int
    status_text: str
    is_armed: bool = False
    is_alarm: bool = False
    all_ready: bool = True
    last_updated: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status_code": self.status_code,
            "status": self.status_text,
            "is_armed": self.is_armed,
            "is_alarm": self.is_alarm,
            "all_ready": self.all_ready,
            "last_updated": self.last_updated.strftime("%Y-%m-%d %H:%M:%S") if self.last_updated else None,
        }


@dataclass
class PanelSnapshot:
    """Full snapshot of panel state."""
    model_name: str
    family: str
    protocol_version: str
    firmware_version: Optional[str]
    serial_number: Optional[int]
    connected: bool
    areas: dict[int, AreaRecord] = field(default_factory=dict)
    points: dict[int, PointRecord] = field(default_factory=dict)
    faults: list[str] = field(default_factory=list)
    recent_transactions: list[TransactionRecord] = field(default_factory=list)
