from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

# Bosch Mode 2 Protocol Opcode Dictionary
OPCODES: Dict[int, str] = {
    0x01: "CMD_WHAT_ARE_YOU",
    0x06: "CMD_AUTHENTICATE",
    0x07: "CMD_REQUEST_PERMISSION_FOR_PANEL_ACTION",
    0x08: "CMD_ALARM_MEMORY_SUMMARY",
    0x11: "CMD_SET_DATE_TIME",
    0x12: "CMD_REQUEST_DATE_TIME",
    0x15: "CMD_REQUEST_RAW_HISTORY_EVENTS",
    0x20: "CMD_REQUEST_PANEL_SYSTEM_STATUS",
    0x23: "CMD_ALARM_MEMORY_DETAIL",
    0x24: "CMD_REQUEST_CONFIGURED_AREAS",
    0x26: "CMD_AREA_STATUS",
    0x27: "CMD_AREA_ARM",
    0x29: "CMD_AREA_TEXT",
    0x2B: "CMD_REQUEST_CONFIGURED_DOORS",
    0x2C: "CMD_DOOR_STATUS",
    0x2D: "CMD_SET_DOOR_STATE",
    0x2E: "CMD_DOOR_TEXT",
    0x30: "CMD_REQUEST_CONFIGURED_OUTPUTS",
    0x31: "CMD_OUTPUT_STATUS",
    0x32: "CMD_SET_OUTPUT_STATE",
    0x33: "CMD_OUTPUT_TEXT",
    0x35: "CMD_REQUEST_CONFIGURED_POINTS",
    0x38: "CMD_POINT_STATUS",
    0x3C: "CMD_POINT_TEXT",
    0x3E: "CMD_LOGIN_REMOTE_USER",
    0x4A: "CMD_PRODUCT_SERIAL",
    0x5F: "CMD_SET_SUBSCRIPTION",
    0x63: "CMD_REQUEST_RAW_HISTORY_EVENTS_EXT",
    # Response codes
    0xFC: "RSP_ACK",
    0xFD: "RSP_NACK",
    0xFE: "RSP_RESULT",
}

# Common Error Code Dictionary for 0xFD (NACK)
NACK_ERRORS: Dict[int, str] = {
    0x00: "NON_SPECIFIC_ERROR",
    0x01: "CHECKSUM_OR_FORMAT_ERROR",
    0x02: "PARAM_INVALID_OR_NOT_SUPPORTED",
    0x03: "PANEL_BUSY",
    0x04: "UNAUTHORIZED_OR_BAD_PASSCODE",
    0x05: "COMMAND_NOT_SUPPORTED_IN_THIS_STATE",
}


def format_hexdump(data: bytes, width: int = 16) -> str:
    """Produce standard hexdump representation with offset, hex bytes, and ASCII."""
    lines: List[str] = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hex_bytes = " ".join(f"{b:02X}" for b in chunk)
        # Pad hex bytes display
        hex_padding = "   " * (width - len(chunk))
        ascii_text = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append(f"{i:04X}  {hex_bytes}{hex_padding} |{ascii_text}|")
    return "\n".join(lines)


@dataclass
class RawFrame:
    """Represents a single raw Mode 2 protocol frame."""
    direction: str  # "TX" (outgoing) or "RX" (incoming)
    timestamp: datetime
    raw_bytes: bytes
    protocol: int
    length: int
    code: Optional[int] = None
    code_name: str = "UNKNOWN"
    payload: bytes = b""
    decoded_info: str = ""

    @property
    def formatted_time(self) -> str:
        return self.timestamp.strftime("%H:%M:%S.%f")[:-3]

    @property
    def hex_str(self) -> str:
        return " ".join(f"{b:02X}" for b in self.raw_bytes)

    @property
    def hexdump(self) -> str:
        return format_hexdump(self.raw_bytes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction,
            "timestamp": self.timestamp.isoformat(),
            "protocol": self.protocol,
            "length": self.length,
            "code": f"0x{self.code:02X}" if self.code is not None else None,
            "code_name": self.code_name,
            "hex": self.hex_str,
            "payload_hex": " ".join(f"{b:02X}" for b in self.payload),
            "decoded_info": self.decoded_info,
        }


def parse_raw_frame(data: bytes, direction: str = "RX") -> Tuple[Optional[RawFrame], int]:
    """
    Parse a single raw Mode 2 frame from bytes buffer.
    Returns (RawFrame, bytes_consumed). If incomplete, returns (None, 0).
    """
    if len(data) < 2:
        return None, 0

    proto = data[0]

    # Protocol 0x01: Basic Request / Response
    if proto == 0x01:
        payload_len = data[1]
        frame_len = 2 + payload_len
        if len(data) < frame_len:
            return None, 0

        raw_frame = data[:frame_len]
        code = raw_frame[2] if payload_len >= 1 else None
        code_name = OPCODES.get(code, f"0x{code:02X}") if code is not None else "NONE"
        payload = raw_frame[3:] if payload_len > 1 else b""

        decoded = ""
        if code == 0xFC:
            decoded = "ACK (Command Accepted)"
        elif code == 0xFD:
            err = payload[0] if payload else 0
            err_text = NACK_ERRORS.get(err, f"Unknown Error (0x{err:02X})")
            decoded = f"NACK: {err_text}"
        elif code == 0xFE:
            decoded = f"RESULT: {len(payload)} bytes payload"
        else:
            decoded = f"{code_name} (Payload: {len(payload)} bytes)"

        return RawFrame(
            direction=direction,
            timestamp=datetime.now(),
            raw_bytes=raw_frame,
            protocol=proto,
            length=payload_len,
            code=code,
            code_name=code_name,
            payload=payload,
            decoded_info=decoded,
        ), frame_len

    # Protocol 0x02: Unsolicited Subscription Push Event
    elif proto == 0x02:
        if len(data) < 3:
            return None, 0
        payload_len = int.from_bytes(data[1:3], "big")
        frame_len = 3 + payload_len
        if len(data) < frame_len:
            return None, 0

        raw_frame = data[:frame_len]
        payload = raw_frame[3:]
        return RawFrame(
            direction=direction,
            timestamp=datetime.now(),
            raw_bytes=raw_frame,
            protocol=proto,
            length=payload_len,
            code=None,
            code_name="UNSOLICITED_PUSH_EVENT",
            payload=payload,
            decoded_info=f"Subscription Event Push ({len(payload)} bytes)",
        ), frame_len

    # Protocol 0x04: Extended Response
    elif proto == 0x04:
        if len(data) < 3:
            return None, 0
        payload_len = int.from_bytes(data[1:3], "big")
        frame_len = 3 + payload_len
        if len(data) < frame_len:
            return None, 0

        raw_frame = data[:frame_len]
        code = raw_frame[3] if payload_len >= 1 else None
        code_name = OPCODES.get(code, f"0x{code:02X}") if code is not None else "NONE"
        payload = raw_frame[4:] if payload_len > 1 else b""
        return RawFrame(
            direction=direction,
            timestamp=datetime.now(),
            raw_bytes=raw_frame,
            protocol=proto,
            length=payload_len,
            code=code,
            code_name=f"EXT_{code_name}",
            payload=payload,
            decoded_info=f"Extended Response ({len(payload)} bytes)",
        ), frame_len

    # Unknown or desynchronized header
    return None, 1


def build_raw_request(opcode: int, data: bytes = b"") -> bytes:
    """Construct a Protocol 1 (Basic) Mode 2 request frame."""
    total_len = 1 + len(data)
    frame = bytearray([0x01, total_len, opcode])
    frame.extend(data)
    return bytes(frame)


class RawMode2Client:
    """Low-level Mode 2 client that exposes and captures raw frames directly."""

    def __init__(self, host: str, port: int = 7700) -> None:
        self.host = host
        self.port = port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.captured_frames: List[RawFrame] = []
        self._rx_buffer = bytearray()
        self._lock = asyncio.Lock()
        self.on_frame: Optional[Callable[[RawFrame], None]] = None

    async def connect(self) -> None:
        """Open raw TCP connection."""
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

    async def close(self) -> None:
        """Close connection."""
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
            self.writer = None
            self.reader = None

    async def send_command(self, opcode: int, data: bytes = b"") -> RawFrame:
        """Send a raw command frame and await its matching response frame."""
        if not self.writer or not self.reader:
            raise RuntimeError("RawMode2Client is not connected")

        async with self._lock:
            # Build and send TX frame
            tx_bytes = build_raw_request(opcode, data)
            tx_frame = RawFrame(
                direction="TX",
                timestamp=datetime.now(),
                raw_bytes=tx_bytes,
                protocol=0x01,
                length=len(data) + 1,
                code=opcode,
                code_name=OPCODES.get(opcode, f"0x{opcode:02X}"),
                payload=data,
                decoded_info=f"Command {OPCODES.get(opcode, hex(opcode))} (len={len(data)})",
            )
            self.captured_frames.append(tx_frame)
            if self.on_frame:
                self.on_frame(tx_frame)

            self.writer.write(tx_bytes)
            await self.writer.drain()

            # Read response from socket
            while True:
                # Check if full frame can be parsed from buffer
                frame, consumed = parse_raw_frame(bytes(self._rx_buffer), direction="RX")
                if frame:
                    del self._rx_buffer[:consumed]
                    self.captured_frames.append(frame)
                    if self.on_frame:
                        self.on_frame(frame)
                    return frame

                chunk = await self.reader.read(1024)
                if not chunk:
                    raise ConnectionResetError("Connection closed by peer while awaiting response")
                self._rx_buffer.extend(chunk)

    async def execute_full_diagnostic_dump(self, user_pin: str = "1234") -> List[Tuple[RawFrame, RawFrame]]:
        """
        Execute an exhaustive diagnostic sequence querying every supported Mode 2 endpoint.
        Returns list of (TX_frame, RX_frame) pairs.
        """
        pairs: List[Tuple[RawFrame, RawFrame]] = []

        # 1. WHAT_ARE_YOU (0x01)
        tx1_len = len(self.captured_frames)
        rx1 = await self.send_command(0x01, bytes([0x03]))
        pairs.append((self.captured_frames[tx1_len], rx1))

        # 2. PRODUCT_SERIAL (0x4A)
        tx2_len = len(self.captured_frames)
        rx2 = await self.send_command(0x4A, b"\x00\x00")
        pairs.append((self.captured_frames[tx2_len], rx2))

        # 3. LOGIN_REMOTE_USER (0x3E)
        pin_bytes = int(user_pin.ljust(8, "F"), 16).to_bytes(4, "big")
        tx3_len = len(self.captured_frames)
        rx3 = await self.send_command(0x3E, pin_bytes)
        pairs.append((self.captured_frames[tx3_len], rx3))

        # 4. REQUEST_DATE_TIME (0x12)
        tx4_len = len(self.captured_frames)
        rx4 = await self.send_command(0x12)
        pairs.append((self.captured_frames[tx4_len], rx4))

        # 5. REQUEST_PANEL_SYSTEM_STATUS (0x20)
        tx5_len = len(self.captured_frames)
        rx5 = await self.send_command(0x20)
        pairs.append((self.captured_frames[tx5_len], rx5))

        # 6. REQUEST_CONFIGURED_AREAS (0x24)
        tx6_len = len(self.captured_frames)
        rx6 = await self.send_command(0x24)
        pairs.append((self.captured_frames[tx6_len], rx6))

        # 7. AREA_STATUS (0x26) for Area 1
        tx7_len = len(self.captured_frames)
        rx7 = await self.send_command(0x26, (1).to_bytes(2, "big"))
        pairs.append((self.captured_frames[tx7_len], rx7))

        # 8. AREA_TEXT (0x29) for Area 1
        tx8_len = len(self.captured_frames)
        rx8 = await self.send_command(0x29, (1).to_bytes(2, "big") + b"\x00")
        pairs.append((self.captured_frames[tx8_len], rx8))

        # 9. REQUEST_CONFIGURED_POINTS (0x35)
        tx9_len = len(self.captured_frames)
        rx9 = await self.send_command(0x35)
        pairs.append((self.captured_frames[tx9_len], rx9))

        # 10. POINT_STATUS (0x38) for Points 1..8
        pt_req = bytearray()
        for pid in range(1, 9):
            pt_req.extend(pid.to_bytes(2, "big"))
        tx10_len = len(self.captured_frames)
        rx10 = await self.send_command(0x38, bytes(pt_req))
        pairs.append((self.captured_frames[tx10_len], rx10))

        # 11. POINT_TEXT (0x3C) for Point 1
        tx11_len = len(self.captured_frames)
        rx11 = await self.send_command(0x3C, (1).to_bytes(2, "big") + b"\x00")
        pairs.append((self.captured_frames[tx11_len], rx11))

        # 12. REQUEST_CONFIGURED_OUTPUTS (0x30)
        tx12_len = len(self.captured_frames)
        rx12 = await self.send_command(0x30)
        pairs.append((self.captured_frames[tx12_len], rx12))

        # 13. ALARM_MEMORY_SUMMARY (0x08)
        tx13_len = len(self.captured_frames)
        rx13 = await self.send_command(0x08)
        pairs.append((self.captured_frames[tx13_len], rx13))

        # 14. REQUEST_RAW_HISTORY_EVENTS (0x15)
        # Query max event ID first (start_id = 0xFFFFFFFF)
        tx14_len = len(self.captured_frames)
        rx14 = await self.send_command(0x15, b"\xff\xff\xff\xff\xff")
        pairs.append((self.captured_frames[tx14_len], rx14))

        return pairs

    async def sniff_loop(self, timeout: Optional[float] = None) -> None:
        """Passively read incoming frames and stream them via on_frame callback."""
        if not self.reader:
            raise RuntimeError("Not connected")

        start_time = asyncio.get_running_loop().time()
        while True:
            if timeout and (asyncio.get_running_loop().time() - start_time) > timeout:
                break

            # Parse any existing buffered frames
            while True:
                frame, consumed = parse_raw_frame(bytes(self._rx_buffer), direction="RX")
                if not frame:
                    break
                del self._rx_buffer[:consumed]
                self.captured_frames.append(frame)
                if self.on_frame:
                    self.on_frame(frame)

            try:
                chunk = await asyncio.wait_for(self.reader.read(1024), timeout=0.5)
                if not chunk:
                    break
                self._rx_buffer.extend(chunk)
            except asyncio.TimeoutError:
                continue
