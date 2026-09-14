import pytest
from datetime import datetime
from bosch_mode2_cli.simulator import BoschSol2000Simulator, encode_sol2000_history_event
from bosch_alarm_mode2.history import SolutionHistoryParser


def test_encode_sol2000_history_event():
    dt = datetime(2026, 9, 14, 14, 25, 30)
    raw = encode_sol2000_history_event(dt, 1, 3, 0)  # Zone 3 Alarm
    assert len(raw) == 8

    parser = SolutionHistoryParser()
    evt = parser.parse_polled_event(1, bytearray(raw))
    assert evt.date == dt
    assert "Zone 3 Alarm" in evt.message


@pytest.mark.asyncio
async def test_simulator_lifecycle():
    sim = BoschSol2000Simulator(host="127.0.0.1", port=17701, user_pin="1234")
    await sim.start()
    assert sim._is_running is True

    # Test internal command dispatch directly
    # 1. WHAT_ARE_YOU (0x01)
    res = sim._dispatch_command(0x01, b"")
    assert res[0] == 0x01
    assert res[2] == 0xFE
    assert res[3] == 0x20  # Model Solution 2000

    # 2. LOGIN_REMOTE_USER (0x3E)
    correct_pin_bytes = int("1234".ljust(8, "F"), 16).to_bytes(4, "big")
    ack = sim._dispatch_command(0x3E, correct_pin_bytes)
    assert ack == bytes([0x01, 0x01, 0xFC])

    wrong_pin_bytes = int("9999".ljust(8, "F"), 16).to_bytes(4, "big")
    nack = sim._dispatch_command(0x3E, wrong_pin_bytes)
    assert nack == bytes([0x01, 0x02, 0xFD, 0x01])

    await sim.stop()
    assert sim._is_running is False
