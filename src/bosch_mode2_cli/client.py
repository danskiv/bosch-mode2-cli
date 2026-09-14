from __future__ import annotations

import asyncio
import logging
import ssl
from datetime import datetime
from typing import Callable, List, Optional

from bosch_alarm_mode2 import Panel
from bosch_alarm_mode2.const import AREA_STATUS, POINT_STATUS
import bosch_alarm_mode2.panel as panel_module

from bosch_mode2_cli.history import parse_history_tuple
from bosch_mode2_cli.models import (
    AreaRecord,
    PanelSnapshot,
    PointRecord,
    TransactionRecord,
)

logger = logging.getLogger("bosch_mode2_cli.client")

# Monkeypatch upstream Panel._poll to safely handle task cancellation and event loop closure
if not getattr(Panel, "_safe_poll_patched", False):
    async def _safe_poll(panel_self: Panel) -> None:
        while True:
            try:
                await asyncio.sleep(1)
                await panel_self._load_status()
                panel_self._last_msg = datetime.now()
            except (asyncio.CancelledError, GeneratorExit):
                break
            except RuntimeError as e:
                err_str = str(e).lower()
                if "no running event loop" in err_str or "event loop is closed" in err_str:
                    break
                logger.error("Polling exception: %s", e)
                try:
                    await asyncio.sleep(2)
                except (asyncio.CancelledError, RuntimeError):
                    break
            except Exception as e:
                logger.error("Polling exception: %s", e)
                try:
                    await asyncio.sleep(2)
                except (asyncio.CancelledError, RuntimeError):
                    break

    Panel._poll = _safe_poll
    setattr(Panel, "_safe_poll_patched", True)


class BoschSol2000Client:
    """Async client managing connection, observation, and decoding for Bosch Solution 2000."""

    def __init__(
        self,
        host: str,
        port: int = 7700,
        user_pin: str = "1234",
        use_ssl: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.user_pin = str(user_pin).strip()
        self.use_ssl = use_ssl

        # Configure SSL context in bosch_alarm_mode2 module
        if self.use_ssl:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.set_ciphers("DEFAULT")
            panel_module.ssl_context = ctx
        else:
            panel_module.ssl_context = None

        # Initialize underlying Mode 2 panel
        self._panel = Panel(
            host=self.host,
            port=self.port,
            automation_code=None,
            installer_or_user_code=self.user_pin,
        )

        self._seen_event_ids: set[int] = set()
        self._transactions: List[TransactionRecord] = []
        self._is_connected: bool = False

        # Callback hooks
        self.on_transaction: Optional[Callable[[TransactionRecord], None]] = None
        self.on_point_update: Optional[Callable[[PointRecord], None]] = None
        self.on_area_update: Optional[Callable[[AreaRecord], None]] = None
        self.on_connection_update: Optional[Callable[[bool], None]] = None

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def transactions(self) -> List[TransactionRecord]:
        return list(self._transactions)

    def _handle_connection_change(self) -> None:
        status = bool(self._panel.connection_status())
        self._is_connected = status
        logger.info("Panel connection status changed: %s", "CONNECTED" if status else "DISCONNECTED")
        if self.on_connection_update:
            try:
                self.on_connection_update(status)
            except Exception as e:
                logger.error("Error in connection update callback: %s", e)

    def _handle_history_update(self) -> None:
        """Triggered when history_observer notifies new events."""
        events = self._panel.events
        for raw_evt in events:
            evt_id = getattr(raw_evt, "id", None)
            if evt_id is not None and evt_id in self._seen_event_ids:
                continue
            if evt_id is not None:
                self._seen_event_ids.add(evt_id)

            rec = parse_history_tuple(raw_evt)
            self._transactions.append(rec)
            logger.debug("New transaction: %s", rec)
            if self.on_transaction:
                try:
                    self.on_transaction(rec)
                except Exception as e:
                    logger.error("Error in transaction callback: %s", e)

    def _handle_point_update(self, point_id: int) -> None:
        point = self._panel.points.get(point_id)
        if not point:
            return
        status_text = POINT_STATUS.TEXT.get(point.status, f"Unknown ({point.status})")
        rec = PointRecord(
            id=point_id,
            name=point.name or f"Zone {point_id}",
            status_code=point.status,
            status_text=status_text,
            is_open=point.is_open(),
            is_normal=point.is_normal(),
            last_updated=datetime.now(),
        )
        if self.on_point_update:
            try:
                self.on_point_update(rec)
            except Exception as e:
                logger.error("Error in point update callback: %s", e)

    def _handle_area_update(self, area_id: int) -> None:
        area = self._panel.areas.get(area_id)
        if not area:
            return
        status_text = AREA_STATUS.TEXT.get(area.status, f"Status ({area.status})")
        rec = AreaRecord(
            id=area_id,
            name=area.name or f"Area {area_id}",
            status_code=area.status,
            status_text=status_text,
            is_armed=area.is_armed(),
            is_alarm=area.is_triggered(),
            all_ready=bool(area.all_ready),
            last_updated=datetime.now(),
        )
        if self.on_area_update:
            try:
                self.on_area_update(rec)
            except Exception as e:
                logger.error("Error in area update callback: %s", e)

    async def connect(self, load_history: bool = True) -> None:
        """Connect to the Bosch panel over Mode 2 TCP socket."""
        logger.info("Connecting to Bosch panel at %s:%d (User PIN: %s)...", self.host, self.port, "***")

        # Attach observers before connecting
        self._panel.connection_status_observer.attach(self._handle_connection_change)
        self._panel.history_observer.attach(self._handle_history_update)

        selector = Panel.LOAD_ALL if load_history else (Panel.LOAD_EXTENDED_INFO | Panel.LOAD_ENTITIES | Panel.LOAD_STATUS)
        await self._panel.connect(load_selector=selector)
        self._is_connected = True

        # Attach observers to all points and areas
        for point_id, point in self._panel.points.items():
            point.status_observer.attach(lambda pid=point_id: self._handle_point_update(pid))

        for area_id, area in self._panel.areas.items():
            area.status_observer.attach(lambda aid=area_id: self._handle_area_update(aid))

        # Ingest already loaded initial history
        self._handle_history_update()

    async def disconnect(self) -> None:
        """Disconnect cleanly from the panel."""
        if self._panel:
            # Cancel background polling task if running
            poll_task = getattr(self._panel, "_poll_task", None)
            if poll_task and not poll_task.done():
                poll_task.cancel()
                try:
                    await poll_task
                except (asyncio.CancelledError, RuntimeError):
                    pass
                self._panel._poll_task = None

            # Cancel background connection monitor task if running
            monitor_task = getattr(self._panel, "_monitor_connection_task", None)
            if monitor_task and not monitor_task.done():
                monitor_task.cancel()
                try:
                    await monitor_task
                except (asyncio.CancelledError, RuntimeError):
                    pass
                self._panel._monitor_connection_task = None

            await self._panel.disconnect()
        self._is_connected = False

    def get_snapshot(self) -> PanelSnapshot:
        """Capture current panel snapshot."""
        model_name = self._panel.model.name if self._panel.model else "Unknown"
        family = str(self._panel.model.family) if self._panel.model else "Unknown"

        areas_dict: dict[int, AreaRecord] = {}
        for aid, area in self._panel.areas.items():
            areas_dict[aid] = AreaRecord(
                id=aid,
                name=area.name or f"Area {aid}",
                status_code=area.status,
                status_text=AREA_STATUS.TEXT.get(area.status, str(area.status)),
                is_armed=area.is_armed(),
                is_alarm=area.is_triggered(),
                all_ready=bool(area.all_ready),
            )

        points_dict: dict[int, PointRecord] = {}
        for pid, point in self._panel.points.items():
            points_dict[pid] = PointRecord(
                id=pid,
                name=point.name or f"Point {pid}",
                status_code=point.status,
                status_text=POINT_STATUS.TEXT.get(point.status, str(point.status)),
                is_open=point.is_open(),
                is_normal=point.is_normal(),
            )

        fault_names = self._panel.panel_faults or []

        return PanelSnapshot(
            model_name=model_name,
            family=family,
            protocol_version=self._panel.protocol_version or "Unknown",
            firmware_version=self._panel.firmware_version,
            serial_number=self._panel.serial_number,
            connected=self._is_connected,
            areas=areas_dict,
            points=points_dict,
            faults=fault_names,
            recent_transactions=list(self._transactions[-50:]),
        )
