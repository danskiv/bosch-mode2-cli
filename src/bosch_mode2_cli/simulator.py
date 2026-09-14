from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bosch_mode2_cli.simulator")


def encode_sol2000_history_event(
    dt: datetime, event_code: int, zone_or_area: int, user: int
) -> bytes:
    """Encode a Solution 2000 8-byte history record."""
    t1 = (dt.minute & 0x3F) | ((dt.hour & 0x1F) << 6) | ((dt.day & 0x1F) << 11)
    t2 = (dt.second & 0x3F) | ((dt.month & 0x0F) << 6) | (((dt.year - 2000) & 0x3F) << 10)
    buf = bytearray()
    buf.extend(t1.to_bytes(2, "little"))
    buf.extend(t2.to_bytes(2, "little"))
    buf.extend(zone_or_area.to_bytes(2, "little"))
    buf.append(event_code & 0xFF)
    buf.append(user & 0xFF)
    return bytes(buf)


class BoschSol2000Simulator:
    """Mock TCP Server emulating a Bosch Solution 2000 with B426 Ethernet module."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7700,
        user_pin: str = "1234",
    ) -> None:
        self.host = host
        self.port = port
        self.user_pin = user_pin
        self._server: Optional[asyncio.Server] = None
        self._is_running = False

        # Panel state
        # Area 1: 0x04 = Disarmed, 0x01 = Away Armed, 0x03 = Stay 1
        self.areas: Dict[int, Dict[str, Any]] = {
            1: {"name": "Area 1", "status": 0x04}
        }
        # Points 1-8: 0x03 = Normal, 0x02 = Open
        self.points: Dict[int, Dict[str, Any]] = {
            1: {"name": "Front Door", "status": 0x03},
            2: {"name": "Living PIR", "status": 0x03},
            3: {"name": "Master Bedroom", "status": 0x03},
            4: {"name": "Kitchen Window", "status": 0x03},
            5: {"name": "Back Door", "status": 0x03},
            6: {"name": "Garage PIR", "status": 0x03},
            7: {"name": "Smoke Detector", "status": 0x03},
            8: {"name": "Emergency Panic", "status": 0x03},
        }

        # History events list (tuple: dt, code, zone_or_area, user)
        self.history_events: List[bytes] = [
            encode_sol2000_history_event(
                datetime(2026, 9, 14, 8, 0, 0), 11, 1, 1  # Disarmed by User 1
            ),
            encode_sol2000_history_event(
                datetime(2026, 9, 14, 8, 15, 22), 1, 1, 0  # Zone 1 Alarm
            ),
            encode_sol2000_history_event(
                datetime(2026, 9, 14, 8, 16, 5), 2, 1, 0  # Zone 1 Alarm Restore
            ),
            encode_sol2000_history_event(
                datetime(2026, 9, 14, 9, 30, 0), 10, 1, 1  # Armed Away by User 1
            ),
            encode_sol2000_history_event(
                datetime(2026, 9, 14, 12, 0, 0), 11, 1, 2  # Disarmed by User 2
            ),
        ]
        self._next_event_id = len(self.history_events) + 100

    def trigger_point(self, point_id: int, is_open: bool) -> None:
        """Simulate point state change."""
        if point_id in self.points:
            self.points[point_id]["status"] = 0x02 if is_open else 0x03
            # Add transaction event
            code = 1 if is_open else 2
            evt = encode_sol2000_history_event(
                datetime.now(), code, point_id, 0
            )
            self.history_events.append(evt)
            self._next_event_id += 1

    def trigger_area(self, area_id: int, status: int, user_id: int = 1) -> None:
        """Simulate area arm/disarm."""
        if area_id in self.areas:
            self.areas[area_id]["status"] = status
            # 0x01 = Away, 0x03 = Stay 1, 0x04 = Disarmed
            code = 10 if status == 0x01 else (12 if status == 0x03 else 11)
            evt = encode_sol2000_history_event(
                datetime.now(), code, area_id, user_id
            )
            self.history_events.append(evt)
            self._next_event_id += 1

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        addr = writer.get_extra_info("peername")
        logger.info("Simulator: Client connected from %s", addr)
        try:
            while self._is_running:
                # Mode 2 Basic Protocol Frame Header:
                # Byte 0: Protocol (0x01)
                # Byte 1: Length of (Code + Payload)
                header = await reader.read(2)
                if not header or len(header) < 2:
                    break

                proto = header[0]
                payload_len = header[1]
                body = await reader.read(payload_len)
                if len(body) < payload_len:
                    break

                cmd_code = body[0]
                cmd_data = body[1:]
                logger.debug("Simulator: Received cmd=0x%02X, data=%s", cmd_code, cmd_data.hex())

                response_frame = self._dispatch_command(cmd_code, cmd_data)
                if response_frame:
                    writer.write(response_frame)
                    await writer.drain()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Simulator client error: %s", e)
        finally:
            writer.close()
            await writer.wait_closed()
            logger.info("Simulator: Client disconnected from %s", addr)

    def _frame_ack(self) -> bytes:
        # Protocol 1, Length 1, 0xFC (ACK)
        return bytes([0x01, 0x01, 0xFC])

    def _frame_nack(self, err_code: int = 0x01) -> bytes:
        # Protocol 1, Length 2, 0xFD (NACK), err
        return bytes([0x01, 0x02, 0xFD, err_code])

    def _frame_result(self, payload: bytes) -> bytes:
        # Protocol 1, Length = 1 (for 0xFE) + len(payload), 0xFE, payload
        total_len = 1 + len(payload)
        return bytes([0x01, total_len, 0xFE]) + payload

    def _dispatch_command(self, cmd: int, data: bytes) -> bytes:
        # 0x01: CMD.WHAT_ARE_YOU
        if cmd == 0x01:
            # Build Solution 2000 identity payload (33+ bytes)
            # data[0]: 0x20 (Solution 2000)
            # data[1..4]: version
            # data[5]: major proto (2), data[6]: minor proto (1)
            # data[13]: busy flag (0)
            # data[23:]: bitmasks
            p = bytearray(64)
            p[0] = 0x20  # Model: Solution 2000
            p[5] = 2     # Proto v2
            p[6] = 1     # Proto .1
            # bitmask starts at offset 23
            # bitmask[0] = 0x00 (no subscriptions, forces polling)
            # bitmask[2] = 0x00 (alarm summary)
            # bitmask[5] = 0x08 (supports system status / faults)
            # bitmask[7] = 0x20 (area text format 1)
            # bitmask[8] = 0x00 (door)
            # bitmask[9] = 0x00 (output text format)
            # bitmask[11] = 0x80 (point text format 1)
            # bitmask[13] = 0x04 (supports serial)
            # bitmask[16] = 0x00 (normal raw history)
            p[23 + 5] = 0x08
            p[23 + 7] = 0x20
            p[23 + 11] = 0x80
            p[23 + 13] = 0x04
            return self._frame_result(bytes(p))

        # 0x3E: CMD.LOGIN_REMOTE_USER
        if cmd == 0x3E:
            expected_hex = int(self.user_pin.ljust(8, "F"), 16).to_bytes(4, "big")
            if data == expected_hex:
                logger.info("Simulator: User PIN authenticated successfully")
                return self._frame_ack()
            logger.warning("Simulator: User PIN mismatch: got %s, expected %s", data.hex(), expected_hex.hex())
            return self._frame_nack(0x01)

        # 0x4A: CMD.PRODUCT_SERIAL
        if cmd == 0x4A:
            # Return 6 bytes serial: e.g. 123456
            return self._frame_result((123456).to_bytes(6, "big"))

        # 0x20: CMD.REQUEST_PANEL_SYSTEM_STATUS
        if cmd == 0x20:
            # 7 bytes: version(1), revision(1), ... faults at offset 5 (2 bytes)
            st = bytearray(7)
            st[0] = 2  # Major firmware
            st[1] = 1  # Minor firmware
            st[5] = 0  # Faults bitmap high
            st[6] = 0  # Faults bitmap low (no faults)
            return self._frame_result(bytes(st))

        # 0x24: CMD.REQUEST_CONFIGURED_AREAS
        if cmd == 0x24:
            # Return bitmap: 0x80 = Area 1 enabled
            return self._frame_result(bytes([0x80]))

        # 0x29: CMD.AREA_TEXT
        if cmd == 0x29:
            # CF01 format: 2-byte area ID + lang byte (0x00) -> returns name + null
            area_id = int.from_bytes(data[:2], "big")
            name = self.areas.get(area_id, {}).get("name", f"Area {area_id}")
            return self._frame_result(name.encode("utf8") + b"\x00")

        # 0x35: CMD.REQUEST_CONFIGURED_POINTS
        if cmd == 0x35:
            # Return bitmap: 0xFF = Points 1..8 enabled
            return self._frame_result(bytes([0xFF]))

        # 0x3C: CMD.POINT_TEXT
        if cmd == 0x3C:
            # CF01 format: 2-byte point ID + lang byte -> returns name + null
            point_id = int.from_bytes(data[:2], "big")
            name = self.points.get(point_id, {}).get("name", f"Point {point_id}")
            return self._frame_result(name.encode("utf8") + b"\x00")

        # 0x30: CMD.REQUEST_CONFIGURED_OUTPUTS
        if cmd == 0x30:
            return self._frame_result(bytes([0x00]))

        # 0x26: CMD.AREA_STATUS
        if cmd == 0x26:
            # Request has 2-byte area IDs
            res = bytearray()
            idx = 0
            while idx < len(data):
                aid = int.from_bytes(data[idx : idx + 2], "big")
                status = self.areas.get(aid, {}).get("status", 0x01)
                res.extend(aid.to_bytes(2, "big"))
                res.append(status)
                idx += 2
            return self._frame_result(bytes(res))

        # 0x38: CMD.POINT_STATUS
        if cmd == 0x38:
            # Request has 2-byte point IDs
            res = bytearray()
            idx = 0
            while idx < len(data):
                pid = int.from_bytes(data[idx : idx + 2], "big")
                status = self.points.get(pid, {}).get("status", 0x01)
                res.extend(pid.to_bytes(2, "big"))
                res.append(status)
                idx += 2
            return self._frame_result(bytes(res))

        # 0x15: CMD.REQUEST_RAW_HISTORY_EVENTS
        if cmd == 0x15:
            # Request: 1 byte count (0xFF), 4 bytes start_event_id
            start_id = int.from_bytes(data[1:5], "big")
            logger.debug("Simulator: History request start_id=%d", start_id)
            if start_id >= 0xFFFFFFFF or start_id >= self._next_event_id:
                # Discovery of max event ID: return count=0, start_id=current_max
                res = bytearray([0])
                res.extend((self._next_event_id).to_bytes(4, "big"))
                return self._frame_result(bytes(res))

            # Return available events starting from start_id
            events_to_send = self.history_events[-5:]  # send up to 5 events
            count = len(events_to_send)
            res = bytearray([count])
            res.extend((start_id).to_bytes(4, "big"))
            for evt in events_to_send:
                res.extend(evt)
            return self._frame_result(bytes(res))

        # Default ACK for any other command
        logger.debug("Simulator: unhandled cmd 0x%02X, returning ACK", cmd)
        return self._frame_ack()

    async def start(self) -> None:
        """Start the simulator server."""
        self._is_running = True
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        logger.info("Bosch Solution 2000 Simulator listening on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        """Stop the simulator server."""
        self._is_running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("Simulator stopped.")
