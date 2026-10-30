"""Tests for the desktop launcher (src/desktop.py) and the server's host binding."""

import base64
from pathlib import Path

from src import desktop
from src.server import NFLSimulatorServer


def test_parse_args_defaults_to_free_port_and_window():
    args = desktop.parse_args([])
    assert args.port == 0
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


def test_save_file_writes_decoded_bytes(tmp_path, monkeypatch):
    target = tmp_path / "out.zip"

    class FakeWindow:
        def create_file_dialog(self, mode, save_filename):
            assert save_filename == "export.zip"
            return str(target)

    import sys
    import types

    fake_webview = types.SimpleNamespace(SAVE_DIALOG=30)
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    api = desktop.DesktopApi()
    api.window = FakeWindow()

    assert api.save_file("export.zip", base64.b64encode(b"PK\x03\x04").decode()) is True
    assert target.read_bytes() == b"PK\x03\x04"


def test_save_file_cancelled(monkeypatch):
    import sys
    import types

    class FakeWindow:
        def create_file_dialog(self, mode, save_filename):
            return None

    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(SAVE_DIALOG=30))
    api = desktop.DesktopApi()
    api.window = FakeWindow()
    assert api.save_file("x.png", "") is False


def test_unblock_bundled_dlls_removes_zone_identifier(monkeypatch, tmp_path):
    # On NTFS "a.dll:Zone.Identifier" is an alternate data stream; elsewhere
    # it's an ordinary file with that name, which exercises the same os.remove.
    (tmp_path / "sub").mkdir()
    marked = tmp_path / "sub" / "a.dll"
    marked.write_bytes(b"")
    Path(f"{marked}:Zone.Identifier").write_text("[ZoneTransfer]\nZoneId=3\n")
    (tmp_path / "b.dll").write_bytes(b"")
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)

    desktop._unblock_bundled_dlls()

    assert not Path(f"{marked}:Zone.Identifier").exists()
    assert marked.exists()


def test_unblock_bundled_dlls_skips_source_runs(monkeypatch, tmp_path):
    marker = tmp_path / "a.dll:Zone.Identifier"
    marker.write_text("")
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("sys.frozen", False, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)

    desktop._unblock_bundled_dlls()

    assert marker.exists()
