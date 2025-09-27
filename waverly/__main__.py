from __future__ import annotations

from .app import WaverlyApp


def main() -> None:
    app = WaverlyApp()
    app.mainloop()


if __name__ == "__main__":
    main()

