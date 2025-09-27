from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable

from tkinter import TclError

from .app import WaverlyApp


def _has_display() -> bool:
    """Return True when a graphical display is likely available."""

    platform = sys.platform
    if platform.startswith(("win", "cygwin")):
        return True
    if platform == "darwin":
        return True

    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the Waverly desktop application")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the current environment without starting the GUI",
    )
    return parser


def _print_display_error() -> None:
    message = (
        "无法启动图形界面：当前环境未检测到可用的显示服务器。\n"
        "请在支持 GUI 的本地环境运行，或使用 xvfb-run / 远程桌面提供 DISPLAY 后重试。"
    )
    print(message, file=sys.stderr)


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.check:
        if _has_display():
            print("图形环境可用，Waverly 可以正常启动。")
            return 0
        _print_display_error()
        return 1

    if not _has_display():
        _print_display_error()
        return 1

    try:
        app = WaverlyApp()
    except TclError:
        _print_display_error()
        return 1

    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

