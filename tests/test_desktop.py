"""Tests for the desktop launcher (src/desktop.py) and the server's host binding.

The tkinter ControlWindow itself isn't covered here (it needs a display); these
cover the logic it is built from.
"""

import json
import socket
from pathlib import Path

import pytest

from src import desktop
from src.server import NFLSimulatorServer


def test_parse_args_defaults():
    args = desktop.parse_args([])
    assert args.port is None
    assert args.no_window is False
    assert args.data_dir is None


def test_default_data_dir_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert desktop.default_data_dir() == tmp_path / desktop.APP_DIR_NAME


def test_default_data_dir_falls_back_to_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert desktop.default_data_dir() == tmp_path / desktop.APP_DIR_NAME


def test_default_static_dir_from_source_is_repo_frontend():
    static_dir = desktop.default_static_dir()
    assert (static_dir / "index.html").is_file()


def test_default_static_dir_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
    assert desktop.default_static_dir() == Path(tmp_path) / "frontend"


def test_server_binds_requested_host_and_free_port(tmp_path):
    server = NFLSimulatorServer(port=0, db_path=str(tmp_path / "c.db"), host="127.0.0.1")
    try:
        host, port = server.server_address
        assert host == "127.0.0.1"
        assert port > 0
    finally:
        server.server_close()
        server.cache.close()
        server.data_client.close()


# --- Port setting -----------------------------------------------------------


def test_load_port_defaults_without_settings(tmp_path):
    assert desktop.load_port(tmp_path) == desktop.DEFAULT_PORT


def test_save_then_load_port(tmp_path):
    desktop.save_port(tmp_path, 9123)
    assert desktop.load_port(tmp_path) == 9123


def test_save_port_keeps_other_settings(tmp_path):
    (tmp_path / desktop.SETTINGS_FILE).write_text(json.dumps({"other": 1, "port": 9000}))
    desktop.save_port(tmp_path, 9001)
    assert json.loads((tmp_path / desktop.SETTINGS_FILE).read_text()) == {"other": 1, "port": 9001}


@pytest.mark.parametrize(
    "content", ["not json", "[1, 2]", '{"port": "8000"}', '{"port": 80}', '{"port": 70000}', '{"port": true}']
)
def test_load_port_falls_back_on_bad_settings(tmp_path, content):
    (tmp_path / desktop.SETTINGS_FILE).write_text(content)
    assert desktop.load_port(tmp_path) == desktop.DEFAULT_PORT


@pytest.mark.parametrize(
    "port,ok",
    [(1024, True), (65535, True), (8765, True), (1023, False), (65536, False), (True, False), ("8765", False), (None, False)],
)
def test_valid_port(port, ok):
    assert desktop.valid_port(port) is ok


# --- Server lifecycle / second-instance detection ----------------------------


def test_server_handle_serves_and_is_detected_as_running_instance(tmp_path):
    handle = desktop.ServerHandle.start(0, 2025, tmp_path)
    try:
        assert handle.url == f"http://127.0.0.1:{handle.port}/"
        assert desktop.is_running_instance(handle.port) is True
    finally:
        handle.stop()
    assert desktop.is_running_instance(handle.port, timeout=0.5) is False


def test_is_running_instance_false_for_other_programs():
    # A plain listening socket that never answers HTTP: not this app.
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        assert desktop.is_running_instance(other.getsockname()[1], timeout=0.5) is False


def test_server_handle_refuses_a_taken_port(tmp_path):
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        with pytest.raises(OSError):
            desktop.ServerHandle.start(other.getsockname()[1], 2025, tmp_path)
