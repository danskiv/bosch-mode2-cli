import argparse
import pytest
from bosch_mode2_cli.cli import build_parser, cmd_status, cmd_history
from bosch_mode2_cli.simulator import BoschSol2000Simulator


def test_cli_parser():
    parser = build_parser()
    args = parser.parse_args(["monitor", "--host", "192.168.1.10", "--pin", "4321"])
    assert args.command == "monitor"
    assert args.host == "192.168.1.10"
    assert args.pin == "4321"

    args_hist = parser.parse_args(["history", "--format", "json", "--limit", "10"])
    assert args_hist.command == "history"
    assert args_hist.format == "json"
    assert args_hist.limit == 10


@pytest.mark.asyncio
async def test_cmd_status_execution(capsys):
    port = 17705
    pin = "1234"
    sim = BoschSol2000Simulator(host="127.0.0.1", port=port, user_pin=pin)
    await sim.start()

    try:
        parser = build_parser()
        args = parser.parse_args(["status", "--host", "127.0.0.1", "-p", str(port), "--pin", pin])
        code = await cmd_status(args, {})
        assert code == 0
    finally:
        await sim.stop()


@pytest.mark.asyncio
async def test_cmd_history_json_execution(capsys):
    port = 17706
    pin = "1234"
    sim = BoschSol2000Simulator(host="127.0.0.1", port=port, user_pin=pin)
    await sim.start()

    try:
        parser = build_parser()
        args = parser.parse_args(
            ["history", "--host", "127.0.0.1", "-p", str(port), "--pin", pin, "--format", "json"]
        )
        code = await cmd_history(args, {})
        assert code == 0
        captured = capsys.readouterr()
        assert "Zone 1 Alarm" in captured.out or "Disarmed" in captured.out
    finally:
        await sim.stop()
