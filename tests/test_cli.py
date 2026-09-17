import argparse
import importlib.metadata
import pytest
from bosch_mode2_cli import __version__
from bosch_mode2_cli.cli import (
    build_parser,
    cmd_status,
    cmd_history,
    resolve_panel_settings,
    save_panel_config,
)
from bosch_mode2_cli.cli import build_telegram_notifier
from bosch_mode2_cli.telegram_notifier import AlarmRestoreNotifier
from bosch_mode2_cli.simulator import BoschSol2000Simulator


def test_version_is_consistent_with_package_metadata():
    assert importlib.metadata.version("bosch-mode2-cli") == __version__


def test_telegram_notifications_are_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    notifier = build_telegram_notifier({}, "Solution 2000")

    assert notifier is None


def test_telegram_notifications_require_explicit_enable_and_environment(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    notifier = build_telegram_notifier(
        {"enabled": True}, "Solution 2000"
    )

    assert isinstance(notifier, AlarmRestoreNotifier)


def test_cli_parser():
    parser = build_parser()
    args = parser.parse_args(["monitor", "--host", "192.168.1.10", "--pin", "4321"])
    assert args.command == "monitor"
    assert args.host == "192.168.1.10"
    assert args.pin == "4321"
    assert args.no_tls is False

    args_monitor = parser.parse_args(["monitor"])
    assert not hasattr(args_monitor, "edit_connection")

    args_plain = parser.parse_args(["status", "--no-tls"])
    assert args_plain.no_tls is True

    args_hist = parser.parse_args(["history", "--format", "json", "--limit", "10"])
    assert args_hist.command == "history"
    assert args_hist.format == "json"
    assert args_hist.limit == 10


def test_first_run_connection_wizard_and_persisted_defaults(monkeypatch, tmp_path):
    answers = iter(["192.168.20.160", "7700", "2580"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    cfg = {}
    config_path = tmp_path / "config.yaml"

    host, port, code = resolve_panel_settings(None, None, None, cfg, config_path=config_path)

    assert (host, port, code) == ("192.168.20.160", 7700, "2580")
    assert cfg["panel"] == {"host": "192.168.20.160", "port": 7700, "user_code": "2580"}
    assert "user_code: '2580'" in config_path.read_text(encoding="utf-8")


def test_existing_connection_values_can_be_edited(monkeypatch, tmp_path):
    answers = iter(["", "7701", "9876"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    cfg = {"panel": {"host": "192.168.20.151", "port": 7700}}
    config_path = tmp_path / "config.yaml"

    host, port, code = resolve_panel_settings(None, None, None, cfg, config_path=config_path)

    assert (host, port, code) == ("192.168.20.151", 7701, "9876")
    assert cfg["panel"]["port"] == 7701
    assert cfg["panel"]["user_code"] == "9876"


def test_save_panel_config_writes_visible_code_and_preserves_other_settings(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "panel:\n  host: old-host\n  port: 7000\n  user_pin: legacy\nmonitor:\n  mode: plain\n",
        encoding="utf-8",
    )
    save_panel_config(config_path, "192.168.20.151", 7700, "2580")
    text = config_path.read_text(encoding="utf-8")
    assert "192.168.20.151" in text
    assert "7700" in text
    assert "user_pin" not in text
    assert "user_code: '2580'" in text
    assert "mode: plain" in text


@pytest.mark.asyncio
async def test_cmd_status_execution(capsys):
    port = 17705
    pin = "1234"
    sim = BoschSol2000Simulator(host="127.0.0.1", port=port, user_pin=pin)
    await sim.start()

    try:
        parser = build_parser()
        args = parser.parse_args(
            ["status", "--host", "127.0.0.1", "-p", str(port), "--pin", pin, "--no-tls"]
        )
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
            [
                "history", "--host", "127.0.0.1", "-p", str(port),
                "--pin", pin, "--format", "json", "--no-tls",
            ]
        )
        code = await cmd_history(args, {})
        assert code == 0
        captured = capsys.readouterr()
        assert "Zone 1 Alarm" in captured.out or "Disarmed" in captured.out
    finally:
        await sim.stop()
