"""Точка входа gps-sim-ui."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "Требуется PySide6. Установите: pip install 'gps-sim[ui]'",
            file=sys.stderr,
        )
        return 1

    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    except ImportError:
        print(
            "Требуется Qt WebEngine (часть PySide6 на вашей платформе). "
            "Проверьте установку PySide6.",
            file=sys.stderr,
        )
        return 1

    from gps_sim.settings import load_settings
    from gps_sim_ui.login_dialog import LoginDialog
    from gps_sim_ui.mainwindow import MainWindow, pick_gps_sdr_sim_path_if_needed

    app = QApplication(sys.argv)
    cfg = load_settings()
    has_login = bool((cfg.get("nasa_login") or "").strip() and (cfg.get("nasa_pass") or "").strip())
    if not has_login:
        from PySide6.QtWidgets import QDialog

        login = LoginDialog()
        if login.exec() != QDialog.DialogCode.Accepted:
            return 0
    if not pick_gps_sdr_sim_path_if_needed(None):
        return 0
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
