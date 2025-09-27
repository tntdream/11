from __future__ import annotations

from typing import Iterable

from tkinter import TclError

from waverly import __main__ as entrypoint


class DummyApp:
    def __init__(self, should_raise: bool = False) -> None:
        if should_raise:
            raise TclError("no display")
        self.loop_count = 0

    def mainloop(self) -> None:
        self.loop_count += 1


def invoke_main(args: Iterable[str] | None = None) -> int:
    return entrypoint.main(args)


def test_main_exits_when_no_display(monkeypatch, capsys):
    monkeypatch.setattr(entrypoint, "_has_display", lambda: False)
    status = invoke_main([])
    assert status == 1
    captured = capsys.readouterr()
    assert "无法启动图形界面" in captured.err


def test_main_handles_tcl_error(monkeypatch, capsys):
    monkeypatch.setattr(entrypoint, "_has_display", lambda: True)

    def factory() -> DummyApp:
        return DummyApp(should_raise=True)

    monkeypatch.setattr(entrypoint, "WaverlyApp", factory)
    status = invoke_main([])
    assert status == 1
    captured = capsys.readouterr()
    assert "无法启动图形界面" in captured.err


def test_main_success_path(monkeypatch):
    monkeypatch.setattr(entrypoint, "_has_display", lambda: True)

    app = DummyApp()
    monkeypatch.setattr(entrypoint, "WaverlyApp", lambda: app)

    status = invoke_main([])
    assert status == 0
    assert app.loop_count == 1


def test_check_flag(monkeypatch, capsys):
    monkeypatch.setattr(entrypoint, "_has_display", lambda: False)
    status = invoke_main(["--check"])
    assert status == 1
    captured = capsys.readouterr()
    assert "DISPLAY" in captured.err

    monkeypatch.setattr(entrypoint, "_has_display", lambda: True)
    status = invoke_main(["--check"])
    assert status == 0
    captured = capsys.readouterr()
    assert "可以正常启动" in captured.out
