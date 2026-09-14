import asyncio
import pytest
from datetime import datetime
from bosch_mode2_cli.raw_protocol import (
    RawMode2Client,
    build_raw_request,
    format_hexdump,
    parse_raw_frame,
)
from bosch_mode2_cli.simulator import BoschSol2000Simulator


def test_format_hexdump():
    data = b"\x01\x04\xfe\x20\x00\x00"
    dump = format_hexdump(data)
    assert "0000" in dump
    assert "01 04 FE 20 00 00" in dump


def test_parse_raw_frame_basic():
    # ACK frame: Proto 1, Len 1, Code 0xFC
    ack_bytes = bytes([0x01, 0x01, 0xFC])
    frame, consumed = parse_raw_frame(ack_bytes)
    assert frame is not None
    assert consumed == 3
    assert frame.protocol == 1
    assert frame.code == 0xFC
    assert frame.code_name == "RSP_ACK"

    # Incomplete frame
    incomplete = bytes([0x01, 0x05, 0xFE])
    frame, consumed = parse_raw_frame(incomplete)
    assert frame is None
    assert consumed == 0


def test_parse_raw_frame_unsolicited():
    # Proto 2, Len 4 (0x00, 0x04), payload "TEST"
    proto2_bytes = bytes([0x02, 0x00, 0x04]) + b"TEST"
    frame, consumed = parse_raw_frame(proto2_bytes)
    assert frame is not None
    assert consumed == 7
    assert frame.protocol == 2
    assert frame.code_name == "UNSOLICITED_PUSH_EVENT"
    assert frame.payload == b"TEST"


def test_build_raw_request():
    req = build_raw_request(0x01, bytes([0x03]))
    assert req == bytes([0x01, 0x02, 0x01, 0x03])


@pytest.mark.asyncio
async def test_raw_client_full_dump_against_simulator():
    port = 17720
    pin = "1234"
    sim = BoschSol2000Simulator(host="127.0.0.1", port=port, user_pin=pin)
    await sim.start()

    raw_client = RawMode2Client(host="127.0.0.1", port=port)
    await raw_client.connect()

    try:
        pairs = await raw_client.execute_full_diagnostic_dump(user_pin=pin)
        assert len(pairs) == 14

        # Verify WHAT_ARE_YOU exchange
        tx1, rx1 = pairs[0]
        assert tx1.code == 0x01
        assert rx1.code == 0xFE
        assert rx1.payload[0] == 0x20  # Sol 2000

        # Verify LOGIN_REMOTE_USER exchange
        tx3, rx3 = pairs[2]
        assert tx3.code == 0x3E
        assert rx3.code == 0xFC  # ACK

        # Verify POINT_STATUS exchange
        tx10, rx10 = pairs[9]
        assert tx10.code == 0x38
        assert rx10.code == 0xFE
        assert len(rx10.payload) == 8 * 3  # 8 points * (2 bytes ID + 1 byte status)

    finally:
        await raw_client.close()
        await sim.stop()


@pytest.mark.asyncio
async def test_raw_client_sniff_unsolicited():
    port = 17721
    pin = "1234"
    sim = BoschSol2000Simulator(host="127.0.0.1", port=port, user_pin=pin)
    await sim.start()

    raw_client = RawMode2Client(host="127.0.0.1", port=port)
    await raw_client.connect()

    received_frames = []
    raw_client.on_frame = lambda f: received_frames.append(f)

    async def broadcast_soon():
        await asyncio.sleep(0.05)
        await sim.broadcast_unsolicited(b"\xAA\xBB\xCC\xDD")

    task = asyncio.create_task(broadcast_soon())

    try:
        await raw_client.sniff_loop(timeout=0.3)
        assert any(f.protocol == 2 and f.payload == b"\xAA\xBB\xCC\xDD" for f in received_frames)
    finally:
        await raw_client.close()
        await sim.stop()
        task.cancel()
